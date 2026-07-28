# -*- coding: utf-8 -*-
# ==============================================================================
# options.py — @期權籌碼：台指期選盤後籌碼五表（OData 突破 ＋ 嚴格精準版）
#
# 升級特點：
#   1. 內建 OData 隱藏端點突破：強制嘗試抓取歷史資料，抵禦 API 單日限制。
#   2. 恢復快照資料庫，配合不休眠策略解決增減計算問題。
#   3. 解除死鎖陷阱：14:30 法人資料一出即刻更新前四表，不被延遲的 OI 拖累。
#   4. 散戶比嚴守精準度：若全市場 OI 未公布，絕不拿昨日分母混充。
# ==============================================================================
import json
import os
import gc
import time
import datetime as dt
import requests
import flex

BASE = "https://openapi.taifex.com.tw/v1"
_HEADERS = {"User-Agent": "Mozilla/5.0 (GEA-bot)", "Accept": "application/json"}
SNAP_FILE = "optchips_snap.json"

# 各資料集
DS_FUT_GEN  = "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
DS_OPT_CP   = "MarketDataOfMajorInstitutionalTradersDetailsOfCallsAndPutsBytheDate"
DS_LARGE    = "OpenInterestOfLargeTradersFutures"
DS_LARGE_OPT = "OpenInterestOfLargeTradersOptions"   
DS_FUT_MKT  = "DailyMarketReportFut"   
DS_PCR      = "PutCallRatio"
DS_OPT_MKT  = "DailyMarketReportOpt"

KW_TX  = ("臺股期貨", "台股期貨")
KW_MXF = ("小型臺指", "小型台指")
KW_TMF = ("微型臺指", "微型台指")
KW_TXO = ("臺指選擇權", "台指選擇權")

def _n(s, default=None):
    try:
        t = str(s).replace(",", "").replace("%", "").strip()
        if t in ("", "-", "—", "None"): return default
        return float(t)
    except Exception:
        return default

def _i(s, default=None):
    v = _n(s, None)
    return int(v) if v is not None else default

def _fetch(name, timeout=25):
    # 嘗試使用 OData 抓取歷史資料 (期交所部分隱藏端點支援此協定)
    try:
        odata_url = f"{BASE}/OData/{name}?$top=15&$orderby=Date%20desc"
        r = requests.get(odata_url, headers=_HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            res = data.get("value") if isinstance(data, dict) else data
            if isinstance(res, list) and len(res) > 1:
                return res
    except Exception:
        pass

    # 若 OData 不支援，退回標準 API (僅回傳最新1天資料)
    r = requests.get(f"{BASE}/{name}", headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list): raise RuntimeError(f"{name} 非預期格式")
    return data

def _latest_date(rows, key="Date"):
    ds = [r.get(key, "") for r in rows if r.get(key)]
    return max(ds) if ds else ""

def _only_latest(rows, key="Date"):
    d = _latest_date(rows, key)
    return d, [r for r in rows if r.get(key) == d]


# ── 一致性鎖（Evans 定調：混合抓有風險，我要一致性，慢沒關係）────────────
# 期交所同類資料不同端點更新速度不一（總表快、明細慢，實測可差一天以上）。
# 取「各端點各自最新日」的最小值當共同資料日：某端點超前就先不用它的新資料，
# 等大家追上再一起跳。避免同一張卡片上不同區塊是不同日期的數字。
# 五個源現在都走主站同日資料（fut_mkt 走 futDataDown CSV），鎖回原本的五鍵設計。
# pcr 不入鎖：它是獨立一張卡、且本來就是多日序列（今日/昨日對照）。
_LOCK_KEYS = ("fut_inst", "opt_cp", "large", "large_opt", "fut_mkt")


def _common_lock_date(b):
    ds = []
    for k in _LOCK_KEYS:
        d = _latest_date(b.get(k) or [])
        if d:
            ds.append(d)
    return min(ds) if ds else ""


def _rows_on(rows, d):
    return [r for r in (rows or []) if r.get("Date") == d]

def _has(text_, kws):
    t = str(text_ or "")
    return any(k in t for k in kws)

def _role(item):
    t = str(item or "")
    if "投信" in t: return "trust"
    if "自營" in t: return "dealer"
    if "外資" in t: return "foreign"
    return None

ROLE_LABEL = {"foreign": "外資", "trust": "投信", "dealer": "自營商"}

def _fmt_i(v, signed=True):
    if v is None: return "—"
    return f"{v:+,.0f}" if signed else f"{v:,.0f}"

def _fmt_diff(cur, prev):
    if cur is None or prev is None: return "—"
    return f"{cur - prev:+,.0f}"

def _mmdd(date_str):
    s = str(date_str).replace("-", "").replace("/", "")
    if len(s) == 8:
        return f"{s[4:6]}/{s[6:8]}"
    return str(date_str)

def _row_oi(r):
    return {"net": _i(r.get("OpenInterest(Net)")), "long": _i(r.get("OpenInterest(Long)")), "short": _i(r.get("OpenInterest(Short)"))}

def _parse_fut_inst(rows, gen_rows=None):
    _, rs = _only_latest(rows) if rows else ("", [])
    out = {}
    for r in rs:
        cc = r.get("ContractCode", "")
        key = ("TX" if _has(cc, KW_TX) else "MXF" if _has(cc, KW_MXF) else "TMF" if _has(cc, KW_TMF) else None)
        role = _role(r.get("Item"))
        if key and role: out.setdefault(key, {})[role] = _row_oi(r)
    return out

def _pick_allmonth(rows_of_contract):
    pri = [r for r in rows_of_contract if _has(r.get("SettlementMonth"), ("所有", "全部", "999"))]
    pool = pri or rows_of_contract
    return max(pool, key=lambda r: _n(r.get("OIOfMarket"), -1) or -1) if pool else None

def _is_spec(item):
    t = str(item or "").strip()
    return ("特定" in t) or (t == "1")

def _parse_large(rows):
    _, rs = _only_latest(rows)
    def _name(r): return str(r.get("ContractName") or r.get("Contract") or "")
    def _grp(key):
        if key == "TX": return [r for r in rs if _has(_name(r), KW_TX) and not _has(_name(r), KW_MXF + KW_TMF + ("小型", "微型"))]
        return [r for r in rs if _has(_name(r), KW_MXF if key == "MXF" else KW_TMF)]

    out = {}
    tx = _grp("TX")
    d = {}
    ra = _pick_allmonth([r for r in tx if not _is_spec(r.get("TypeOfTraders"))])
    if ra:
        b, s = _i(ra.get("Top10Buy")), _i(ra.get("Top10Sell"))
        d["top10_all"] = (b - s) if (b is not None and s is not None) else None
    rp = _pick_allmonth([r for r in tx if _is_spec(r.get("TypeOfTraders"))])
    if rp:
        b, s = _i(rp.get("Top10Buy")), _i(rp.get("Top10Sell"))
        d["top10_spec"] = (b - s) if (b is not None and s is not None) else None
    out["TX"] = d
    return out

def _parse_opt_cp(rows):
    _, rs = _only_latest(rows)
    out = {"call": {}, "put": {}}
    for r in rs:
        if not _has(r.get("ContractCode"), KW_TXO + ("TXO",)): continue
        cp = str(r.get("CallPut", ""))
        side = "call" if ("買" in cp or "CALL" in cp.upper()) else "put" if ("賣" in cp or "PUT" in cp.upper()) else None
        role = _role(r.get("Item"))
        if side and role: out[side][role] = _i(r.get("OpenInterest(Net)"))
    return out

def _parse_pcr(rows):
    uniq = {}
    for r in rows:
        d = r.get("Date", "")
        if d: uniq[d] = {"date": d, "vol": _n(r.get("PutCallVolumeRatio%")), "oi": _n(r.get("PutCallOIRatio%"))}
    return [uniq[d] for d in sorted(uniq, reverse=True)]

def _parse_market_oi(rows):
    _, rs = _only_latest(rows) if rows else ("", [])
    codes = {"TX": ("TX", "TXF"), "MXF": ("MTX", "MXF"), "TMF": ("TMF", "TM")}
    per = {}
    for r in rs:
        c = str(r.get("Contract", "")).strip().upper()
        key = next((k for k, cs in codes.items() if c in cs), None)
        if not key: continue
        mon = str(r.get("ContractMonth(Week)", "")).strip()
        oi = _i(r.get("OpenInterest"), 0) or 0
        kk = (key, mon)
        per[kk] = max(per.get(kk, 0), oi)
    out = {}
    for (key, _mon), oi in per.items(): out[key] = out.get(key, 0) + oi
    return {k: v for k, v in out.items() if v > 0}

def _parse_large_opt(rows):
    _, rs = _only_latest(rows) if rows else ("", [])
    out = {"call": {}, "put": {}}
    def _name(r): return str(r.get("ContractName") or r.get("Contract") or "")
    txo = [r for r in rs if _has(_name(r), KW_TXO) or _has(r.get("Contract"), ("TXO",))]
    for side, key in (("買", "call"), ("賣", "put"), ("CALL", "call"), ("PUT", "put")):
        grp = [r for r in txo if side in str(r.get("CallPut", "")).upper() or side in str(r.get("CallPut", ""))]
        if not grp: continue
        allr = _pick_allmonth([r for r in grp if not _is_spec(r.get("TypeOfTraders"))])
        sper = _pick_allmonth([r for r in grp if _is_spec(r.get("TypeOfTraders"))])
        if allr:
            bb, ss = _i(allr.get("Top10Buy")), _i(allr.get("Top10Sell"))
            if bb is not None and ss is not None: out[key]["top10_all"] = bb - ss
        if sper:
            bb, ss = _i(sper.get("Top10Buy")), _i(sper.get("Top10Sell"))
            if bb is not None and ss is not None: out[key]["top10_spec"] = bb - ss
    return out

def _retail(fut_inst, market_oi, key):
    inst = fut_inst.get(key) or {}
    oi = market_oi.get(key)
    if not oi or len(inst) < 3: return None
    il = sum(v["long"] for v in inst.values() if v.get("long") is not None)
    ish = sum(v["short"] for v in inst.values() if v.get("short") is not None)
    net = (oi - il) - (oi - ish)
    return (net / oi * 100.0, net, oi)

# ── 迷你資料庫：快照系統 ──
def _load_snap():
    if os.path.exists(SNAP_FILE):
        try:
            with open(SNAP_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def _save_snap(data):
    try:
        keys = sorted(data.keys())[-15:] # 保留 15 天歷史
        data = {k: data[k] for k in keys}
        with open(SNAP_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
    except Exception: pass

def _update_snapshot(lock, fut_inst, opt_cp, large, large_opt, retail_m, retail_t):
    if not lock: return {}
    snap = _load_snap()
    if lock not in snap:
        snap[lock] = {"fut": {}, "opt": {"call": {}, "put": {}}, "large": {}, "large_opt": {"call": {}, "put": {}}, "retail": {}}
    
    s = snap[lock]
    for role in ("foreign", "trust", "dealer"):
        v = (fut_inst.get("TX") or {}).get(role, {}).get("net")
        if v is not None: s["fut"][role] = v
        
    for side in ("call", "put"):
        for role in ("foreign", "trust", "dealer"):
            v = opt_cp.get(side, {}).get(role)
            if v is not None: s["opt"][side][role] = v
        for k in ("top10_all", "top10_spec"):
            v = large_opt.get(side, {}).get(k)
            if v is not None: s["large_opt"][side][k] = v
            
    for k in ("top10_all", "top10_spec"):
        v = (large.get("TX") or {}).get(k)
        if v is not None: s["large"][k] = v
        
    if retail_m is not None: s["retail"]["MXF"] = retail_m[0]
    if retail_t is not None: s["retail"]["TMF"] = retail_t[0]
    
    _save_snap(snap)
    return snap

# ── 資料打包與排版 ──
_raw_cache = {"ts": 0.0, "bundle": None}

def _get_bundle(force=False):
    if not force and _raw_cache["bundle"] and time.time() - _raw_cache["ts"] < 600:
        return _raw_cache["bundle"]
    b = {"errors": {}}
    for name, key in ((DS_FUT_GEN, "fut_inst"), (DS_LARGE, "large"), (DS_LARGE_OPT, "large_opt"),
                      (DS_FUT_MKT, "fut_mkt"), (DS_OPT_CP, "opt_cp"), (DS_PCR, "pcr")):
        try:
            b[key] = _fetch(name)
        except Exception as e:
            b[key] = []
            b["errors"][key] = str(e)
            
    try: 
        raw = _fetch(DS_OPT_MKT, timeout=40)
        b["support"] = _parse_support(raw)
        del raw
        gc.collect()
    except Exception as e:
        b["support"] = {}
        b["errors"]["support"] = str(e)
        
    # ── 主站同日資料覆蓋（OpenAPI 慢一個交易日，見 taifex_web.py）──
    # 只覆蓋主站確定拿得到同日的四個源；fut_mkt/pcr 仍走 OpenAPI（T-1），
    # 由 _common_lock_date 排除它們，各自標自己的資料日。
    b["web_date"] = ""
    try:
        import taifex_web
        wd, wrows = taifex_web.fetch_bundle()
        if wd and wrows.get("fut_inst"):
            for k, rows in wrows.items():
                if rows:
                    b[k] = rows
            b["web_date"] = wd
        # P/C 比主站只有 HTML（pcRatioDown 是空的），單獨抓
        try:
            pr = taifex_web.fetch_pcr()
            if pr:
                b["pcr"] = pr
        except Exception as e:
            b["errors"]["taifex_web_pcr"] = str(e)
    except Exception as e:
        b["errors"]["taifex_web"] = str(e)

    _raw_cache.update({"ts": time.time(), "bundle": b})
    return b

def _parse_support(rows, topn=6):
    _, rs = _only_latest(rows)
    per = {}
    cms = set()
    for r in rs:
        if not (_has(r.get("Contract"), ("TXO",)) or _has(r.get("Contract"), KW_TXO)): continue
        cm = str(r.get("ContractMonth(Week)", "")).strip()
        if not cm: continue
        cp = str(r.get("CallPut", ""))
        side = "call" if ("買" in cp or "CALL" in cp.upper()) else "put" if ("賣" in cp or "PUT" in cp.upper()) else None
        k = _n(r.get("StrikePrice"))
        oi = _i(r.get("OpenInterest"), 0)
        if side is None or k is None: continue
        cms.add(cm)
        kk = (cm, side, int(k))
        per[kk] = max(per.get(kk, 0), oi or 0)
    weeks  = sorted(c for c in cms if "W" in c.upper())
    months = sorted(c for c in cms if "W" not in c.upper() and c.isdigit())
    out = {}
    for tag, pool in (("week", weeks), ("month", months)):
        if not pool: continue
        cm = pool[0]
        calls = {k[2]: v for k, v in per.items() if k[0] == cm and k[1] == "call" and v > 0}
        puts  = {k[2]: v for k, v in per.items() if k[0] == cm and k[1] == "put" and v > 0}
        top_c = sorted(calls, key=lambda s: -calls[s])[:topn]
        top_p = sorted(puts,  key=lambda s: -puts[s])[:topn]
        strikes = sorted(set(top_c) | set(top_p), reverse=True)
        ladder = [(s, calls.get(s, 0), puts.get(s, 0)) for s in strikes]
        cmax = max((calls[s] for s in top_c), default=0)
        pmax = max((puts[s] for s in top_p), default=0)
        out[tag] = (cm, ladder, cmax, pmax)
    return out

def _bub_fail(title, err):
    return flex.bubble([flex.text(title, size="md", weight="bold", color=flex.C_TITLE),
                        flex.text(f"⚠️ 解析失敗：{err}", size="xs", color=flex.C_SUB, wrap=True)])

_C_CALL, _C_PUT = "#C0392B", "#1A9E4B"
def _bar_cell(oi, vmax, color, side):
    frac = 0 if not vmax else max(0, min(1.0, oi / vmax))
    fill = max(1, int(round(frac * 100)))
    gap = max(1, 100 - fill)
    barbox = {"type": "box", "layout": "horizontal", "height": "16px", "contents": []}
    solid = {"type": "box", "layout": "vertical", "flex": fill, "backgroundColor": color, "cornerRadius": "2px", "contents": [{"type": "filler"}]}
    space = {"type": "box", "layout": "vertical", "flex": gap, "contents": [{"type": "filler"}]}
    barbox["contents"] = ([space, solid] if side == "left" else [solid, space])
    return barbox

def _support_bubble_merged(sections, disp):
    body = [flex.text(f"🧱 選擇權支撐壓力 ({disp})", size="md", weight="bold", color=flex.C_TITLE),
            flex.text("柱長＝未平倉口數｜履約價由高到低", size="xxs", color=flex.C_SUB, wrap=True), flex.sep()]
    for i, (lab, cm, ladder, cmax, pmax) in enumerate(sections):
        if i > 0: body.append(flex.sep())
        c_star = max((c for _s, c, _p in ladder), default=0)
        p_star = max((p for _s, _c, p in ladder), default=0)
        body.append(flex.text(f"🧱 {lab} {cm}", size="sm", weight="bold", color=flex.C_TITLE))
        body.append({"type": "box", "layout": "horizontal", "contents": [
            flex.text("支撐 Put", flex=5, size="xxs", color=_C_PUT, align="start", weight="bold"),
            flex.text("履約價", flex=3, size="xxs", color=flex.C_SUB, align="center", weight="bold"),
            flex.text("Call 壓力", flex=5, size="xxs", color=_C_CALL, align="end", weight="bold")]})
        for s, c, p in ladder:
            p_lab = (("★" if p == p_star and p > 0 else "") + (f"{p:,}" if p else "·"))
            c_lab = (f"{c:,}" if c else "·") + ("★" if c == c_star and c > 0 else "")
            body.append({"type": "box", "layout": "horizontal", "alignItems": "center", "paddingTop": "1px", "paddingBottom": "1px", "contents": [
                flex.text(p_lab, flex=3, size="xxs", color=(_C_PUT if p else flex.C_SUB), align="start"),
                {"type": "box", "layout": "vertical", "flex": 4, "contents": [_bar_cell(p, pmax, _C_PUT, "left")]},
                flex.text(f"{s}", flex=3, size="xs", color=flex.C_HEAD, align="center", weight="bold"),
                {"type": "box", "layout": "vertical", "flex": 4, "contents": [_bar_cell(c, cmax, _C_CALL, "right")]},
                flex.text(c_lab, flex=3, size="xxs", color=(_C_CALL if c else flex.C_SUB), align="end")]})
    body.append(flex.sep())
    body.append(flex.text("★＝該邊最大未平倉｜Call 大＝上方壓力、Put 大＝下方支撐", size="xxs", color=flex.C_SUB, wrap=True))
    return flex.bubble(body)

def _retail_bar_row(label, cur, pv_r, hist_series):
    if not cur:
        return {"type": "box", "layout": "horizontal", "contents": [
            flex.text(label, flex=3, size="sm", weight="bold", color=flex.C_HEAD),
            flex.text("資料缺漏", flex=7, size="xs", color=flex.C_SUB)]}
    ratio, net, oi = cur
    color = "#1A9E4B" if ratio >= 0 else "#C0392B"
    stance = "散戶偏多" if ratio >= 0 else "散戶偏空"
    pp = f"（前日 {ratio - pv_r:+.1f}pp）" if pv_r is not None else ""
    head = {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
                flex.text(label, flex=2, size="sm", weight="bold", color=flex.C_HEAD),
                flex.text(f"{ratio:+.1f}%", flex=3, size="lg", weight="bold", color=color, align="center"),
                flex.text(stance, flex=3, size="xs", color=color, align="end")]}
    out = [head]
    if hist_series and len(hist_series) >= 2:
        # 走勢改成「橫柱、中軸左右發散」——與 @期權籌碼 支撐壓力那張同一套畫法
        # （flex 比例 + backgroundColor），那套在 LINE 上實測畫得出來。
        # 先前的直式柱用 height px + width% + justifyContent，LINE 渲染不出來 → 整片空白。
        hmax = max((abs(v) for _, v in hist_series), default=1) or 1
        out.append({"type": "box", "layout": "horizontal", "paddingTop": "4px", "contents": [
            flex.text("日期", flex=3, size="xxs", color=flex.C_SUB, align="start"),
            flex.text("偏空", flex=5, size="xxs", color=_C_CALL, align="center"),
            flex.text("偏多", flex=5, size="xxs", color=_C_PUT, align="center"),
            flex.text("比例", flex=4, size="xxs", color=flex.C_SUB, align="end")]})
        for d_str, v in hist_series:
            col = _C_PUT if v >= 0 else _C_CALL
            frac = max(0.0, min(1.0, abs(v) / hmax))
            fill = max(1, int(round(frac * 100)))
            gap = max(1, 100 - fill)
            solid = {"type": "box", "layout": "vertical", "flex": fill, "backgroundColor": col,
                     "cornerRadius": "2px", "contents": [{"type": "filler"}]}
            space = {"type": "box", "layout": "vertical", "flex": gap, "contents": [{"type": "filler"}]}
            blank = {"type": "box", "layout": "vertical", "flex": 1, "contents": [{"type": "filler"}]}
            left = {"type": "box", "layout": "horizontal", "flex": 5, "height": "12px",
                    "contents": ([space, solid] if v < 0 else [blank])}
            right = {"type": "box", "layout": "horizontal", "flex": 5, "height": "12px",
                     "contents": ([solid, space] if v >= 0 else [blank])}
            out.append({"type": "box", "layout": "horizontal", "alignItems": "center",
                        "paddingTop": "1px", "paddingBottom": "1px", "contents": [
                flex.text(d_str, flex=3, size="xxs", color=flex.C_SUB, align="start"),
                left, right,
                flex.text(f"{v:+.1f}%", flex=4, size="xxs", color=col, align="end")]})
    else:
        out.append(flex.text("（走勢資料累積中）", size="xxs", color=flex.C_SUB, align="center"))
    out.append(flex.text(f"散戶淨 {net:+,} 口／市場未平倉 {oi:,} 口{('｜'+pp) if pp else ''}", size="xxs", color=flex.C_SUB, wrap=True))
    return {"type": "box", "layout": "vertical", "paddingTop": "4px", "paddingBottom": "4px", "contents": out}

def get_option_chips():
    b = _get_bundle()
    
    # 1. 鎖定主日期＝各端點最新日的「最小值」（一致性鎖，見 _common_lock_date）
    lock = _common_lock_date(b)
    _newest = max([_latest_date(b.get(k) or []) for k in _LOCK_KEYS] + [""])
    _lagging = bool(lock and _newest and _newest > lock)
    if not lock: return [flex.to_flex_message([_bub_fail("期權籌碼", "無法取得期交所資料日")], "期權籌碼")]

    # 2. 解析當日一般資料（全部鎖到同一天）
    fut_inst = _parse_fut_inst(_rows_on(b.get("fut_inst"), lock), b.get("fut_gen"))
    opt_cp   = _parse_opt_cp(_rows_on(b.get("opt_cp"), lock))
    large    = _parse_large(_rows_on(b.get("large"), lock))
    large_opt = _parse_large_opt(_rows_on(b.get("large_opt"), lock))
    
    # 3. 處理散戶比 (嚴格檢查全市場 OI 是否出爐)
    fm_date = _latest_date(b.get("fut_mkt") or [])
    retail_date = lock if fm_date >= lock else ""
    retail_m = retail_t = None
    if retail_date:
        market_oi = _parse_market_oi(_rows_on(b.get("fut_mkt"), lock))
        retail_m = _retail(fut_inst, market_oi, "MXF")
        retail_t = _retail(fut_inst, market_oi, "TMF")

    # 4. 更新快照 (補齊前日資料以算增減)
    # 主站端點吃日期區間，payload 本來就含多日 → 把 lock 之前的每一天也灌進快照。
    # 這樣「增減」和「散戶多空比走勢」不再依賴落地檔（Render 免費層每次部署/
    # 休眠都會清掉檔案系統，那條路永遠累積不起來）。
    for _d in sorted({r.get("Date") for r in (b.get("fut_inst") or []) if r.get("Date")}):
        if _d >= lock:
            continue
        _fi = _parse_fut_inst(_rows_on(b.get("fut_inst"), _d))
        if not _fi:
            continue
        _moi = _parse_market_oi(_rows_on(b.get("fut_mkt"), _d))
        _update_snapshot(_d, _fi,
                         _parse_opt_cp(_rows_on(b.get("opt_cp"), _d)),
                         _parse_large(_rows_on(b.get("large"), _d)),
                         _parse_large_opt(_rows_on(b.get("large_opt"), _d)),
                         _retail(_fi, _moi, "MXF"), _retail(_fi, _moi, "TMF"))

    snap = _update_snapshot(lock, fut_inst, opt_cp, large, large_opt, retail_m, retail_t)
    prevs = [d for d in snap.keys() if d < lock]
    prev_date = max(prevs) if prevs else ""
    pv = snap.get(prev_date, {"fut": {}, "opt": {"call": {}, "put": {}}, "large": {}, "large_opt": {"call": {}, "put": {}}, "retail": {}})
    
    # 取出歷史散戶比用於畫圖
    hist_mxf, hist_tmf = [], []
    for d in sorted(snap.keys()):
        rm = snap[d].get("retail", {}).get("MXF")
        rt = snap[d].get("retail", {}).get("TMF")
        if rm is not None: hist_mxf.append((_mmdd(d), rm))
        if rt is not None: hist_tmf.append((_mmdd(d), rt))
    hist = {"MXF": hist_mxf[-10:], "TMF": hist_tmf[-10:]}

    disp = _mmdd(lock) + ("（明細更新中）" if _lagging else "")
    diff_note = f"增減＝與 {_mmdd(prev_date)} 相比" if prev_date else "增減＝無前日資料"
    bubbles = []

    # ── ① 台指期籌碼 ──
    try:
        if not fut_inst.get("TX"): raise RuntimeError("查無臺股期貨列")
        rows = ["三大法人（台指期未平倉）"]
        for role in ("foreign", "trust", "dealer"):
            v = (fut_inst["TX"].get(role) or {}).get("net")
            rows.append([ROLE_LABEL[role], _fmt_i(v), _fmt_diff(v, pv.get("fut", {}).get(role))])
        bubbles += flex.flex_table(f"🏦 台指期貨籌碼 ({disp})", ["身份", "淨部位", "增減"], [4, 3, 3],
            rows, color_cols=(1, 2), rows_per_bubble=99, subtitle="單位：口｜淨部位＝多方OI−空方OI（正＝淨多單）", note=diff_note)
    except Exception as e: bubbles.append(_bub_fail("🏦 台指期貨", e))

    # ── ② 選擇權三大法人 ──
    try:
        if not (opt_cp["call"] or opt_cp["put"]): raise RuntimeError("查無臺指選擇權列")
        rows = []
        for side, lab in (("call", "買權 CALL"), ("put", "賣權 PUT")):
            rows.append(lab)
            for role in ("foreign", "trust", "dealer"):
                v = opt_cp[side].get(role)
                rows.append([ROLE_LABEL[role], _fmt_i(v), _fmt_diff(v, pv.get("opt", {}).get(side, {}).get(role))])
            lo, pv_lo = large_opt.get(side, {}), pv.get("large_opt", {}).get(side, {})
            for llab, lk in ((" 十大交易人", "top10_all"), (" 十大特定法人", "top10_spec")):
                if lk in lo: rows.append([llab, _fmt_i(lo[lk]), _fmt_diff(lo[lk], pv_lo.get(lk))])
        bubbles += flex.flex_table(f"🎯 選擇權 法人淨部位 ({disp})", ["身份", "淨部位", "增減"], [4, 3, 3],
            rows, color_cols=(1, 2), rows_per_bubble=99, subtitle="單位：口｜淨部位＝買方OI−賣方OI", note=diff_note)
    except Exception as e: bubbles.append(_bub_fail("🎯 選擇權淨部位", e))

    # ── ③ Put/Call 比 ──
    try:
        pcr = _parse_pcr(b["pcr"]) if b["pcr"] else []
        if not pcr: raise RuntimeError("無PCR資料")
        rows = [[_mmdd(r["date"]), f"{r['vol']:.2f}%" if r["vol"] is not None else "—", f"{r['oi']:.2f}%" if r["oi"] is not None else "—"] for r in pcr[:5]]
        bubbles += flex.flex_table(f"⚖️ Put/Call 比 ({disp})", ["日期", "成交量比", "未平倉比"], [3, 3, 3],
            rows, rows_per_bubble=99, subtitle="P/C＝賣權÷買權｜未平倉比>100%＝下方支撐", note="近 5 個交易日，新→舊")
    except Exception as e: bubbles.append(_bub_fail("⚖️ Put/Call 比", e))

    # ── ④ 支撐壓力 ──
    try:
        support = b.get("support") or {}
        if not support: raise RuntimeError("查無 TXO 行情")
        sections = []
        for tag, lab in (("week", "週選"), ("month", "月選")):
            if tag in support: sections.append((lab,) + support[tag])
        bubbles.append(_support_bubble_merged(sections, disp))
    except Exception as e: bubbles.append(_bub_fail("🧱 支撐壓力", e))

    # ── ⑤ 散戶多空比 ──
    try:
        r_disp = disp if retail_date else f"{disp} (今日 OI 尚未公布)"
        r_body = [flex.text(f"🐑 散戶多空比 ({r_disp})", size="md", weight="bold", color=flex.C_TITLE),
                  flex.text("柱狀＝逐日走勢，中軸上=偏多(綠)、下=偏空(紅)", size="xxs", color=flex.C_SUB, wrap=True), flex.sep()]
        r_body.append(_retail_bar_row("小台", retail_m, pv.get("retail", {}).get("MXF"), hist.get("MXF")))
        r_body.append(flex.sep())
        r_body.append(_retail_bar_row("微台", retail_t, pv.get("retail", {}).get("TMF"), hist.get("TMF")))
        r_body.append(flex.sep())
        r_body.append(flex.text("⚠️ 推估值僅供參考｜" + diff_note, size="xxs", color=flex.C_SUB, wrap=True))
        bubbles.append(flex.bubble(r_body))
    except Exception as e: bubbles.append(_bub_fail("🐑 散戶多空比", e))

    return flex.to_stacked_messages(bubbles, f"期權籌碼 {disp}")

def record_snapshot(): pass

def debug_dump():
    b = _get_bundle(force=True)
    out = ["🔧 期權籌碼 [深度除錯報告]", "=" * 24]
    
    # 1. 檢查 API 到底給了幾天的資料？
    fut_inst_rows = b.get("fut_inst") or []
    dates_in_api = sorted(list(set(r.get("Date") for r in fut_inst_rows if r.get("Date"))), reverse=True)
    out.append("▍API 原始回傳日期 (fut_inst):")
    out.append(f"共 {len(dates_in_api)} 天")
    out.append(f"清單: {', '.join(dates_in_api[:5])}" + ("..." if len(dates_in_api) > 5 else ""))
    
    # 2. 檢查鎖定日期
    lock = _common_lock_date(b)
    out.append("\n▍一致性鎖（取各端點最新日的最小值）:")
    for k in _LOCK_KEYS:
        out.append(f"  {k}: {_latest_date(b.get(k) or []) or '無'}")
    out.append(f"▍今日基準日 (lock): {lock or '無'}")
    
    # 3. 檢查本地快照檔案狀態 (Render 是否清空了檔案)
    snap = _load_snap()
    snap_dates = sorted(list(snap.keys()), reverse=True)
    out.append(f"\n▍本地快照 (optchips_snap.json):")
    out.append(f"檔案實際存在: {os.path.exists(SNAP_FILE)}")
    out.append(f"快照庫內存日期: {', '.join(snap_dates) if snap_dates else '空 (或被 Render 刪除了)'}")
    
    # 4. 算出程式找出的前一日
    prevs = [d for d in snap.keys() if d < lock]
    prev_date = max(prevs) if prevs else "無"
    out.append(f"\n▍用於算增減的前一日: {prev_date}")
    
    return "\n".join(out)