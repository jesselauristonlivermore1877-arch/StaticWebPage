# -*- coding: utf-8 -*-
# ==============================================================================
# screener.py v4 — GEA 選股引擎（日線 EOD 官方大盤脫鉤精準版 - 解除點數限制）
#
# 升級特點：
#   1. 徹底與 yfinance 錯亂的大盤數據脫鉤，強制使用證交所官方收盤價。
#   2. 盤中/盤後全面即時覆蓋，解決大盤與上櫃 OTC 價格定格問題。
#   3. 【重要修復】拔除任何大盤點數硬限制，大盤點數與台積電貢獻點數正常顯示。
#   4. 【精準校準】直連 MIS API 抓取官方昨收價 (y)，完全避免因 Yahoo 缺失歷史
#      資料或除權息導致的漲跌點數 (idx_pts) 計算錯誤與隱形問題。
#   5. 完全保留 Evans 調整已久的 Flex Carousel 輸出 Layout，不影響前端視覺。
# ==============================================================================
import os
import threading
from datetime import datetime

import numpy as np
import pandas as pd

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False

import engines
import flex
from engines import core_universe, pad_str

W_TSMC = float(os.environ.get("W_TSMC", "0.42"))
EMA_LADDER = [9, 23, 60, 97, 113, 288, 565, 1356]
SMA_LADDER = [5, 20, 60, 120, 240]   # 傳統均線：週/月/季/半年/年（收盤價）
BENCH = "^TWII"
TSMC = "2330.TW"

_lock = threading.Lock()
_cache = {"date": None, "data": {}, "stats": {}}
_adhoc = {"date": None, "stats": {}}   # 非地圖股的臨時統計

DISCLAIMER = "—\n以上為公開資料整理，僅供參考，非投資建議。"

LEGEND = (
    "📖 【名詞解釋】\n"
    "・高點回檔DD%＝收盤價 ÷ 52週最高價(盤中高點) − 1\n"
    " 例：最高185.5、今收144 → 回檔 -22%\n"
    "・YTD＝今年以來累計漲跌%\n"
    "・均線±%＝收盤距該均線的百分比\n"
    " 正＝站在線上方、負＝跌破在線下方\n"
    "・SMA(收盤價簡單平均)：5週線/20月線/\n"
    " 60季線/120半年線/240年線\n"
    "・EMA(以開高低收÷4計)：9/23/60/97/113/288/565/1356\n"
    "・轉強✅＝站上5日線且站上EMA9\n"
    "・格局：站上月線＝多頭格局；\n"
    " 跌破季線(生命線)＝中長多接受考驗\n"
    "・市場體感＝產業地圖全檔中位數"
)
LEGEND_SHORT = "📖 回檔=距52週最高價｜均線±%=距線距離｜@名詞 看完整解釋"


# ── 資料層 ───────────────────────────────────────────────────────
def _all_tickers():
    return list(core_universe.keys()) + [BENCH]

def _tw_now():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Taipei"))

def _today_key():
    return _tw_now().strftime("%Y%m%d")

def _data_date():
    bench = _cache.get("stats", {}).get(BENCH)
    if bench and bench.get("date"):
        return bench["date"]
    return _tw_now().strftime("%m-%d")

_CUTOFF_HHMM = 1400

def _hhmm(dt):
    return dt.hour * 100 + dt.minute

def cache_ready():
    if _cache["date"] != _today_key() or not _cache["stats"]:
        return False
    warm = _cache.get("ts")
    if warm is not None and _hhmm(warm) < _CUTOFF_HHMM <= _hhmm(_tw_now()):
        return False
    return True

def build_cache():
    if not HAS_YF:
        return 0, ["yfinance 未安裝"]
    with _lock:
        if cache_ready():
            return len(_cache["stats"]), []
        tickers = _all_tickers()
        gc_mod = __import__("gc")

        def _extract(rw, t):
            try:
                df = rw[t].dropna(subset=["Close"]) if isinstance(rw.columns, pd.MultiIndex) else rw.dropna(subset=["Close"])
                return df if len(df) >= 60 else None
            except Exception:
                return None

        data, failed = {}, []
        n = len(tickers)
        third = (n + 2) // 3
        for batch in (tickers[:third], tickers[third:2*third], tickers[2*third:]):
            if not batch:
                continue
            raw = yf.download(batch, period="8y", interval="1d",
                              auto_adjust=True, group_by="ticker",
                              threads=True, progress=False)
            for t in batch:
                df = _extract(raw, t)
                if df is not None:
                    data[t] = df
                else:
                    failed.append(t)
            del raw
            gc_mod.collect()
        
        if failed:
            import time as _time
            def _flip(t):
                return t.replace(".TWO", ".TW") if t.endswith(".TWO") else t.replace(".TW", ".TWO")
            retry = list({x for t in failed for x in (t, _flip(t)) if x != BENCH})
            for _wait in (8, 45):
                if not failed:
                    break
                _time.sleep(_wait)
                try:
                    raw2 = yf.download(retry, period="10y", interval="1d",
                                       auto_adjust=True, group_by="ticker",
                                       threads=False, progress=False)
                    still = []
                    for t in failed:
                        df = _extract(raw2, t)
                        if df is None:
                            df = _extract(raw2, _flip(t))
                        if df is not None:
                            data[t] = df
                        else:
                            still.append(t)
                    failed = still
                    del raw2; gc_mod.collect()
                except Exception:
                    pass
        
        # 🛡️ 修正大盤：強制使用官方真實加權指數覆蓋，徹底擺脫 Yahoo 錯亂
        official_date = None
        try:
            od = engines.get_taiex_daily()
            bdf = data.get(BENCH)
            if od:
                ts = pd.Timestamp(od[0])
                c = float(od[1])
                # 防禦 Yahoo 回傳空表的 IndexError 錯誤
                if bdf is not None and not bdf.empty:
                    if ts == bdf.index[-1].normalize():
                        bdf.iloc[-1, bdf.columns.get_loc("Close")] = c
                        bdf.iloc[-1, bdf.columns.get_loc("Open")] = c
                        bdf.iloc[-1, bdf.columns.get_loc("High")] = c
                        bdf.iloc[-1, bdf.columns.get_loc("Low")] = c
                    elif ts > bdf.index[-1].normalize():
                        nr = pd.DataFrame({"Open": [c], "High": [c], "Low": [c], "Close": [c]}, index=[ts])
                        data[BENCH] = pd.concat([bdf, nr])
                else:
                    data[BENCH] = pd.DataFrame({"Open": [c], "High": [c], "Low": [c], "Close": [c]}, index=[ts])
                official_date = ts
        except Exception:
            pass
        
        try:
            after_close = not _is_market_hours()
            closes = engines.get_official_closes() if after_close else {}
            amounts = engines.get_official_amounts() if after_close else {}
            stock_date = official_date if official_date is not None else pd.Timestamp(
                _tw_now().strftime("%Y-%m-%d"))
            for tk, df in list(data.items()):
                if tk == BENCH or df is None or not len(df):
                    continue
                code = tk.split(".")[0]
                p = closes.get(code)
                if not p:
                    continue
                av = amounts.get(code)
                off_vol = float(av[1]) if (av and av[1]) else None
                last_day = df.index[-1].normalize()
                if stock_date > last_day:
                    vol = off_vol if off_vol is not None else (
                        float(df["Volume"].iloc[-1]) if "Volume" in df and len(df) else 0.0)
                    nr = pd.DataFrame(
                        {"Open": [p], "High": [p], "Low": [p], "Close": [p],
                         "Volume": [vol]}, index=[stock_date])
                    data[tk] = pd.concat([df, nr])
                else:
                    df.iloc[-1, df.columns.get_loc("Close")] = p
                    if off_vol is not None and "Volume" in df.columns:
                        df.iloc[-1, df.columns.get_loc("Volume")] = off_vol
        except Exception:
            pass

        stats = {}
        bench_close = data.get(BENCH, pd.DataFrame()).get("Close")
        for t, df in data.items():
            stats[t] = _compute_stats(df, bench_close)
            
        keep = {BENCH: data[BENCH]} if BENCH in data else {}
        _cache.update({"date": _today_key(), "data": keep, "stats": stats, "ts": _tw_now()})
        _adhoc.update({"date": None, "stats": {}})
        return len(stats), failed

def _compute_stats(df, bench_close):
    close = df["Close"]
    ohlc4 = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0
    last = float(close.iloc[-1])

    hi_52w = float(df["High"].tail(252).max())
    hi_60d = float(df["High"].tail(60).max())
    dd_52w = last / hi_52w - 1 if hi_52w else 0.0
    dd_60d = last / hi_60d - 1 if hi_60d else 0.0

    def ret(n):
        if len(close) <= n:
            return None
        return float(close.iloc[-1] / close.iloc[-1 - n] - 1)
    r1, r5, r20 = ret(1), ret(5), ret(20)
    # 近 21 根日收盤（新→舊）。盤中 last 是即時價、但 r5/r20 仍是「昨天的近5/20日」，
    # 大跌當天會出現「當日 -4% 但近5日仍普漲」這種自相矛盾的判讀 → 存基準價供覆蓋層重算。
    c_hist = [float(x) for x in close.iloc[-21:][::-1]] if len(close) >= 2 else []

    amt_today = amt_dev = base_avg_amt = None
    try:
        if "Volume" in df and len(df) >= 6:
            amts = (df["Close"] * df["Volume"]).astype(float)
            amt_today = float(amts.iloc[-1])
            base5 = amts.iloc[-6:-1]
            base_avg = float(base5.mean()) if len(base5) else 0.0
            if base_avg > 0:
                base_avg_amt = base_avg
                amt_dev = amt_today / base_avg - 1
    except Exception:
        pass

    ytd = ytd_hi = None
    try:
        yr = close.index[-1].year
        prev = close[close.index.year < yr]
        if len(prev):
            base = float(prev.iloc[-1])
            ytd = last / base - 1
            yhi = df["High"][df.index.year == yr]
            if len(yhi):
                ytd_hi = float(yhi.max()) / base - 1
    except Exception:
        pass

    rs5 = rs20 = None
    if bench_close is not None and len(bench_close) > 21:
        b5 = float(bench_close.iloc[-1] / bench_close.iloc[-6] - 1)
        b20 = float(bench_close.iloc[-1] / bench_close.iloc[-21] - 1)
        if r5 is not None:
            rs5 = r5 - b5
        if r20 is not None:
            rs20 = r20 - b20

    ladder = {}
    for span in EMA_LADDER:
        if len(ohlc4) >= span:
            ladder[span] = float(ohlc4.ewm(span=span, adjust=False).mean().iloc[-1])
    above = [s for s in EMA_LADDER if s in ladder and last >= ladder[s]]
    sma = {}
    for span in SMA_LADDER:
        if len(close) >= span:
            sma[span] = float(close.tail(span).mean())
    above_sma = [s for s in SMA_LADDER if s in sma and last >= sma[s]]
    dsma = {n: last / v - 1 for n, v in sma.items()}
    dema = {n: last / v - 1 for n, v in ladder.items()}

    prev_close = float(close.iloc[-2]) if len(close) >= 2 else None
    return {
        "last": last, "dd_52w": dd_52w, "dd_60d": dd_60d,
        "prev_close": prev_close, "hi_52w": hi_52w, "hi_60d": hi_60d,
        "c_hist": c_hist,
        "r1": r1, "r5": r5, "r20": r20, "ytd": ytd, "ytd_hi": ytd_hi, "rs5": rs5, "rs20": rs20,
        "dsma": dsma, "dema": dema,
        "ema": ladder, "above": above, "sma": sma, "above_sma": above_sma,
        "above_e23": (23 in ladder and last >= ladder[23]),
        "vol": (float(df["Volume"].iloc[-1]) if "Volume" in df and len(df) else None),
        "amt_today": amt_today, "amt_dev": amt_dev, "base_avg_amt": base_avg_amt,
        "date": (df.index[-1].strftime("%m-%d") if len(df) else None),
    }

# 盤中即時價覆蓋快取
_intraday_px = {"ts": 0.0, "live_px": {}}

def _mis_num(v):
    """MIS 欄位轉數字。'-'、空字串、None 一律回 None（那代表『沒有這個值』不是 0）。"""
    try:
        if v is None:
            return None
        t = str(v).replace(",", "").strip()
        if t in ("", "-"):
            return None
        f = float(t)
        return f if f > 0 else None
    except Exception:
        return None


def _mis_price(it, allow_quote=True):
    """MIS 取價鏈：z(最近成交) → 最佳一檔中價 → o(開盤) → h/l 中值。

    **刻意不用 y(昨收) 頂替。** MIS 在該檔當下沒有成交時 z 會是 '-'，
    舊版拿 y 頂替 → last 與 prev_close 同值 → 漲跌算出來剛好 +0.0%，
    整張表看起來像「今天全市場都沒動」，比誠實留著昨日收盤更糟、也更難察覺。
    回 (價格, 來源標籤)；都拿不到就回 (None, "none")，呼叫端直接跳過不覆蓋。

    allow_quote=False（非盤中）時**只認 z**。收盤後 MIS 的委買賣價可能是殘留的
    舊報價，拿它去蓋掉 build_cache already 寫好的官方定版收盤價，等於把正確的
    數字換成過期的——所以非盤中一律不用報價類回退。
    """
    z = _mis_num(it.get("z"))
    if z:
        return z, "z"
    if not allow_quote:
        return None, "none(非盤中只認成交價)"
    b = _mis_num(str(it.get("b") or "").split("_")[0])
    a = _mis_num(str(it.get("a") or "").split("_")[0])
    if b and a:
        return (b + a) / 2, "bidask"
    if b or a:
        return (b or a), "bidask"
    o = _mis_num(it.get("o"))
    if o:
        return o, "open"
    h, l = _mis_num(it.get("h")), _mis_num(it.get("l"))
    if h and l:
        return (h + l) / 2, "hilo"
    return None, "none"


def _fetch_all_live_prices():
    """獨立、輕量的即時報價抓取：全地圖 + 官方真實大盤點位
    ⚠️ 校準升級：不僅抓最新價 (z)，也把昨收 (y) 抓出來供精準點數計算"""
    chans = ["tse_t00.tw"]
    for tk in core_universe.keys():
        code = tk.split(".")[0]
        if tk.endswith(".TWO"):
            chans.append(f"otc_{code}.tw")
        else:
            chans.append(f"tse_{code}.tw")
    
    px_dict = {}
    # 非盤中只認成交價 z：收盤後的委買賣殘留報價不可以蓋掉官方定版收盤價
    _allow_q = _is_market_hours()
    _stat = {"batches": 0, "returned": 0, "src": {}, "rt": [], "allow_quote": _allow_q}
    import requests
    try:
        # 批次 90 → 40：MIS 對單次 ex_ch 的channel 數有上限，塞太多會靜默截斷/退空。
        for i in range(0, len(chans), 40):
            batch = "|".join(chans[i:i+40])
            r = requests.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                             params={"ex_ch": batch, "json": "1", "delay": "0"},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            j = r.json() or {}
            arr = j.get("msgArray", []) or []
            _stat["batches"] += 1
            _stat["returned"] += len(arr)
            _stat["rt"].append(f"{j.get('rtcode', '?')}/{str(j.get('rtmessage', ''))[:20]}")
            for it in arr:
                c = it.get("c", "")
                last_px, src = _mis_price(it, allow_quote=_allow_q)
                val_y = _mis_num(it.get("y"))
                val_v = _mis_num(it.get("v"))
                _stat["src"][src] = _stat["src"].get(src, 0) + 1
                # 拿不到即時價就**不要**放進 px_dict —— 呼叫端會跳過覆蓋，
                # 保留快取裡誠實的昨日收盤，而不是偽造一個 +0.0%。
                if last_px is not None:
                    key = BENCH if c == "t00" else c
                    px_dict[key] = {"last": last_px, "prev": val_y,
                                    "vol": val_v, "src": src}
    except Exception as e:
        _stat["err"] = f"{type(e).__name__}: {e}"
    _intraday_px["stat"] = _stat
    
    # 🛡️ 雙重保險：如果 MIS 大盤端點收盤後清空，退用官方當日定版收盤價
    if BENCH not in px_dict:
        try:
            od = engines.get_taiex_daily()
            if od:
                px_dict[BENCH] = {"last": float(od[1]), "prev": None, "vol": None}
        except Exception:
            pass
            
    return px_dict

def _refresh_intraday_prices():
    """盤中用 MIS 即時價(與精準昨收)覆蓋快取 stats 的 last 與 prev_close。"""
    import time as _t
    now = _t.time()
    
    if "live_px" not in _intraday_px or (now - _intraday_px.get("ts", 0) > 60):
        px = _fetch_all_live_prices()
        if px:
            _intraday_px["live_px"] = px
            _intraday_px["ts"] = now
            
    live_px = _intraday_px.get("live_px", {})
    if not live_px:
        return
    # 量能只在真正盤中覆蓋：收盤後維持官方 EOD 口徑（含盤後定價/零股），不被 MIS 一般撮合蓋小
    _use_vol = _is_market_hours()

    with _lock:
        for tk, st in _cache["stats"].items():
            code = tk.split(".")[0]
            if tk == BENCH:
                live_info = live_px.get(BENCH)
            else:
                live_info = live_px.get(code)
            
            if live_info is None or not st:
                continue
            _overlay_stat_price(st, live_info, use_vol=_use_vol)

def _overlay_stat_price(st, live_info, use_vol=False):
    """用即時資訊就地更新衍生欄位。接受 dict 格式以寫入精準昨收。"""
    if isinstance(live_info, dict):
        live = live_info["last"]
        prev = live_info.get("prev")
        if prev is not None and prev > 0:
            st["prev_close"] = prev
    else:
        live = live_info
        
    prev_close = st.get("prev_close")
    st["last"] = live
    if prev_close and prev_close > 0:
        st["r1"] = live / prev_close - 1

    # 盤中把「近5日/近20日」一起拉到今天。
    # 不做的話：當日 -4%、近5日卻還是昨天算的「普漲」，判讀自相矛盾（Evans 2026-07-28 抓到）。
    # c_hist[0]=昨收、c_hist[4]=5 個交易日前、c_hist[19]=20 個交易日前。
    if use_vol:
        ch = st.get("c_hist") or []
        if len(ch) >= 5 and ch[4]:
            st["r5"] = live / ch[4] - 1
        if len(ch) >= 20 and ch[19]:
            st["r20"] = live / ch[19] - 1

    # 盤中量能即時化：MIS 的 v 單位是**張**，但 st["vol"] 全站口徑是**股**
    # （_fmt_vol 會再除以 1000 換算張數）→ 不乘 1000 的話台積電一萬張會顯示成 11 張。
    if use_vol and isinstance(live_info, dict):
        lv = live_info.get("vol")
        if lv is not None and lv > 0:
            st["vol"] = lv * 1000
            st["amt_today"] = live * lv * 1000
            base_avg = st.get("base_avg_amt")
            if base_avg and base_avg > 0:
                st["amt_dev"] = st["amt_today"] / base_avg - 1
        
    sma = st.get("sma") or {}
    ema = st.get("ema") or {}
    st["dsma"] = {n: live / v - 1 for n, v in sma.items() if v}
    st["dema"] = {n: live / v - 1 for n, v in ema.items() if v}
    st["above_sma"] = [s for s in sma if sma[s] and live >= sma[s]]
    st["above"] = [s for s in ema if ema[s] and live >= ema[s]]
    st["above_e23"] = bool(ema.get(23) and live >= ema[23])
    hi52 = st.get("hi_52w")
    if hi52:
        st["dd_52w"] = live / hi52 - 1
    hi60 = st.get("hi_60d")
    if hi60:
        st["dd_60d"] = live / hi60 - 1

def _ensure():
    ok = True
    if not cache_ready():
        n, failed = build_cache()
        ok = n > 0
    if ok:
        try:
            _refresh_intraday_prices()
        except Exception:
            pass
    return ok

def force_rewarm():
    with _lock:
        _cache.update({"date": None, "stats": {}, "data": {}, "ts": None})
        _adhoc.update({"date": None, "stats": {}})
    try:
        engines._proc_cache.clear()
    except Exception:
        pass
    return build_cache()

def get_stats_for_codes(codes):
    out, missing = {}, []
    for c in codes:
        hit = None
        for suf in (".TW", ".TWO"):
            if c + suf in _cache["stats"]:
                hit = _cache["stats"][c + suf]
                break
        if hit:
            out[c] = hit
        elif _adhoc["date"] == _today_key() and c in _adhoc["stats"] and not (
                _adhoc.get("ts") is not None
                and _hhmm(_adhoc["ts"]) < _CUTOFF_HHMM <= _hhmm(_tw_now())):
            out[c] = _adhoc["stats"][c]
        else:
            missing.append(c)
    if missing and HAS_YF:
        cands = [c + suf for c in missing for suf in (".TW", ".TWO")]
        try:
            raw = yf.download(cands, period="1y", interval="1d",
                              auto_adjust=True, group_by="ticker",
                              threads=True, progress=False)
            bench_close = _cache["data"].get(BENCH, pd.DataFrame()).get("Close")
            if _adhoc["date"] != _today_key() or (
                    _adhoc.get("ts") is not None
                    and _hhmm(_adhoc["ts"]) < _CUTOFF_HHMM <= _hhmm(_tw_now())):
                _adhoc.update({"date": _today_key(), "stats": {}, "ts": _tw_now()})
            for c in missing:
                for suf in (".TW", ".TWO"):
                    try:
                        df = raw[c + suf].dropna(subset=["Close"])
                        if len(df) >= 60:
                            s = _compute_stats(df, bench_close)
                            _adhoc["stats"][c] = s
                            out[c] = s
                            break
                    except Exception:
                        continue
        except Exception:
            pass
    return out


# ── 工具 ─────────────────────────────────────────────────────────
def _tier_emoji(dd):
    if dd <= -0.40:
        return "🔴"
    if dd <= -0.30:
        return "🟠"
    if dd <= -0.20:
        return "🟡"
    if dd <= -0.10:
        return "⚪"
    return "▫️"

def _pct(x, digits=1):
    return f"{x*100:+.{digits}f}%" if x is not None else "  n/a"

def _px(v):
    if v is None:
        return "n/a"
    return f"{v:,.0f}" if v >= 100 else f"{v:.1f}"

def _chg_pts(st):
    """由 last 與 prev_close 精準反推當日漲跌點數/元"""
    last = st.get("last")
    prev = st.get("prev_close")
    if last is not None and prev is not None and prev > 0:
        return last - prev
        
    # 若退無可退，用 r1 概算反推
    r1 = st.get("r1")
    if last is not None and r1 is not None:
        prev_fallback = last / (1 + r1)
        return last - prev_fallback
    return None

def _bench_r5():
    s = _cache["stats"].get(BENCH)
    return s["r5"] if s else None

def build_legend():
    return [LEGEND]

def build_sector_list():
    secs = sorted(set(m["sector"] for m in core_universe.values()))
    msg = "🗂 【產業地圖族群一覽】\n"
    msg += "輸入「@回檔 族群名」看該族群明細\n" + "-"*28 + "\n"
    msg += "、".join(secs)
    msg += "\n\n💡 族群名打部分關鍵字也可以，\n如 @回檔 被動、@回檔 CPO"
    return [msg]


# ── 引擎 A：回檔追蹤 ─────────────────────────────────────────────
def build_drawdown_overview():
    rows_by_sector = {}
    for tk, meta in core_universe.items():
        st = _cache["stats"].get(tk)
        if not st or st["dd_52w"] > -0.10:
            continue
        rows_by_sector.setdefault(meta["sector"], []).append(
            (tk.split(".")[0], meta["name"], st["dd_52w"], st.get("ytd"), st.get("ytd_hi"),
             st.get("last")))
    if not rows_by_sector:
        return ["✅ 目前產業地圖內沒有回檔逾 10% 的標的。\n" + DISCLAIMER]

    n_total = sum(len(v) for v in rows_by_sector.values())
    trows = []
    order = sorted(rows_by_sector.items(), key=lambda kv: min(r[2] for r in kv[1]))
    for sector, rows in order:
        rows.sort(key=lambda r: r[2])
        trows.append(sector)                       
        for code, name, dd, ytd, yh, px in rows:
            yy = (f"{yh*100:+.0f}%→{ytd*100:+.0f}%"
                  if (yh is not None and ytd is not None) else "n/a")
            trows.append([f"{_tier_emoji(dd)}{code} {name}", _px(px), yy,
                          f"{dd*100:.0f}%"])
    bubbles = flex.flex_table(
        f"📉 產業地圖・高點回檔追蹤 ({_data_date()})",
        ["名稱", "收盤", "今年高→現", "回檔"], [8, 4, 7, 3], trows,
        aligns=["start", "start", "end", "end"],
        subtitle=(f"距52週最高價回檔逾10% 共 {n_total} 檔 "
                  "⚪-10~20 🟡-20~30 🟠-30~40 🔴-40↑ ＊先看今年漲多少，再看回檔深度"),
        color_cols=(3,), rows_per_bubble=45,
        note="💡 @回檔 族群名→明細｜@族群→清單\n" + DISCLAIMER)
    return flex.to_stacked_messages(bubbles, f"高點回檔追蹤 共{n_total}檔")

def build_drawdown_sector(query):
    hits = {tk: m for tk, m in core_universe.items() if query in m["sector"]}
    if not hits:
        return build_sector_list()
    items = []
    for tk, meta in hits.items():
        st = _cache["stats"].get(tk)
        if st:
            items.append((tk, meta, st))
    items.sort(key=lambda x: x[2]["dd_52w"])
    trows = []
    for tk, meta, st in items:
        code = tk.split(".")[0]
        ds, de = st.get("dsma", {}), st.get("dema", {})
        asma = "/".join(str(a) for a in st.get("above_sma", [])) or "無"
        aema = "/".join(str(a) for a in st["above"]) or "無"
        cp = _chg_pts(st)
        px = _px(st.get('last')) + (f"({cp:+,.1f})" if cp is not None else "")
        trows.append({"cells": [f"{_tier_emoji(st['dd_52w'])}{meta['name']}({code})",
                                px, _pct(st.get("r1")), f"{st['dd_52w']*100:.0f}%"],
                      "sub": (f"今年高{_pct(st.get('ytd_hi'),0)}→現{_pct(st.get('ytd'),0)}｜"
                              f"月線{_pct(ds.get(20))}｜季線{_pct(ds.get(60))}｜"
                              f"EMA23{_pct(de.get(23))}｜站上SMA:{asma}｜EMA:{aema}")})
    bubbles = flex.flex_table(
        f"📉 {query}・回檔明細 ({_data_date()})",
        ["名稱", "收盤(漲跌)", "當日", "回檔"], [4, 3, 2, 2], trows,
        color_cols=(2, 3), rows_per_bubble=20,
        note=LEGEND_SHORT + "\n" + DISCLAIMER)
    return flex.to_stacked_messages(bubbles, f"{query} 回檔明細")


# ── 引擎 B：轉強雷達 ─────────────────────────────────────────────
VIP_WEIGHTS = {
    "rs": 0.32,       
    "trend": 0.24,    
    "pullback": 0.16,  
    "volume": 0.16,   
    "momentum": 0.12,  
}

VIP_GATE = {
    "min_above_sma20": True,   
    "max_drawdown": -0.45,     
    "min_rs20": -0.05,         
}

def _clip01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)

def _vip_score(st):
    ds = st.get("dsma", {})
    rs20 = st.get("rs20")
    dd = st.get("dd_52w")
    above_sma = st.get("above_sma", []) or []
    amt_dev = st.get("amt_dev")
    r5 = st.get("r5")
    
    if VIP_GATE["min_above_sma20"] and ds.get(20, -1) < 0: return None
    if dd is not None and dd < VIP_GATE["max_drawdown"]: return None
    if rs20 is not None and rs20 < VIP_GATE["min_rs20"]: return None
    
    f_rs = _clip01(((rs20 or 0) + 0.05) / 0.35)          
    f_trend = len(above_sma) / 5.0                        
    ddv = dd if dd is not None else -0.15
    if ddv >= -0.08:
        f_pull = _clip01(1 - ((-0.08 - ddv) / -0.08) * 0.4)  
    else:
        f_pull = _clip01(1 - (abs(ddv) - 0.08) / 0.22)       
    f_vol = _clip01(((amt_dev or 0) + 0.1) / 0.5)        
    f_mom = _clip01(((r5 or 0) + 0.05) / 0.15)           
    score = (VIP_WEIGHTS["rs"] * f_rs + VIP_WEIGHTS["trend"] * f_trend +
             VIP_WEIGHTS["pullback"] * f_pull + VIP_WEIGHTS["volume"] * f_vol +
             VIP_WEIGHTS["momentum"] * f_mom) * 100
    return score, {"rs": f_rs, "trend": f_trend, "pull": f_pull,
                   "vol": f_vol, "mom": f_mom}

def vip_debug():
    out = ["🔧 @日選 診斷", "=" * 20]
    ready = cache_ready()
    out.append(f"▍cache_ready: {ready}")
    if not ready:
        n, failed = build_cache()
        out.append(f"▍重建快取: {n} 檔（失敗 {len(failed)}）")
    stats = _cache.get("stats", {})
    total = len([k for k in stats if k != BENCH])
    out.append(f"▍快取個股數: {total}")
    if total == 0:
        out.append("▍→ 快取空！凌晨/剛重啟 yfinance 可能 429，稍後或盤中再試")
        return "\n".join(out)
    
    no_sma20 = no_dd = no_rs = passed = 0
    no_stat_fields = 0
    for tk, meta in core_universe.items():
        st = stats.get(tk)
        if not st: continue
        ds = st.get("dsma", {})
        rs20, dd = st.get("rs20"), st.get("dd_52w")
        if not ds:
            no_stat_fields += 1
            continue
        if VIP_GATE["min_above_sma20"] and ds.get(20, -1) < 0:
            no_sma20 += 1; continue
        if dd is not None and dd < VIP_GATE["max_drawdown"]:
            no_dd += 1; continue
        if rs20 is not None and rs20 < VIP_GATE["min_rs20"]:
            no_rs += 1; continue
        passed += 1
    out.append(f"▍門檻刷除：跌破月線 {no_sma20}｜回檔>45% {no_dd}｜"
               f"弱於大盤(rs20<-5%) {no_rs}｜缺均線資料 {no_stat_fields}")
    out.append(f"▍通過門檻入選: {passed} 檔")
    if passed == 0:
        out.append("▍→ 全被門檻刷掉（多半是大盤弱、普遍跌破月線）。"
                   "可放寬 VIP_GATE 或改成不淘汰純排序")
    
    b = stats.get(BENCH)
    if b:
        bs = b.get("dsma", {})
        out.append(f"▍大盤 距月線{_pct(bs.get(20))}｜距季線{_pct(bs.get(60))}")
    return "\n".join(out)

def build_vip_screen(top_n=20):
    if not _ensure():
        return [{"type": "text", "text": "⚠️ 選股資料建置中，稍候再試。"}]
    ranked = []
    for tk, meta in core_universe.items():
        st = _cache["stats"].get(tk)
        if not st or not st.get("dsma"):
            continue
        score, fac = _vip_score_open(st)
        ranked.append((tk.split(".")[0], meta["name"], meta.get("sector", ""),
                       score, st, fac))
    if not ranked:
        return [{"type": "text", "text": "⚠️ 選股快取空，稍後再試。"}]
    ranked.sort(key=lambda r: -r[3])
    ranked = ranked[:top_n]

    headers = ["#", "標的", "分數", "當日", "RS20", "距高"]
    widths = [1, 5, 2, 2, 2, 2]
    aligns = ["start", "start", "end", "end", "end", "end"]
    rows = []
    for i, (code, name, sector, score, st, fac) in enumerate(ranked, 1):
        ds = st.get("dsma", {})
        below = ds.get(20, 0) < 0
        mark = "⚠️" if below else ""      
        r1, rs20, dd = st.get("r1"), st.get("rs20"), st.get("dd_52w")
        cells = [str(i), f"{mark}{code} {name}", f"{score:.0f}",
                 _pct(r1), _pct(rs20, 0),
                 f"{dd*100:.0f}%" if dd is not None else "—"]
        sub = (f" 趨勢{fac['trend']*100:.0f}｜強度{fac['rs']*100:.0f}｜"
               f"回檔{fac['pull']*100:.0f}｜量{fac['vol']*100:.0f}｜"
               f"動能{fac['mom']*100:.0f}｜{sector}"
               + ("｜⚠️破月線" if below else ""))
        rows.append({"cells": cells, "sub": sub})

    b = _cache["stats"].get(BENCH)
    bs = b.get("dsma", {}) if b else {}
    regime = ("🟢大盤月線上" if bs.get(20, -1) >= 0 else "⚠️大盤破月線(弱勢，⚠️標注者宜謹慎)")
    subtitle = (f"多因子分數排序｜相對強度32%+趨勢24%+回檔16%+量能16%+動能12%"
                f"｜{regime}")
    note = ("分數＝各因子標準化加權（子分數見每列下方）。⚠️＝已跌破月線，"
            "大盤弱時榜上仍會有，宜謹慎。以上為量化篩選，非投資建議。")
    bubbles = flex.flex_table(f"💎 GEA 多因子日選 VIP（{_data_date()}）",
                              headers, widths, rows, subtitle=subtitle,
                              aligns=aligns, color_cols=(3, 4), note=note,
                              rows_per_bubble=20)
    return flex.to_stacked_messages(bubbles, f"GEA 多因子日選 VIP 前 {len(rows)}名")

def _vip_score_open(st):
    ds = st.get("dsma", {})
    rs20 = st.get("rs20")
    dd = st.get("dd_52w")
    above_sma = st.get("above_sma", []) or []
    amt_dev = st.get("amt_dev")
    r5 = st.get("r5")
    f_rs = _clip01(((rs20 or 0) + 0.05) / 0.35)
    f_trend = len(above_sma) / 5.0
    ddv = dd if dd is not None else -0.15
    if ddv >= -0.08:
        f_pull = _clip01(1 - ((-0.08 - ddv) / -0.08) * 0.4)
    else:
        f_pull = _clip01(1 - (abs(ddv) - 0.08) / 0.22)
    f_vol = _clip01(((amt_dev or 0) + 0.1) / 0.5)
    f_mom = _clip01(((r5 or 0) + 0.05) / 0.15)
    score = (VIP_WEIGHTS["rs"] * f_rs + VIP_WEIGHTS["trend"] * f_trend +
             VIP_WEIGHTS["pullback"] * f_pull + VIP_WEIGHTS["volume"] * f_vol +
             VIP_WEIGHTS["momentum"] * f_mom) * 100
    return score, {"rs": f_rs, "trend": f_trend, "pull": f_pull,
                   "vol": f_vol, "mom": f_mom}

def build_strength_ranking(top_n=40):
    b = _cache["stats"].get(BENCH)
    if not b:
        return ["⚠️ 大盤資料缺漏。"]
    bs, be = b.get("dsma", {}), b.get("dema", {})
    regime = ("🟢 月線上＝多頭格局" if bs.get(20, -1) >= 0 else
              ("⚠️ 跌破季線＝中長多接受考驗（上方套牢賣壓重）" if bs.get(60, 0) < 0
               else "🔶 月線下、季線上＝多空拉鋸"))
    rows = []
    for tk, meta in core_universe.items():
        st = _cache["stats"].get(tk)
        if not st:
            continue
        ds, de = st.get("dsma", {}), st.get("dema", {})
        flag = "✅" if (ds.get(5, -1) >= 0 and de.get(9, -1) >= 0) else " "
        pos = "🟢" if ds.get(20, -1) >= 0 else ("⚠️" if ds.get(60, 0) < 0 else "▫️")
        rows.append((tk.split(".")[0], meta["name"], st.get("last"), st.get("r1"),
                     ds.get(5), ds.get(20), flag, pos))
    rows.sort(key=lambda r: (r[4] if r[4] is not None else -9), reverse=True)

    bp = _chg_pts(b)
    head = [flex.text(f"⚡ 轉強雷達 ({_data_date()})",
                      size="md", weight="bold", color=flex.C_TITLE),
            flex.sep()]
    head += flex.kv_rows([
        ("🧭 大盤", f"{b['last']:,.0f}" + (f"（{bp:+,.0f} 點）" if bp is not None else ""), True),
        ("當日", _pct(b.get("r1")), True),
        ("5日線 / EMA9", f"{_pct(bs.get(5))} / {_pct(be.get(9))}", False),
        ("月線 / 季線", f"{_pct(bs.get(20))} / {_pct(bs.get(60))}", False)])
    head.append(flex.sep())
    head.append(flex.text(regime, size="xs", wrap=True))
    head.append(flex.text("✅短線轉強＝站上5日線+EMA9\n格局：🟢月線上｜▫️月線下季線上｜⚠️破季線",
                          size="xxs", color=flex.C_SUB, wrap=True))
    head_msg = flex.to_flex_message([flex.bubble(head)], "轉強雷達・大盤")
    key = lambda r: (r[4] if r[4] is not None else -9)
    g_up   = sorted([r for r in rows if r[7] == "🟢"], key=key, reverse=True)
    g_mid  = sorted([r for r in rows if r[7] == "▫️"], key=key, reverse=True)
    g_dn   = sorted([r for r in rows if r[7] == "⚠️"], key=key, reverse=True)
    trows = []
    for sec, grp, cap in [(f"🟢 月線上・多頭格局 ({len(g_up)}檔)", g_up, None),
                          (f"▫️ 月線下季線上・拉鋸 ({len(g_mid)}檔)", g_mid, None),
                          (f"⚠️ 破季線 (前{min(top_n, len(g_dn))}/{len(g_dn)}檔)", g_dn, top_n)]:
        if not grp:
            continue
        trows.append(sec)
        for code, name, px, r1, d5, d20, flag, pos in (grp[:cap] if cap else grp):
            trows.append([f"{code} {name}", _px(px), _pct(r1), _pct(d5), _pct(d20),
                          "✅" if flag.strip() else " "])
    bubbles = flex.flex_table(
        "⚡ 相對強度排行（依格局分節）", ["名稱", "收盤", "當日", "5日線", "月線", "轉強"],
        [4, 2, 2, 2, 2, 1], trows, color_cols=(2, 3, 4), rows_per_bubble=35,
        note="✅轉強＝站上5日線+EMA9｜大盤弱勢時還站在月線/季線上的，就是相對強度名單\n"
             + LEGEND_SHORT + "\n" + DISCLAIMER)
    return [head_msg] + flex.to_stacked_messages(bubbles, "轉強雷達・排行")


# ── 大盤成交金額（期交所家族 TWSE OpenAPI，抓不到整列自動略過）──────
_turnover_cache = {"date": None, "ts": None, "rows": []}

def _fetch_fmtqik(ym):
    """抓 TWSE 市場成交資訊（月檔）→ [(yyyymmdd, 成交金額元)]。失敗回 []。"""
    import requests
    try:
        r = requests.get("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK",
                         params={"date": ym + "01", "response": "json"}, timeout=8)
        j = r.json()
        out = []
        for row in j.get("data") or []:
            y, m, d = row[0].split("/")          # 民國年
            key = f"{int(y)+1911}{m}{d}"
            out.append((key, float(row[2].replace(",", ""))))
        return out
    except Exception:
        return []

def _turnover_rows():
    now = _tw_now()
    c = _turnover_cache
    if (c["date"] == _today_key() and c["rows"] and not (
            c["ts"] is not None and _hhmm(c["ts"]) < _CUTOFF_HHMM <= _hhmm(now))):
        return c["rows"]
    rows = _fetch_fmtqik(now.strftime("%Y%m"))
    if len(rows) < 6:                             # 月初不足 5 日均 → 補前月
        prev = (now.replace(day=1) - pd.Timedelta(days=1)).strftime("%Y%m")
        rows = _fetch_fmtqik(prev) + rows
    if rows:
        c.update({"date": _today_key(), "ts": now, "rows": rows})
    return rows

def mis_debug(codes=("2330", "2454", "3363", "6173")):
    """直接把 MIS 原始欄位傾印出來——『部分對部分錯』只能靠看原始回應定位。"""
    import requests
    chans = ["tse_t00.tw"]
    for c in codes:
        tk = next((t for t in core_universe if t.split(".")[0] == c), None)
        chans.append(f"otc_{c}.tw" if (tk or "").endswith(".TWO") else f"tse_{c}.tw")
    out = ["🔧 MIS 即時報價原始欄位", "=" * 24,
           f"時間 {_tw_now():%m/%d %H:%M}｜盤中={_is_market_hours()}"]
    try:
        r = requests.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                         params={"ex_ch": "|".join(chans), "json": "1", "delay": "0"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        j = r.json() or {}
        out.append(f"HTTP {r.status_code}｜rtcode {j.get('rtcode')}"
                   f"｜rtmessage {str(j.get('rtmessage'))[:40]}")
        arr = j.get("msgArray", []) or []
        out.append(f"要 {len(chans)} 檔，回 {len(arr)} 檔")
        for it in arr:
            px, src = _mis_price(it, allow_quote=_is_market_hours())
            out.append(f"\n▍{it.get('c')} {it.get('n', '')[:6]}")
            out.append(f"  z={it.get('z')} y={it.get('y')} o={it.get('o')} "
                       f"h={it.get('h')} l={it.get('l')} v={it.get('v')} tv={it.get('tv')}")
            out.append(f"  b={str(it.get('b'))[:24]} a={str(it.get('a'))[:24]}")
            out.append(f"  → 取價 {px}（來源 {src}）")
    except Exception as e:
        out.append(f"❌ {type(e).__name__}: {e}")
    st = _intraday_px.get("stat")
    if st:
        out.append(f"\n▍上次全量抓取：批次 {st.get('batches')}｜回 {st.get('returned')} 檔"
                   f"｜取價來源分布 {st.get('src')}")
        out.append(f"  rt {st.get('rt')}｜err {st.get('err', '無')}")
    return "\n".join(out)


def screener_debug():
    _ensure()
    out = ["🔧 選股資料診斷", "=" * 20]
    try:
        od = engines.get_taiex_daily()
        out.append(f"▍官方大盤(FMTQIK)最新: {od[0] if od else '—'}｜收 {od[1] if od else '—'}")
    except Exception as e:
        out.append(f"▍官方大盤取得失敗: {e}")
    try:
        closes = engines.get_official_closes()
        out.append(f"▍官方個股收盤表: {len(closes)} 檔（上市+上櫃合併）")
        for c in ("2330", "2317", "2454"):
            out.append(f" {c} 官方收盤: {closes.get(c, '—')}")
        out.append(" ── 上櫃(先前抓錯的) ──")
        for c in ("4971", "4991", "3363", "3163", "6182"):
            out.append(f" {c} 官方收盤: {closes.get(c, '—')}")
    except Exception as e:
        out.append(f"▍官方個股表失敗: {e}")
    out.append(f"▍_data_date()（顯示用）: {_data_date()}")
    bench = _cache.get("stats", {}).get(BENCH)
    out.append(f"▍大盤 stats.date: {bench.get('date') if bench else '—'}")
    for tk in (TSMC, "2317.TW", "2454.TW"):
        st = _cache.get("stats", {}).get(tk)
        if st:
            out.append(f" {tk}: 收 {st.get('last')}｜資料日 {st.get('date')}｜當日 "
                       f"{(st.get('r1') or 0)*100:+.1f}%")
    out.append("＊若『資料日』與官方最新日一致＝個股補丁生效；不一致＝Yahoo 延遲且補丁未命中")
    warm = _cache.get("ts")
    out.append(f"▍快取暖機時間: {warm.strftime('%m-%d %H:%M') if warm else '—'}"
               f"｜現在 {_tw_now().strftime('%m-%d %H:%M')}")
    tsmc_st = _cache.get("stats", {}).get(TSMC)
    today_str = _tw_now().strftime("%m-%d")
    if tsmc_st:
        is_today = tsmc_st.get("date") == today_str
        out.append(f"▍台積電快取K棒日={tsmc_st.get('date')}｜今天={today_str}｜"
                   + ("✅含今日(盤中價會進)" if is_today else "❌僅到昨日(Yahoo日K盤中未更新)"))
    now = _tw_now()
    hm = now.hour * 100 + now.minute
    out.append(" ── 時間源切換 ──")
    out.append(f"▍現在 {now.strftime('%H:%M')}（現貨09:00-13:30、期貨08:45-13:45）")
    phase = ("盤前" if hm < 900 else "盤中(MIS即時)" if hm <= 1345 else
             "剛收盤~官方EOD未出(13:45~約14:30 空窗)" if hm < 1430 else "盤後(官方EOD)")
    out.append(f"▍研判時段：{phase}")
    out.append(f"▍@量榜切換點：{'MIS即時' if 900 <= hm <= 1345 else 'EOD官方'}"
               f"｜快取重暖斷代線={_CUTOFF_HHMM//100:02d}:{_CUTOFF_HHMM%100:02d}")
    try:
        closes = engines.get_official_closes()
        c2330 = closes.get("2330")
        out.append(f"▍官方個股收盤 2330={c2330}（若=昨值→官方7/22未出、還在空窗）")
    except Exception as e:
        out.append(f"▍官方個股收盤查詢失敗：{e}")
    out.append(" ── 台積電量額覆蓋 ──")
    try:
        am = engines.get_official_amounts()
        a2330 = am.get("2330")
        out.append(f"▍get_official_amounts['2330'] = {a2330}"
                   + (f"（{a2330[1]/1000:.0f}張／{a2330[0]/1e8:.0f}億）" if a2330 and a2330[1] else "（無！）"))
        out.append(f"▍官方amounts筆數={len(am)}｜含2330={'2330' in am}")
    except Exception as e:
        out.append(f"▍get_official_amounts 失敗: {e}")
    tst = _cache.get("stats", {}).get(TSMC)
    if tst:
        v = tst.get("vol")
        at = tst.get("amt_today")
        out.append(f"▍快取台積電 vol={v}（{(v/1000):.0f}張）"
                   f"｜amt_today={(at/1e8):.0f}億" if v and at else f"▍快取台積電 vol={v}｜amt={tst.get('amt_today')}")
    out.append(f"▍after_close閘門(≥13:45)={_hhmm(_tw_now())>=1345}｜現在{_hhmm(_tw_now())}")
    return "\n".join(out)


def _fmt_amt(v):
    return f"{v/1e12:.2f}兆" if v >= 1e12 else f"{v/1e8:,.0f}億"

def _fetch_intraday_turnover():
    try:
        rk = engines._fetch_intraday_ranking_mis(top_n=999)
        if not rk:
            return None
        total = sum(amt for _c, _n, amt, *_ in rk if amt)
        return (total, len(rk)) if total > 0 else None
    except Exception:
        return None


def _is_market_hours():
    now = _tw_now()
    return (now.weekday() < 5 and
            (now.hour, now.minute) >= (9, 0) and (now.hour, now.minute) <= (13, 45))


def _turnover_line():
    rows = _turnover_rows()
    if len(rows) < 2:
        return None
    base = [v for _, v in rows[-6:-1]] if len(rows) >= 6 else [v for _, v in rows[:-1]]
    if not base:
        return None
    if _is_market_hours():
        est = _fetch_intraday_turnover()
        if est:
            total, ncov = est
            return ("成交金額", f"{_fmt_amt(total)}｜⏱盤中估", True)
        amt = rows[-1][1]
        return ("成交金額", f"{_fmt_amt(amt)}（昨日｜盤中即時暫無，收盤更新）", False)
    try:
        today = _data_date()  
        fmtqik_mmdd = None
        if rows:
            ds = str(rows[-1][0])
            if len(ds) == 8:
                fmtqik_mmdd = f"{ds[4:6]}-{ds[6:8]}"
        if (not _is_market_hours()) and fmtqik_mmdd and fmtqik_mmdd != today:
            am = engines.get_official_amounts()
            if am:
                mkt = sum(a for a, _v in am.values() if a)
                if mkt > 0:
                    return ("成交金額",
                            f"{_fmt_amt(mkt)}（今日收盤｜市場總額官方統計中，暫以個股加總）",
                            False)
    except Exception:
        pass
    amt, is_live = rows[-1][1], False
    dev = amt / (sum(base) / len(base)) - 1
    tag = ("🔥爆量" if dev >= 0.30 else "量增" if dev >= 0.10 else
           "量平" if dev > -0.10 else "量縮" if dev > -0.30 else "急凍")
    live_mark = "⏱盤中" if is_live else ""
    sep = "｜" if live_mark else ""
    return ("成交金額", f"{_fmt_amt(amt)}{sep}{live_mark}（5日{dev*100:+.0f}%｜{tag}）", is_live)


def _fmt_vol(shares):
    if shares is None:
        return ""
    zhang = shares / 1e3
    return f"量{zhang/1e4:.1f}萬張" if zhang >= 1e4 else f"量{zhang:,.0f}張"


# ── 引擎 C：盤勢結構儀 ───────────────────────────────────────────
def _ex_tsmc(idx_ret, tsmc_ret):
    if idx_ret is None or tsmc_ret is None:
        return None
    return (idx_ret - W_TSMC * tsmc_ret) / (1 - W_TSMC)

def build_market_structure():
    bench = _cache["stats"].get(BENCH)
    tsmc = _cache["stats"].get(TSMC)
    if not bench or not tsmc:
        return ["⚠️ 大盤或台積電資料缺漏，無法產生盤勢結構。"]
    x5 = _ex_tsmc(bench["r5"], tsmc["r5"])

    ok20 = ok23 = tot = 0
    roster20 = {}
    med = {"r1": [], "dd": [], "d20": [], "e23": []}
    for tk, meta in core_universe.items():
        st = _cache["stats"].get(tk)
        if not st:
            continue
        tot += 1
        ds, de = st.get("dsma", {}), st.get("dema", {})
        if ds.get(20, -1) >= 0:
            ok20 += 1
            roster20.setdefault(meta["sector"], []).append(meta["name"])
        if de.get(23, -1) >= 0:
            ok23 += 1
        for k, v in (("r1", st.get("r1")), ("dd", st.get("dd_52w")),
                     ("d20", ds.get(20)), ("e23", de.get(23))):
            if v is not None:
                med[k].append(v)
    md = {k: (float(np.median(v)) if v else None) for k, v in med.items()}

    # 📌 精準點數校準：直接用昨收價(prev_close)減算，拋棄從 r1 小數反推產生的誤差
    idx_last = bench.get("last")
    idx_prev = bench.get("prev_close")
    
    if idx_last is not None and idx_prev is not None and idx_prev > 0:
        idx_pts = idx_last - idx_prev
        r1i = idx_pts / idx_prev
        bench["r1"] = r1i   # 就地校正 r1
    else:
        idx_pts = None
        r1i = bench.get("r1")

    tsmc_last = tsmc.get("last")
    tsmc_prev = tsmc.get("prev_close")
    tp = None
    if tsmc_last is not None and tsmc_prev is not None and tsmc_prev > 0:
        tp = tsmc_last - tsmc_prev
        r1t = tp / tsmc_prev
        tsmc["r1"] = r1t    # 就地校正台積電 r1
        
        if idx_prev is not None:
            # 大盤昨收 × 台積權重 × 台積漲幅 ＝ 台積電貢獻的大盤點數
            tsmc_pts = idx_prev * W_TSMC * r1t
        else:
            tsmc_pts = None
    else:
        r1t = tsmc.get("r1")
        tsmc_pts = None
        if tsmc_last is not None and r1t is not None:
            tp = tsmc_last - tsmc_last / (1 + r1t)

    bds, bde = bench.get("dsma", {}), bench.get("dema", {})
    tds, tde = tsmc.get("dsma", {}), tsmc.get("dema", {})
    d = _data_date()

    t5, e5 = tsmc.get("r5"), x5
    if t5 is None or e5 is None:
        state5 = "資料不足"
    elif t5 < 0 and e5 < 0:
        state5 = ("🔻 全面回檔——台積電也開始補跌（最後一隻鞋），"
                  "此階段廣度何時止穩比指數位置更關鍵" if t5 < e5 else
                  "🔻 全面回檔——中小仍領跌，台積電相對抗跌")
    elif t5 >= 0 and e5 < 0:
        state5 = "🛡 台積撐盤——資金避風港效應，指數失真，個股體感遠比指數差"
    elif e5 >= 0 and t5 < 0:
        state5 = "🌱 中小回神、台積歇息——轉強雷達開始有參考價值"
    else:
        state5 = "🟢 普漲——台積電與中小同步走揚"

    t1, e1 = r1t, _ex_tsmc(r1i, r1t)
    if t1 is None or e1 is None:
        state1 = "資料不足"
    elif t1 < 0 and e1 < 0:
        state1 = ("🔻 今日普跌——台積領跌" if t1 < e1 else "🔻 今日普跌——中小領跌")
    elif t1 >= 0 and e1 < 0:
        state1 = "🛡 今日台積獨強、中小走弱——指數被權值撐住"
    elif e1 >= 0 and t1 < 0:
        state1 = "🌱 今日中小翻紅、台積休息"
    else:
        state1 = "🟢 今日普漲——權值與中小齊揚"

    body = [flex.text(f"🧭 盤勢結構儀 ({d})", size="md", weight="bold", color=flex.C_TITLE)]
    idx_line = (f"{idx_last:,.0f}（{idx_pts:+,.0f}點｜{_pct(r1i)}）"
                if idx_pts is not None else f"{idx_last:,.0f}（{_pct(r1i)}）")
    body += flex.kv_rows([("加權指數", idx_line, True)], value_flex=6)
    
    tv = _turnover_line()
    if tv:
        body += flex.kv_rows([(tv[0], tv[1], True)], value_flex=6)
    if tp is not None:
        tsmc_vol = tsmc.get("vol")
        t_amt = tsmc.get("amt_today")
        t_dev = tsmc.get("amt_dev")
        try:
            if _hhmm(_tw_now()) >= 1345:
                av = engines.get_official_amounts().get(TSMC.split(".")[0])
                if av and av[1]:
                    tsmc_vol = av[1]
                    t_amt = av[0] if av[0] else (tsmc["last"] * av[1])
        except Exception:
            pass
        vol_str = f"｜{_fmt_vol(tsmc_vol)}" if tsmc_vol else ""
        body += flex.kv_rows([("台積電",
                               f"{_px(tsmc['last'])}（{tp:+,.0f}元｜{_pct(r1t)}{vol_str}）",
                               True)], value_flex=6)
        if t_amt:
            if t_dev is not None:
                t_tag = ("🔥爆量" if t_dev >= 0.30 else "量增" if t_dev >= 0.10 else
                         "量平" if t_dev > -0.10 else "量縮" if t_dev > -0.30 else "急凍")
                amt_val = f"{_fmt_amt(t_amt)}（5日{t_dev*100:+.0f}%｜{t_tag}）"
            else:
                amt_val = _fmt_amt(t_amt)
            body += flex.kv_rows([("成交金額", amt_val, True)], value_flex=6)
    body.append(flex.sep())
    hdr, wid = ["", "當日", "回檔", "月線", "EMA23"], [3, 2, 2, 2, 2]
    aligns = ["start", "end", "end", "end", "end"]
    body.append(flex.row(hdr, wid, aligns, [flex.C_SUB]*5, size="xxs"))

    def _dd(v):
        return f"{v*100:.0f}%" if v is not None else "n/a"
    for i, (label, r1_, dd_, d20_, e23_) in enumerate([
            ("加權指數", r1i, bench.get("dd_52w"), bds.get(20), bde.get(23)),
            ("台積電", r1t, tsmc.get("dd_52w"), tds.get(20), tde.get(23)),
            ("市場體感", md["r1"], md["dd"], md["d20"], md["e23"])]):
        cells = [label, _pct(r1_), _dd(dd_), _pct(d20_), _pct(e23_)]
        body.append(flex.row(cells, wid, aligns,
                             [flex.C_HEAD] + [flex.val_color(c) for c in cells[1:]],
                             bg=flex.C_ZEBRA if i % 2 else None))
    body.append(flex.text(f"＊市場體感＝地圖{tot}檔中位數", size="xxs", color=flex.C_SUB))
    if idx_pts is not None and tsmc_pts is not None:
        others = idx_pts - tsmc_pts
        body.append(flex.text(f"📌 當日 {idx_pts:+,.0f} 點｜台積電貢獻 {tsmc_pts:+,.0f} 點"
                              f"｜其他 {others:+,.0f} 點", size="xs", wrap=True))
    body.append(flex.sep())
    body += flex.kv_rows([
        (f"📊 站上月線SMA20", f"{ok20}/{tot} 檔 ({ok20/tot*100:.0f}%)", False),
        ("  站上EMA23", f"{ok23}/{tot} 檔 ({ok23/tot*100:.0f}%)", False)])

    try:
        import engines as _e
        bal = _e.get_margin_balance()
        if bal:
            tw_b, tp_b, bdisp = bal
            total_b = tw_b + tp_b
            cap_per_pt = float(os.environ.get("TW_CAP_PER_PT", "30"))  
            cap_est = idx_last * cap_per_pt
            ratio = total_b / cap_est * 100
            body += flex.kv_rows([
                ("💰 融資餘額", f"{total_b:,.0f} 億", False),
                ("  佔估算市值", f"約 {ratio:.2f}%（泡沫參考）", False)])
            body.append(flex.text(f"＊市值以指數×{cap_per_pt:.0f}億/點估；ETF與槓桿商品未計",
                                  size="xxs", color=flex.C_SUB, wrap=True))
    except Exception:
        pass
    body.append(flex.sep())
    body.append(flex.text("狀態判讀", size="xs", weight="bold"))
    body.append(flex.text(f"▍當日：{state1}", size="xs", wrap=True))
    body.append(flex.text(f"▍近5日：{state5}", size="xs", wrap=True))
    
    if t1 is not None and t5 is not None:
        if t1 >= 0 > t5 or (e1 is not None and e5 is not None and e1 >= 0 > e5):
            body.append(flex.text("⚡ 當日翻紅但5日仍負——反彈初期，需連續2-3日確認才算轉勢",
                                  size="xxs", color=flex.C_SUB, wrap=True))
        elif t1 < 0 <= t5 or (e1 is not None and e5 is not None and e1 < 0 <= e5):
            body.append(flex.text("⚠️ 當日回落但5日仍正——漲多休息或轉弱起點，觀察廣度",
                                  size="xxs", color=flex.C_SUB, wrap=True))
    msg = flex.to_flex_message([flex.bubble(body)], f"盤勢結構儀 ({d})")

    body2 = [flex.text(f"📋 站上月線(SMA20)名單 ({ok20}/{tot})",
                       size="md", weight="bold", color=flex.C_TITLE),
             flex.sep()]
    if roster20:
        for zi, sector in enumerate(sorted(roster20)):
            body2.append(flex.row([f"▍{sector}", "、".join(roster20[sector])],
                                  [3, 5], ["start", "start"],
                                  [flex.C_SECT, flex.C_HEAD],
                                  bg=flex.C_ZEBRA if zi % 2 else None))
            body2[-1]["contents"][1]["wrap"] = True
    else:
        body2.append(flex.text("（目前全地圖無個股站上月線）", size="xs"))
    body2.append(flex.sep())
    body2.append(flex.text(f"其餘 {tot-ok20} 檔位於月線之下（@回檔 看明細）\n"
                           + LEGEND_SHORT + "\n" + DISCLAIMER,
                           size="xxs", color=flex.C_SUB, wrap=True))
    msg2 = flex.to_flex_message([flex.bubble(body2)], f"站上月線名單 {ok20}/{tot}")
    return [msg, msg2]


# ── 引擎 D：法人結構（今日法人要角的結構定位）────────────────────
def build_inst_structure(n_each=8):
    dd, lst = engines.get_power_list()
    if not lst:
        return ["⚠️ 目前無法取得法人個股資料。"]

    def side_vals(row):
        f_val = row[2] * 1000 * row[5] / 1e8
        t_val = row[3] * 1000 * row[5] / 1e8
        return f_val, t_val

    enriched = []
    for row in lst:
        f_val, t_val = side_vals(row)
        enriched.append((row[0], row[1], f_val, t_val))

    f_buy = sorted([e for e in enriched if e[2] > 0], key=lambda x: -x[2])[:n_each]
    t_buy = sorted([e for e in enriched if e[3] > 0], key=lambda x: -x[3])[:n_each]
    f_sell = sorted([e for e in enriched if e[2] < 0], key=lambda x: x[2])[:n_each]
    t_sell = sorted([e for e in enriched if e[3] < 0], key=lambda x: x[3])[:n_each]

    def merge(a, b, buy=True):
        seen, out = set(), []
        for e in a + b:
            if e[0] in seen:
                continue
            seen.add(e[0])
            out.append(e)
        out.sort(key=lambda x: -(x[2] + x[3]) if buy else (x[2] + x[3]))
        return out

    buys = merge(f_buy, t_buy, buy=True)
    sells = merge(f_sell, t_sell, buy=False)
    stats = get_stats_for_codes([e[0] for e in buys + sells])

    def fmt(entries, title, emoji, note=None):
        trows = []
        for code, name, f_val, t_val in entries:
            st = stats.get(code)
            if st:
                ds = st.get("dsma", {})
                cells = [f"{code} {name}", f"外{f_val:+.1f}/投{t_val:+.1f}億",
                         _pct(st.get("r1")), f"{st['dd_52w']*100:.0f}%"]
                sub = f"月線{_pct(ds.get(20))}｜季線{_pct(ds.get(60))}"
            else:
                cells = [f"{code} {name}", f"外{f_val:+.1f}/投{t_val:+.1f}億", "n/a", "n/a"]
                sub = "（價格歷史不足，無結構資料）"
            trows.append({"cells": cells, "sub": sub})
        bubbles = flex.flex_table(
            f"{emoji} {title} ({dd})", ["名稱", "金額", "當日", "回檔"],
            [9, 12, 4, 3], trows, subtitle="＊入選＝外資或投信金額買賣超要角",
            aligns=["start", "start", "end", "end"],
            color_cols=(1, 2, 3), rows_per_bubble=20, note=note)
        return flex.to_flex_message(bubbles, f"{title} ({dd})")

    return [fmt(buys, "法人買超要角・結構定位", "🟢"),
            fmt(sells, "法人賣超要角・結構定位", "🔴",
                note=LEGEND_SHORT + "\n" + DISCLAIMER)]


# ── 引擎 F：@量榜 成交金額 Top50（爆量榜＋個股體質二合一）────────
def build_volume_ranking(top_n=50):
    import engines
    disp, ranked, is_live = engines.get_amount_ranking(top_n=top_n)
    if not ranked:
        return ["⚠️ 目前無法取得成交金額排行（證交所/櫃買來源異常）。"]
    stats = get_stats_for_codes([c for c, *_ in ranked])
    trows = []
    for rank, (code, name, amt, close, chg, is_otc) in enumerate(ranked, 1):
        amt_e = amt / 1e8                                   
        amt_s = f"{amt_e:,.0f}" if amt_e >= 100 else f"{amt_e:.1f}"
        tag = "櫃" if is_otc else ""
        st = stats.get(code)
        if st:
            ds, de = st.get("dsma", {}), st.get("dema", {})
            asma = "/".join(str(a) for a in st.get("above_sma", [])) or "無"
            sub = (f"今年高{_pct(st.get('ytd_hi'),0)}→現{_pct(st.get('ytd'),0)}｜"
                   f"回檔{st['dd_52w']*100:.0f}%｜月線{_pct(ds.get(20))}｜"
                   f"季線{_pct(ds.get(60))}｜EMA23{_pct(de.get(23))}｜站上SMA:{asma}")
        else:
            sub = "（近況資料不足）"
        trows.append({"cells": [f"{rank}.{name}({code}){tag}", amt_s,
                                _px(close), _pct(chg) if chg is not None else "—"],
                      "sub": sub})
    live_tag = "⏱盤中即時" if is_live else "收盤"
    header_col = "現價" if is_live else "收盤"
    scope = ("盤中＝地圖股即時排行（MIS 即時報價，全市場即時排行無單次源）"
             if is_live else "上市＋上櫃全市場合併排行（證交所/櫃買個股日成交金額，不含ETF）")
    bubbles = flex.flex_table(
        f"🔥 成交金額 Top{len(ranked)}（{live_tag}｜{disp or _data_date()}）",
        ["名稱", "金額(億)", header_col, "當日"], [5, 2, 2, 2],
        trows, color_cols=(3,), rows_per_bubble=17,
        subtitle=scope + "｜sub列＝體質近況（口徑同 @回檔/@轉強）",
        note=("💡 盤中金額為即時累計、會隨盤跳動；收盤後同指令自動切全市場定版\n"
              if is_live else "💡 爆量處通常是多空決戰位；搭配回檔深度與均線位置判讀\n")
             + DISCLAIMER)
    return flex.to_stacked_messages(bubbles, f"成交金額 Top{len(ranked)}")