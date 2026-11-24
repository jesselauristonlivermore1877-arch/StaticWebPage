# -*- coding: utf-8 -*-
"""個股／族群融資維持率（本站推估）—— 雲端新13，2026-11-20；【新】總指揮派工，Evans 11-20 夜指定

預覽＝正式版同一段程式；之後接 daily.yml 也呼叫這支。只讀本 repo 的檔，不打網路。

用法：
  正式（daily.yml 每班）：python site_tools/stock_maint.py --sector ../code/sector_map.csv → docs/data/stock_maint.json
  預覽：另加 --preview docs/preview/<目錄>（同一份結果另寫 data.json＋index.html）
網站「籌碼 → 維持率」（template.html tabMaint）讀 docs/data/stock_maint.json；說明與驗證段落由 stock_maint_page.help_html 產生，預覽與正式同一段

算法（總指揮規格）：
 1. 逐檔逐日累推「推估融資金額」（先用法規成數 r0：上市 0.6、上櫃 0.5）
      今日 V ＝ 昨日 V ×(今日餘額 − 今日買進)÷ 昨日餘額 ＋ 今日買進張 × 1000 × 當日均價 × r0
      起點（第一個有日K的交易日）＝ 餘額 × 1000 × 收盤 × r0
      買進：有 data/margin_full 的日子用證交所／櫃買公布的「融資買進」；沒有就用退路 max(今日餘額 − 昨日餘額, 0)
 2. 校準：全市場（股票＋ETF）ΣV 對官方融資金額 → 每日校準係數 k_raw ＝ 官方 ÷ ΣV；
      「有官方金額且有 ETF 逐檔」的交易日用當天 k；沒有就沿用最近一個校準日（照實標）；實際平均成數 ＝ r0 × k；各股推估金額 ＝ k × V
      驗證：用前一個校準日的 k 推今天（out-of-sample），誤差＝ k_prev × ΣV ÷ 官方 − 1
      （上市官方金額含 ETF，所以分母要含 ETF；當天沒有 ETF 逐檔就不拿來校準，照實標）
 3. 誤差＝ k×ΣV ÷ 官方 − 1（不硬湊）
 4. 個股推估維持率 ＝ 融資張數 × 1000 × 收盤 ÷ 推估融資金額；離門檻 ＝(維持率 − 門檻)÷ 維持率
    （門檻＝資料日的追繳門檻，site_tools/maint_call.py：11/24 起 120%、之前 130%；雲端舊34 11-23）
 5. 族群維持率 ＝ Σ 族群融資市值 ÷ Σ 族群推估金額（依 sector_map 當下分類，族群用「細類」）
"""
import argparse, csv, json, os, glob, random
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maint_call import maint_call   # 🔴 11-23 雲端舊34：追繳門檻依日期生效

R0 = {'twse': 0.6, 'otc': 0.5}
FILE_MKT = {'twse': 'twse', 'otc': 'tpex'}
TRACE_N = 5

# ── ETF 分組（雲端新18，11-21；個股表 ETF 列、族群表 ETF 分組、「大盤」子頁主動／被動分組共用這一處）──
#   主動式：代號 A（股票）、D（債券）、T（平衡／多重資產）結尾 —— 名稱也都以「主動」或「平衡」開頭
#   被動式：台股正2＝00631L、00663L、00675L、00685L；其他槓桿＝其餘 L 結尾；反向＝R 結尾；債券＝B 結尾；
#           期貨商品＝U 結尾；其餘（純數字代號：市值型、高息、產業主題、海外股票…）歸「市值高息等」
ETF_TW2 = ('00631L', '00663L', '00675L', '00685L')
ETF_GROUPS = [('主動式', '主動式'), ('被動式', '台股正2'), ('被動式', '其他槓桿'), ('被動式', '反向'),
              ('被動式', '市值高息等'), ('被動式', '債券'), ('被動式', '期貨商品')]


def etf_group(code):
    """回傳 (主動式／被動式, 細類)；不是 ETF（不是 00 開頭）回 None"""
    if not code.startswith('00'):
        return None
    t = code[-1]
    if t in 'ADT':
        return ('主動式', '主動式')
    if code in ETF_TW2:
        return ('被動式', '台股正2')
    return ('被動式', {'L': '其他槓桿', 'R': '反向', 'B': '債券', 'U': '期貨商品'}.get(t, '市值高息等'))


def load_official(site):
    """官方融資金額（億）。
    上市：data/margin_amt_hist.json（證交所 MI_MARGN 逐日官方值）優先；沒有的日子才用 docs/data/mkt_overlay.json maint.twse 第 4 欄
         （總指揮 11-21 裁示）；兩者重疊日的差異另外輸出到 off_cmp，列在「說明與驗證」。
    上櫃：mkt_overlay maint.otc 第 5 欄優先，缺的用 data/margin_dash_hist.json marginBalance（櫃買台股儀表板）。"""
    mo = json.load(open(os.path.join(site, 'docs/data/mkt_overlay.json')))['maint']
    hist = json.load(open(os.path.join(site, 'data/margin_amt_hist.json')))
    ovl = {r[0]: r[3] for r in mo['twse']['rows'] if r[3]}
    tw = dict(ovl); tw.update(hist)
    both = sorted(d for d in hist if d in ovl)
    diffs = [(d, (ovl[d] / hist[d] - 1) * 100) for d in both]
    cmp_ = {'n': len(both), 'start': both[0] if both else None, 'end': both[-1] if both else None,
            'only_overlay': sorted(d for d in ovl if d not in hist)}
    if diffs:
        big = [x for x in diffs if abs(x[1]) > 0.1]
        mx = max(diffs, key=lambda x: abs(x[1]))
        cmp_.update({'first_gt01': big[0][0] if big else None, 'n_gt01': len(big),
                     'max_date': mx[0], 'max_pct': round(mx[1], 3),
                     'mean_abs': round(sum(abs(x[1]) for x in diffs) / len(diffs), 3),
                     'last_date': diffs[-1][0], 'last_pct': round(diffs[-1][1], 3),
                     'monthly': {}})
        for d, v in diffs:
            cmp_['monthly'].setdefault(d[:7], []).append(v)
        cmp_['monthly'] = {k: round(max(v, key=abs), 3) for k, v in cmp_['monthly'].items()}
    otc = {}
    p = os.path.join(site, 'data/margin_dash_hist.json')
    if os.path.exists(p):
        for k, v in json.load(open(p)).items():
            if v.get('marginBalance'):
                otc[f'{k[:4]}-{k[4:6]}-{k[6:]}'] = v['marginBalance']
    for r in mo['otc']['rows']:
        if r[4]:
            otc[r[0]] = r[4]
    return {'twse': tw, 'otc': otc}, cmp_


def load_ca(site):
    """除權息／減資／面額變更（data/corp_actions.json）。只取會改變融資張數的事件：
    實測（雲端新13，11-21）：面額變更、減資當天證交所／櫃買會把融資餘額張數 × f（例：2327 面額 4 倍 6526→26429 張；
    3290 減資 0.7 → 18942→14150 張含當天買賣），所以當天先把昨日餘額 × f，不把張數跳動當成買賣；融資金額（貸款）不變。
    配股：融資張數不調整（例：1519 配 1.1 倍張數沒跳），貸款也不變 → 不調整（配到的股票不在融資擔保品裡，維持率照實下降；列待定奪）。"""
    p = os.path.join(site, 'data/corp_actions.json')
    out = {}
    if os.path.exists(p):
        for c, evs in json.load(open(p))['events'].items():
            for e in evs:
                if e.get('k') in ('面額', '減資') and e.get('f'):
                    out.setdefault(c, []).append((e['d'], float(e['f']), e['k']))
    return out


def load_rows(site, sub, mkt, d):
    p = os.path.join(site, 'data', sub, f'{FILE_MKT[mkt]}_{d}.json')
    if not os.path.exists(p):
        return None
    return json.load(open(p))['rows']


def load_sector(path):
    m = {}
    if path and os.path.exists(path):
        for r in csv.DictReader(open(path, encoding='utf-8-sig')):
            c = (r.get('code') or '').strip()
            if c:
                m[c] = ((r.get('細類') or '').strip() or '未分類', (r.get('大類') or '').strip() or '未分類')
    return m


def load_industry(site):
    """官方產業別（data/industry_official.json：證交所 t187ap03_L、櫃買 mopsfin_t187ap03_O 公司基本資料的產業別代碼＋代碼表名稱）"""
    p = os.path.join(site, 'data/industry_official.json')
    if not os.path.exists(p):
        return {}
    d = json.load(open(p))
    return {c: d['names'].get(v[0], v[0]) for c, v in d['map'].items()}


def classify(code, smap, ind):
    """族群：本站 sector_map 有分類就用「細類」（來源＝本站）；沒有就用官方產業別（來源＝官方）；都沒有＝未分類"""
    if code in smap and smap[code][0] != '未分類':
        return smap[code][0], smap[code][1], '本站'
    if code in ind:
        return ind[code], '官方產業別', '官方'
    return '未分類', '未分類', '未分類'


def run_market(site, mkt, daily, official, ca=None):
    npz = np.load(os.path.join(site, 'data/bars', 'margin.npz' if mkt == 'twse' else 'margin_otc.npz'), allow_pickle=True)
    ncodes = [str(c) for c in npz['codes']]; nnames = [str(x) for x in npz['names']]
    ndates = [str(x) for x in npz['dates']]
    dd = {d: i for i, d in enumerate(daily['dates'])}
    # 有日K的融資日；該市場日K覆蓋 < 50% 的日子（例：上櫃 11/18、11/20 日K 尚未進）不當交易日，照實列在 skipped
    msk = daily['mkt'] == FILE_MKT[mkt]
    cov = (~np.isnan(daily['close'][:, msk])).sum(1) / max(int(msk.sum()), 1)
    D = [d for d in ndates if d in dd and cov[dd[d]] >= 0.5]
    skipped = [d for d in ndates if d in dd and cov[dd[d]] < 0.5]
    carry = {}                                               # 被跳過那天的真買進併入下一個交易日
    for d in skipped:
        nxt = next((x for x in D if x > d), None)
        if nxt:
            carry.setdefault(nxt, []).append(d)
    nidx = {d: i for i, d in enumerate(ndates)}

    # 每天的逐檔原始資料：margin_full（全部，含買進）＞ margin_etf（只有 ETF）
    full = {d: load_rows(site, 'margin_full', mkt, d) for d in D}
    etf = {d: load_rows(site, 'margin_etf', mkt, d) for d in D}

    # 代號宇集：npz 股票 ＋ 檔案裡出現過的 ETF
    codes = list(ncodes); names = dict(zip(ncodes, nnames))
    seen = set(codes)
    for src in (full, etf):
        for rows in src.values():
            if rows:
                for c in rows:
                    if c.startswith('00') and c not in seen:
                        seen.add(c); codes.append(c)
    for c in codes:
        if c not in names:
            names[c] = daily['name'].get(c, c)
    ci = {c: i for i, c in enumerate(codes)}
    n = len(codes); T = len(D)
    is_etf = np.array([c.startswith('00') for c in codes])
    dcol = np.array([daily['ci'].get(c, -1) for c in codes])
    has_px = dcol >= 0

    bal = np.full((T, n), np.nan); buy_real = np.full((T, n), np.nan)
    close = np.full((T, n), np.nan); avgp = np.full((T, n), np.nan)
    etf_ok = np.zeros(T, bool); full_ok = np.zeros(T, bool)
    chk = []   # 驗證 1：margin_full 餘額 vs npz
    for t, d in enumerate(D):
        k = nidx[d]
        bal[t, :len(ncodes)] = npz['margin'][k]
        rows = full[d]
        if rows:
            full_ok[t] = True
            same = diff = 0; bad = []; flow_bad = 0
            for c, r in rows.items():
                j = ci.get(c)
                if j is None:
                    continue
                b, s, rp, pv, td = r[0], r[1], r[2], r[3], r[4]
                if pv + b - s - rp != td:
                    flow_bad += 1
                if j < len(ncodes) and not np.isnan(bal[t, j]):
                    if int(bal[t, j]) == td:
                        same += 1
                    else:
                        diff += 1
                        if len(bad) < 10:
                            bad.append([c, int(bal[t, j]), td])
                bal[t, j] = td; buy_real[t, j] = b
            chk.append({'date': d, 'same': same, 'diff': diff, 'bad': bad, 'flow_bad': flow_bad})
            for d2 in carry.get(d, []):
                r2 = load_rows(site, 'margin_full', mkt, d2) or {}
                for c, r in r2.items():
                    j = ci.get(c)
                    if j is not None and not np.isnan(buy_real[t, j]):
                        buy_real[t, j] += r[0]
        er = rows if rows else etf[d]
        if er:
            got = 0
            for c, r in er.items():
                if c.startswith('00') and c in ci:
                    bal[t, ci[c]] = r[4]; got += 1
                    if r[0] is not None:
                        buy_real[t, ci[c]] = r[0]
            etf_ok[t] = got > 0
        di = dd[d]
        close[t, has_px] = daily['close'][di, dcol[has_px]]
        v = daily['vol'][di, dcol[has_px]]; a = daily['amt'][di, dcol[has_px]]
        with np.errstate(invalid='ignore', divide='ignore'):
            avgp[t, has_px] = np.where(v > 0, a / v, np.nan)
    # 收盤停牌往前補；均價缺用收盤
    for t in range(1, T):
        m = np.isnan(close[t]); close[t, m] = close[t - 1, m]
    avgp = np.where(np.isnan(avgp), close, avgp)

    r0 = R0[mkt]

    # 減資／面額變更：事件生效的交易日，昨日餘額 × f（張數換算），不當成買賣
    adj = np.ones((T, n)); ca_applied = []
    for c, evs in (ca or {}).items():
        j = ci.get(c)
        if j is None:
            continue
        for ed, fct, kd in evs:
            t = next((i for i, d in enumerate(D) if d >= ed), None)
            if t is None or t == 0:
                continue
            adj[t, j] *= fct
            ca_applied.append([c, names.get(c, c), kd, ed, D[t], fct,
                               None if np.isnan(bal[t - 1, j]) else int(bal[t - 1, j]),
                               None if np.isnan(bal[t, j]) else int(bal[t, j])])

    def accumulate(use_real):
        V = np.full((T, n), np.nan)
        restart = np.zeros((T, n), bool)
        for t in range(T):
            b = bal[t]; px = close[t]
            if t == 0:
                V[t] = b * 1000 * px * r0; restart[t] = ~np.isnan(b); continue
            pb = bal[t - 1] * adj[t]; pv = V[t - 1]
            approx = np.maximum(b - pb, 0)
            bu = np.where(use_real & ~np.isnan(buy_real[t]), buy_real[t], approx) if use_real else approx
            bu = np.minimum(bu, b)
            with np.errstate(invalid='ignore', divide='ignore'):
                keep = np.clip(np.where(pb > 0, (b - bu) / pb, 0.0), 0, 1)
            new = np.nan_to_num(pv) * keep + bu * 1000 * avgp[t] * r0
            gap = np.isnan(pb) | np.isnan(pv)          # 前一天沒資料（ETF 斷檔／新上市）→ 用起點公式重起
            st = b * 1000 * px * r0
            V[t] = np.where(gap, st, new)
            restart[t] = gap & ~np.isnan(b)
            V[t] = np.where(b > 0, V[t], np.where(np.isnan(b), np.nan, 0.0))
        return V, restart

    V, restart = accumulate(True)
    Va, _ = accumulate(False)

    mv = bal * 1000 * close
    off = official[mkt]
    ok_px = has_px[None, :] & ~np.isnan(V)
    sumV = np.where(ok_px, V, 0).sum(1) / 1e8
    sumVa = np.where(ok_px, Va, 0).sum(1) / 1e8
    sumMV = np.nansum(np.where(ok_px, mv, 0), 1) / 1e8
    k_raw = np.full(T, np.nan)
    for t, d in enumerate(D):
        if d in off and etf_ok[t]:
            k_raw[t] = off[d] / sumV[t]
    # 當日校準：有官方金額＋ETF 逐檔的日子 k ＝ k_raw（當天）；沒有就沿用最近一個校準日（照實標 k_from）
    # 驗證用「前一校準日的成數推今天」誤差（out-of-sample，才不是硬湊）：err_pred ＝ k_prev × ΣV ÷ 官方 − 1
    k = np.full(T, np.nan); k_from = [None] * T; last_k = None; last_d = None
    cal = []
    for t, d in enumerate(D):
        o = off.get(d)
        prev_k = last_k
        if not np.isnan(k_raw[t]):
            last_k = float(k_raw[t]); last_d = d
        if last_k is not None:
            k[t] = last_k; k_from[t] = last_d
        cal.append({'date': d, 'official': o, 'sumV': round(float(sumV[t]), 2), 'sumVa': round(float(sumVa[t]), 2),
                    'mv': round(float(sumMV[t]), 2), 'etf': bool(etf_ok[t]), 'full': bool(full_ok[t]),
                    'k_raw': None if np.isnan(k_raw[t]) else round(float(k_raw[t]), 5),
                    'k': None if np.isnan(k[t]) else round(float(k[t]), 5), 'k_from': k_from[t],
                    'ratio': None if np.isnan(k[t]) else round(float(k[t] * r0), 4),
                    'est': None if np.isnan(k[t]) else round(float(k[t] * sumV[t]), 2),
                    'err': None if (np.isnan(k[t]) or not o) else round(float(k[t] * sumV[t] / o - 1) * 100, 3),
                    'err_r0': None if not o else round(float(sumV[t] / o - 1) * 100, 3),
                    'err_pred': None if (prev_k is None or np.isnan(k_raw[t])) else round(float(prev_k * sumV[t] / o - 1) * 100, 3)})

    # 每日 ETF 融資金額（校準版）＝ k × Σ ETF V；ETF 融資市值＝Σ ETF 張數 × 1000 × 收盤（億）
    # 🟢 11-21（雲端新18 追加，Evans 裁示 3）：ETF 改用跟股票同一套校準成數，市場動態卡「扣除 ETF」、「大盤」子頁、個股／ETF 表三處都讀這一串
    em = is_etf[None, :] & ok_px
    sVe = np.where(em, V, 0).sum(1); sMe = np.nansum(np.where(em, mv, 0), 1)
    eser = {D[t]: [None if np.isnan(k[t]) else float(k[t] * sVe[t]) / 1e8, float(sMe[t]) / 1e8,
                   None if np.isnan(k[t]) else float(k[t] * r0)] for t in range(T)}

    # 最新一天的個股表
    t = T - 1; kk = k[t]
    cl = maint_call(D[t], mkt)   # 這一天的追繳門檻（%）
    rows = []
    legal = {}   # 「以法定成數計」維持率（上市 6 成、上櫃 5 成，不校準的累推值）＝ 融資市值 ÷ V；主數字 ＝ 這個 × 法定成數 ÷ 校準成數
    for j, c in enumerate(codes):
        if is_etf[j] or not has_px[j]:
            continue
        b = bal[t, j]
        if not (b > 0) or not (V[t, j] > 0):
            continue
        amt = kk * V[t, j]
        mt = mv[t, j] / amt * 100
        cost = V[t, j] / (r0 * b * 1000)          # 推估融資成本（每股均價）＝ 推估買進成本 ÷ 股數
        b5 = bal[t - 5, j] * float(np.prod(adj[t - 4:t + 1, j])) if t >= 5 else np.nan
        legal[c] = round(float(mv[t, j] / V[t, j] * 100), 1)
        rows.append([c, names[c], int(b), round(float(mv[t, j]) / 1e8, 3), round(float(cost), 2),
                     round(float(mt), 1), round((mt - cl) / mt * 100, 1),
                     None if np.isnan(b5) else int(b - b5), round(float(close[t, j]), 2), round(float(amt) / 1e8, 3)])

    # ETF 個別推估維持率：🟢 11-21（雲端新18 追加，Evans 裁示 3）改用跟股票同一套校準成數（推估金額＝k × V），不再用 6 成另算；
    # 全部 ETF 推估金額合計＝eser 最新一天＝市場動態卡 ETF 融資金額。全部有融資的 ETF 都列（不設 100 張門檻，搜得到）
    etf_rows = []
    for j, c in enumerate(codes):
        if not is_etf[j] or not has_px[j]:
            continue
        b = bal[t, j]
        if not (b > 0) or not (V[t, j] > 0) or np.isnan(close[t, j]):
            continue
        amt = kk * V[t, j]
        mt = mv[t, j] / amt * 100
        cost = V[t, j] / (r0 * b * 1000)
        b5 = bal[t - 5, j] if t >= 5 else np.nan
        legal[c] = round(float(mv[t, j] / V[t, j] * 100), 1)
        etf_rows.append([c, names[c], int(b), round(float(mv[t, j]) / 1e8, 3), round(float(cost), 2),
                         round(float(mt), 1), round(float((mt - cl) / mt * 100), 1),
                         None if np.isnan(b5) else int(b - b5), round(float(close[t, j]), 2), round(float(amt) / 1e8, 3)])

    etf_cal = eser[D[-1]][0]

    # 「大盤」子頁 20 日資券進出（雲端新18）：逐檔原始資料加總（張），含 ETF／扣除 ETF 兩組；margin_full 沒有的日子只有融資（npz＋ETF 檔），融券寫 None
    board = []
    for tt in range(max(0, T - 21), T):
        d = D[tt]; rows_f = full.get(d)
        b_all = float(np.nansum(bal[tt])); b_etf = float(np.nansum(bal[tt, is_etf]))
        s_all = s_etf = None
        if rows_f:
            s_all = sum(r[5] for r in rows_f.values()); s_etf = sum(r[5] for c, r in rows_f.items() if c.startswith('00'))
        board.append({'date': d, 'lots': int(b_all), 'lots_etf': int(b_etf), 'short': s_all, 'short_etf': s_etf,
                      'etf_ok': bool(etf_ok[tt]),
                      'mv': round(float(np.nansum(np.where(has_px, mv[tt], np.nan))) / 1e8, 2),
                      'mv_etf': round(float(np.nansum(np.where(has_px & is_etf, mv[tt], np.nan))) / 1e8, 2)})

    # 抽樣累推過程
    random.seed(13)
    cand = [r[0] for r in rows if r[2] >= 500]
    picks = random.sample(cand, min(TRACE_N, len(cand)))
    traces = []
    for c in picks:
        j = ci[c]; steps = []
        for tt in list(range(0, min(3, T))) + list(range(max(T - 3, 3), T)):
            pb = bal[tt - 1, j] if tt else np.nan
            br = buy_real[tt, j]
            ap = max(bal[tt, j] - pb, 0) if tt else np.nan
            steps.append({'date': D[tt], 'bal': None if np.isnan(bal[tt, j]) else int(bal[tt, j]), 'prev': None if np.isnan(pb) else int(pb),
                          'buy': None if np.isnan(br) else int(br), 'buy_approx': None if np.isnan(ap) else int(ap),
                          'avgp': round(float(avgp[tt, j]), 2), 'close': round(float(close[tt, j]), 2),
                          'V': None if np.isnan(V[tt, j]) else round(float(V[tt, j]) / 1e6, 3), 'k': None if np.isnan(k[tt]) else round(float(k[tt]), 4),
                          'amt': None if np.isnan(k[tt]) or np.isnan(V[tt, j]) else round(float(k[tt] * V[tt, j]) / 1e6, 3),
                          'maint': None if np.isnan(k[tt]) or not (V[tt, j] > 0) else round(float(mv[tt, j] / (k[tt] * V[tt, j]) * 100), 1),
                          'restart': bool(restart[tt, j])})
        traces.append({'code': c, 'name': names[c], 'steps': steps})

    # 驗證：真的買進 vs 近似買進（只算 margin_full 有資料的區段）
    return {'date': D[-1], 'call': cl, 'start': D[0], 'skipped': skipped, 'ca': ca_applied, 'r0': r0, 'rows': rows, 'etf_rows': etf_rows, 'legal': legal, 'eser': eser, 'etf_cal': None if etf_cal is None else round(etf_cal, 1), 'board': board, 'cal': cal, 'chk': chk, 'traces': traces,
            'n_full': int(full_ok.sum()), 'n_etf': int(etf_ok.sum()), 'n_days': T}


def summarize(res):
    cal = res['cal']
    pr = [x for x in cal if x['err_pred'] is not None]
    e20 = [abs(x['err_pred']) for x in pr[-20:]]
    last = cal[-1]
    s = {'last_date': last['date'], 'ratio': last['ratio'], 'k': last['k'], 'k_from': last['k_from'],
         'err_last': last['err'], 'err_pred_last': pr[-1]['err_pred'] if pr else None,
         'err20_max': max(e20) if e20 else None, 'n_pred20': len(e20),
         'n_cal_days': sum(1 for x in cal if x['k_raw'] is not None),
         'within2': sum(1 for x in pr if abs(x['err_pred']) < 2), 'n_pred': len(pr),
         'err_r0_last': next((x['err_r0'] for x in reversed(cal) if x['err_r0'] is not None), None)}
    # 真買進 vs 近似（最後一天全市場）
    if res['n_full']:
        s['real_vs_approx_pct'] = round((last['sumV'] / last['sumVa'] - 1) * 100, 2) if last['sumVa'] else None
    if res['chk']:
        same = sum(x['same'] for x in res['chk']); diff = sum(x['diff'] for x in res['chk'])
        s['bal_match'] = round(same / max(same + diff, 1) * 100, 3); s['bal_diff'] = diff
        s['flow_bad'] = sum(x['flow_bad'] for x in res['chk'])
    return s


def sectors(rows, cl=130.0):
    """rows：[代號, 族群, 大類, 來源, 融資市值億, 推估維持率, 推估金額億]；cl＝資料日追繳門檻（lt130 欄＝低於門檻檔數，鍵名沿用）"""
    g = {}
    for c, sec, big, src, mv, mt, amt in rows:
        x = g.setdefault((src, sec), {'big': big, 'n': 0, 'mv': 0.0, 'amt': 0.0, 'lt130': 0, 'codes': []})
        x['n'] += 1; x['mv'] += mv; x['amt'] += amt; x['lt130'] += mt < cl; x['codes'].append(c)
    out = []
    for (src, sec), x in g.items():
        out.append([sec, x['big'], x['n'], round(x['mv'], 2), round(x['amt'], 2),
                    round(x['mv'] / x['amt'] * 100, 1) if x['amt'] else None, x['lt130'], x['codes'], src])
    return out


def etf_sectors(etf_rows, last, n_stock, cl=130.0):
    """ETF 分組表：[分組, 主動式／被動式／合計, 檔數, 融資張數, 融資市值億, 推估金額億, 分組維持率, 低於門檻檔數, 成分]
    依 ETF_GROUPS 順序；另附「主動式合計」「被動式合計」「ETF 合計」「股票（扣除 ETF）」四列。
    「股票（扣除 ETF）」直接取「大盤」20 日表最新一天（＝市場動態卡同一份數字），不另算"""
    g = {sub: {'top': top, 'n': 0, 'lots': 0, 'mv': 0.0, 'amt': 0.0, 'lt': 0, 'codes': []} for top, sub in ETF_GROUPS}
    for r in etf_rows:
        x = g[r[2]]
        x['n'] += 1; x['lots'] += r[3]; x['mv'] += r[4]; x['amt'] += r[10]; x['lt'] += r[6] < cl; x['codes'].append(r[0])
    row = lambda nm, top, x: [nm, top, x['n'], x['lots'], round(x['mv'], 2), round(x['amt'], 2),
                              round(x['mv'] / x['amt'] * 100, 1) if x['amt'] else None, x['lt'], x['codes']]
    def tot(keys):
        z = {'n': 0, 'lots': 0, 'mv': 0.0, 'amt': 0.0, 'lt': 0, 'codes': []}
        for k in keys:
            for kk in ('n', 'lots', 'mv', 'amt', 'lt'):
                z[kk] += g[k][kk]
        return z
    out = [row(sub, top, g[sub]) for top, sub in ETF_GROUPS if g[sub]['n']]
    act = [s for t, s in ETF_GROUPS if t == '主動式']; pas = [s for t, s in ETF_GROUPS if t == '被動式']
    out += [row('主動式合計', '合計', tot(act)), row('被動式合計', '合計', tot(pas)), row('ETF 合計', '合計', tot(act + pas))]
    if last and last.get('amt_ex'):
        out.append(['股票（扣除 ETF）', '合計', n_stock, last['lots'] - last['lots_etf'] if last['lots'] is not None else None,
                    round(last['maint_ex'] * last['amt_ex'] / 100, 2), last['amt_ex'], last['maint_ex'], None, []])
    return out


def board_rows(mkt, raw, mo, eser):
    """「大盤」子頁 20 日資券進出：維持率、融資金額直接取 docs/data/mkt_overlay.json（市場動態卡同一份），張數、融券取逐檔原始資料加總。
    上市：maint.twse.rows ＝ [日期, 含 ETF 維持率, 加權, 融資金額億, 扣除 ETF 維持率, 扣除 ETF 金額億, ETF 金額億]（etf_margin.adjust 寫的）
    上櫃：maint.otc.rows 第 3 欄＝本站含 ETF 維持率、第 5 欄＝融資金額億；扣除 ETF 用同一串校準版 ETF 金額（eser）照上市公式算（卡上沒有，本站推估）
    回傳近 21 日（最舊→最新；頁面只顯示最近 20 日，第 21 日只拿來算最舊那天的增減，總指揮 11-21 裁示），每列：date、lots、lots_etf、short、short_etf、amt、amt_ex、amt_etf、maint、maint_ex"""
    rw = {x['date']: x for x in raw}
    out = []
    for r in mo['rows']:
        d = r[0]
        if mkt == 'twse':
            if len(r) < 4 or r[1] is None or not r[3]:
                continue
            # 11-24 總指揮：mkt_overlay 有時還沒被 etf_margin.adjust 補成 7 欄（同一班先後順序），以前整段丟掉 → board 空 → maint_board／maint_120 IndexError；
            # 改成含 ETF 欄照用、扣除 ETF 三欄留空（下一班補齊）
            maint, amt = r[1], r[3]
            maint_ex, amt_ex, amt_etf = (r[4], r[5], r[6]) if len(r) >= 7 else (None, None, None)
        else:
            maint, amt = r[2], r[4]
            bk = eser.get(d)
            if maint is None or not amt or not bk or bk[0] is None:
                continue
            amt_etf = round(bk[0], 1); amt_ex = round(amt - bk[0], 1)
            maint_ex = round((maint * amt / 100 - bk[1]) / (amt - bk[0]) * 100, 2)
        x = rw.get(d, {})
        out.append({'date': d, 'lots': x.get('lots'), 'lots_etf': x.get('lots_etf'), 'short': x.get('short'), 'short_etf': x.get('short_etf'),
                    'amt': round(amt, 1), 'amt_ex': amt_ex, 'amt_etf': amt_etf, 'maint': maint, 'maint_ex': maint_ex})
    return out[-21:]


def etf_series(site, extra_twse=None):
    """校準版 ETF 融資金額逐日序列（etf_margin.adjust 寫市場動態卡「扣除 ETF」用這一段；build() 也用同一段 run_market 算，數字相同）。
    extra_twse：{日期: 上市融資金額億}，只補 load_official 沒有的日子（daily 裡 pick_edm 比 mkt_overlay.json 落地早跑時用）。
    回傳 {'twse'／'otc': {日期: [ETF 金額億, ETF 融資市值億, 校準成數]}}"""
    daily = load_daily(site)
    official, _ = load_official(site)
    for d, v in (extra_twse or {}).items():
        if v and d not in official['twse']:
            official['twse'][d] = v
    ca = load_ca(site)
    return {m: run_market(site, m, daily, official, ca)['eser'] for m in ('twse', 'otc')}


def load_daily(site):
    z = np.load(os.path.join(site, 'data/bars/daily.npz'), allow_pickle=True)
    codes = [str(c) for c in z['codes']]
    return {'dates': [str(d) for d in z['dates']], 'ci': {c: i for i, c in enumerate(codes)},
            'name': dict(zip(codes, [str(x) for x in z['names']])),
            'close': z['close'], 'vol': z['vol'], 'amt': z['amt'], 'mkt': np.array([str(x) for x in z['mkt']])}


def add_mcap_turnover(site, daily, out):
    """每列（股票 rows、ETF etf_rows）最後補 [市值億, 成交值億20日均]；印覆蓋率"""
    p = os.path.join(site, 'docs/data/company.json')
    co = (json.load(open(p, encoding='utf-8')).get('co') or {}) if os.path.exists(p) else {}
    if not co:
        print('⚠ 找不到 docs/data/company.json 股數，市值欄全部寫 —')
    amt = daily['amt']
    for mkt, res in out['mkts'].items():
        n_cap = n_to = 0
        for key in ('rows', 'etf_rows'):
            for r in res[key]:
                sh = (co.get(r[0]) or {}).get('shares') if key == 'rows' else None
                cap = round(sh * r[9] / 1e8, 1) if (sh and r[9]) else None
                i = daily['ci'].get(r[0])
                to = None
                if i is not None:
                    a = amt[-20:, i]
                    a = a[np.isfinite(a) & (a > 0)]
                    to = round(float(a.mean()) / 1e8, 2) if len(a) else None
                r.append(cap); r.append(to)
                n_cap += cap is not None; n_to += to is not None
        print(f'  {mkt} 市值欄 {n_cap} 檔、成交值欄 {n_to} 檔（股票 {len(res["rows"])}、ETF {len(res["etf_rows"])}）')


def build(site, sector):
    """算全部數字 → dict（預覽與正式共用這一段，不分兩套）"""
    daily = load_daily(site)
    official, off_cmp = load_official(site)
    ca = load_ca(site)
    ind = load_industry(site)
    smap = load_sector(sector)
    out = {'gen': 'site_tools/stock_maint.py', 'mkts': {}}
    mo = json.load(open(os.path.join(site, 'docs/data/mkt_overlay.json')))['maint']
    for mkt in ('twse', 'otc'):
        res = run_market(site, mkt, daily, official, ca)
        res['summary'] = summarize(res)
        cls = {}
        for r in res['rows']:
            sec, big, src = classify(r[0], smap, ind)
            cls[r[0]] = (big, src)
            r.insert(2, sec); r.append(src); r.append(res['legal'].get(r[0]))
        # 族群表只算融資 ≥ 100 張（同個股表預設）
        res['sectors'] = sectors([[r[0], r[2], cls[r[0]][0], r[11], r[4], r[6], r[10]] for r in res['rows'] if r[3] >= 100], res['call'])
        # ETF：第 3 欄＝ETF 細類、最後一欄來源＝'ETF'；分組維持率＝Σ融資市值 ÷ Σ推估金額（全部有融資的 ETF，不設張數門檻）
        for r in res['etf_rows']:
            top, sub = etf_group(r[0])
            r.insert(2, sub); r.append('ETF'); r.append(res['legal'].get(r[0]))
        res['board'] = board_rows(mkt, res['board'], mo[mkt], res['eser'])
        del res['legal'], res['eser']
        res['etf_sec'] = etf_sectors(res['etf_rows'], res['board'][-1] if res['board'] else None, len(res['rows']), res['call'])
        out['mkts'][mkt] = res
        print(mkt, json.dumps(res['summary'], ensure_ascii=False))
    # 🟢 11-21（雲端新19，Evans：「維持率裡面的個股可以讓我用市值排名嗎」）：每列最後加兩欄（不改既有索引，前端依索引讀）
    #    r[13] 市值（億）＝發行股數（docs/data/company.json co[代號].shares，公開資訊觀測站基本資料；河流圖同業市值同一份股數）× 收盤（r[9]）；
    #          沒有股數的寫 None（頁面「—」）；ETF 目前沒有逐檔規模的落地資料 → None
    #    r[14] 成交值（億，20 日均）＝ daily.npz 成交金額最近 20 個交易日平均（有資料的日子），代表熱門程度
    add_mcap_turnover(site, daily, out)
    out['fields'] = ['代號', '名稱', '族群', '融資張數', '融資市值億', '推估成本', '推估維持率', '離追繳門檻%', '近5日增減', '收盤', '推估金額億', '來源', '以法定成數計維持率', '市值億', '成交值億20日均']
    out['sector_fields'] = ['族群', '大類', '檔數', '融資市值億', '推估金額億', '族群維持率', '低於追繳門檻檔數', '成分股']
    out['sector_n'] = len(smap)
    out['etf_groups'] = [list(x) for x in ETF_GROUPS]
    out['etf_start'] = {'twse': mo['twse']['rows'][0][0] if mo['twse']['rows'] else None,
                        'otc': mo['otc']['rows'][0][0] if mo['otc']['rows'] else None}
    out['off_cmp'] = off_cmp
    out['sector_cov'] = {m: {k: sum(1 for r in out['mkts'][m]['rows'] if r[3] >= 100 and r[11] == k) for k in ('本站', '官方', '未分類')}
                         for m in out['mkts']}
    return out


def ext_check(text):
    """公開檔不得出現他站平台名稱（程式 repo ext_platforms.py；check_web 會 ✗✗ 擋上線）。找不到模組就跳過、印出來。"""
    for d in ('../code', '../CustomerServiceANDSales'):
        if os.path.exists(os.path.join(d, 'ext_platforms.py')):
            import sys; sys.path.insert(0, os.path.abspath(d))
            import ext_platforms
            return ext_platforms.scan(text)
    print('⚠ 找不到 ext_platforms.py，他站名稱檢查跳過')
    return []


def main():
    """正式（daily.yml 每班）：python site_tools/stock_maint.py --sector ../code/sector_map.csv
         → docs/data/stock_maint.json（網站「籌碼 → 維持率」讀這份）
       預覽：另加 --preview docs/preview/<目錄>，同一份結果再寫 data.json＋index.html（正式建置不可加，提交步驟會擋）"""
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='.')
    ap.add_argument('--sector', required=True, help='族群分類：程式 repo 當下的 sector_map.csv（跟網站其他族群口徑一致）')
    ap.add_argument('--json', default='docs/data/stock_maint.json', help='正式檔')
    ap.add_argument('--preview', default=None, help='預覽目錄（選用）')
    a = ap.parse_args()
    site = a.site
    sector = a.sector if os.path.isabs(a.sector) else os.path.join(site, a.sector)
    if not os.path.exists(sector):
        raise SystemExit(f'✗ 找不到族群分類 {sector}，不寫檔（網站沿用上一份）')
    out = build(site, sector)
    import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stock_maint_page
    pub = stock_maint_page.public(out)
    txt = json.dumps(pub, ensure_ascii=False, separators=(',', ':'))
    hit = ext_check(txt)
    if hit:
        raise SystemExit(f'✗ 公開檔出現他站平台名稱 {hit}，不寫檔')
    jp = os.path.join(site, a.json)
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    open(jp + '.tmp', 'w').write(txt); os.replace(jp + '.tmp', jp)
    print('✓', a.json, f'{len(txt) // 1024} KB；上市 {pub["mkts"]["twse"]["date"]}、上櫃 {pub["mkts"]["otc"]["date"]}；驗證 {"通過" if pub["passed"] else "未過（照實標）"}')
    if a.preview:
        os.makedirs(os.path.join(site, a.preview), exist_ok=True)
        json.dump(out, open(os.path.join(site, a.preview, 'data.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
        stock_maint_page.write(out, os.path.join(site, a.preview, 'index.html'))
        print('✓ 預覽', a.preview)


if __name__ == '__main__':
    main()
