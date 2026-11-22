# -*- coding: utf-8 -*-
"""「融資 × 指數」融資金額改官方優先 —— 雲端舊32，2026-11-22；【舊】總指揮派工（P19：改讀官方）

為什麼：docs/data/mkt_overlay.json（程式 repo tools/mkt_overlay.py 產生）上市融資金額是逐檔累推的，
  2025-09～2026-05 跟證交所公布值差 8～14.6 億；官方逐日總額已回補到 data/margin_total/<twse|otc>.json
  （site_tools/margin_total_backfill.py；每日班 --forward 往後接）。
做法（只改 docs/data/mkt_overlay.json 的數字，版面不動）：
  1. maint.twse／maint.otc rows 的融資金額欄：有官方那天用官方「今日餘額」；官方沒有的日子保留原算法，日期列在 amt_est_dates。
  2. 本站估算維持率（twse est／est_ex、otc est）＝融資市值 ÷ 融資金額 → 分母換官方後等比例重算（市值不變）；
     otc 第 2 欄 official（證交所全市場擔保維持率）是官方值，不動。last 換成 rows 同一天那列；百分位用同公式重算。
  3. maint.cuts 與 maint.wave 的大減金額（chg_yi、chg_pct、margin_yi、prev_yi、sum_yi、sum_pct、why 文字）用官方逐日餘額重算；
     哪幾天算大減仍由 tools/mkt_overlay.py 決定（選日規則在程式 repo），換官方後若某天不再過門檻 → 印 ⚠ 列待定奪，不自行刪。
  4. maint.check.twse／otc（網站「核對：」那行）註明「融資金額＝官方 n 天、本站累推 m 天（日期）」→ 就是頁面上的標示。
排在 daily「疊圖三張」之後、「融資維持率改含 ETF」之前（ETF 修正用的是這裡換好的官方分母）。只讀檔、不打網路。
用法：python site_tools/margin_official.py [site]　　（exit 0＝已套用或不需套用；1＝沒改）
"""
import json, os, re, sys


def load(site, mkt):
    p = os.path.join(site, 'data', 'margin_total', mkt + '.json')
    return {k: v[1] for k, v in json.load(open(p))['days'].items()} if os.path.exists(p) else {}


def pct_le(vals, v):     # 同 etf_margin.adjust 的上市百分位公式
    return round(100 * sum(x <= v for x in vals) / len(vals))


def pct_mid(vals, v):    # 同 etf_margin.adjust 的上櫃 pct_est 公式
    return round((sum(1 for y in vals if y < v) + 0.5 * sum(1 for y in vals if y == v)) / len(vals) * 100)


def fix_rows(T, off, im, iests):
    """rows 的融資金額換官方、估算維持率等比例重算；回傳 (官方天數, 本站累推日期, 最大差[日期, 原值, 官方])"""
    n, est_days, mx = 0, [], None
    for r in T['rows']:
        d, old = r[0], r[im]
        if d not in off:
            est_days.append(d); continue
        new = round(off[d], 2)
        if old:
            for ie in iests:
                if ie < len(r) and r[ie] is not None:
                    r[ie] = round(r[ie] * old / new, 2)
            if mx is None or abs(old - new) > abs(mx[1] - mx[2]):
                mx = [d, old, new]
        r[im] = new; n += 1
    if T.get('last'):
        x = next((r for r in T['rows'] if r[0] == T['last'][0]), None)
        if x:
            T['last'] = list(x)
    return n, est_days, mx


def chg(off, ds, d):
    """官方 d 那天比 rows 前一個交易日的變化（億、%）"""
    i = ds.index(d) if d in ds else -1
    if i <= 0 or d not in off or ds[i - 1] not in off:
        return None
    a, b = off[ds[i - 1]], off[d]
    return round(b - a, 1), round((b - a) / a * 100, 2), round(a, 1), round(b, 1)


def fix_why(s, cy, cp):
    s = re.sub(r'減幅 -?[\d.]+%', f'減幅 {abs(cp):.2f}%', s)
    return re.sub(r'減額 -?[\d.]+ 億', f'減額 {abs(cy):.1f} 億', s)


def fix_cuts(lst, off, ds, floor, nm):
    warn = []
    for c in lst or []:
        for x in c.get('days', []):
            z = chg(off, ds, x['date'])
            if not z:
                continue
            x['chg_yi'], x['chg_pct'] = z[0], z[1]
            if 'why' in x:
                x['why'] = fix_why(x['why'], z[0], z[1])
            thr = x.get('thr_pct')
            ok = (thr is not None and -z[1] >= thr) or (-z[0] >= floor and -z[1] >= 2)
            if not ok:
                warn.append(f'{nm} {x["date"]} 換官方後 {z[0]} 億（{z[1]}%）不再過大減門檻（tools/mkt_overlay.py 仍標大減）')
        z = chg(off, ds, c['date'])
        if z:
            c['chg_yi'], c['chg_pct'], c['margin_yi'] = z[0], z[1], z[3]
        if c.get('from') in off and c.get('to') in off:
            a, b = off[c['from']], off[c['to']]
            c['sum_yi'], c['sum_pct'] = round(b - a, 1), round((b - a) / a * 100, 2)
    return warn


def fix_cut1(W, off, ds):
    if not W:
        return
    z = chg(off, ds, W['date'])
    if z:
        W['chg_yi'], W['chg_pct'], W['prev_yi'], W['margin_yi'] = z
        W['check'] = (W.get('check', '') + '；' if W.get('check') else '') + '金額已換證交所／櫃買公布值（data/margin_total）'


def patch(M, site):
    tw, ot = load(site, 'twse'), load(site, 'otc')
    if not tw and not ot:
        print('✗ data/margin_total 沒有官方檔，不改'); return 1
    if M.get('amt_official'):
        print('已經是官方優先版（amt_official），不重複套用'); return 0
    T, O = M['twse'], M.get('otc') or {}
    rep = {}
    # 上市：fields date, est, taiex, margin_yi[, est_ex, margin_ex_yi, etf_amt_yi]（含 ETF 版的 est_ex 分母是 margin_ex，不在這裡改）
    fi = T.get('fields', ['date', 'est', 'taiex', 'margin_yi'])
    if T.get('etf_in'):
        print('⚠ 上市已是含 ETF 版（etf_margin patch 先跑了）→ 不改（順序要在 ETF 修正之前）'); return 1
    n, est_days, mx = fix_rows(T, tw, fi.index('margin_yi'), [fi.index('est')])
    vals = [r[1] for r in T['rows'] if r[1] is not None]
    if vals and T.get('last'):
        T['pct'] = pct_le(vals, T['last'][1])
    T['amt_est_dates'] = est_days
    rep['twse'] = (n, est_days, mx)
    if O.get('rows'):
        fo = O.get('fields', ['date', 'official', 'est', 'tpex', 'margin_yi'])
        n2, est2, mx2 = fix_rows(O, ot, fo.index('margin_yi'), [fo.index('est')])
        ie = fo.index('est')
        ev = [r[ie] for r in O['rows'] if r[ie]]
        v = next((r[ie] for r in reversed(O['rows']) if r[ie]), None)
        if ev and v is not None and 'pct_est' in O:
            O['pct_est'] = pct_mid(ev, v)
        O['amt_est_dates'] = est2
        rep['otc'] = (n2, est2, mx2)
    # 大減金額
    CU = M.get('cuts') or {}
    warn = fix_cuts(CU.get('twse'), tw, [r[0] for r in T['rows']], 100, '上市')
    if O.get('rows'):
        warn += fix_cuts(CU.get('otc'), ot, [r[0] for r in O['rows']], 50, '上櫃')
    W = M.get('wave') or {}
    fix_cut1(W.get('cut'), tw, [r[0] for r in T['rows']])
    if O.get('rows'):
        fix_cut1(W.get('otc_cut'), ot, [r[0] for r in O['rows']])
        if W.get('otc_low') and W['otc_low'].get('date') in ot:
            W['otc_low']['margin_yi'] = round(ot[W['otc_low']['date']], 2)
    if W.get('maint_low') and W['maint_low'].get('date') in tw:
        W['maint_low']['margin_yi'] = round(tw[W['maint_low']['date']], 1)
    # 頁面標示（核對那行）
    ck = M.setdefault('check', {})
    for k, nm in (('twse', '上市'), ('otc', '上櫃')):
        if k not in rep:
            continue
        n_, ed, mx_ = rep[k]
        s = f'{nm}融資金額官方優先：{n_} 天用{"證交所" if k == "twse" else "櫃買"}公布值'
        s += f'、{len(ed)} 天官方未到用本站累推（{ed[0]}～{ed[-1]}）' if ed else '、本站累推 0 天'
        if mx_:
            s += f'；換官方前最大差 {mx_[0]} {mx_[1] - mx_[2]:+.1f} 億'
        ck[k + '_amt'] = s
        if k == 'twse':
            ck['twse'] = s + (('；' + ck['twse']) if ck.get('twse') and not ck['twse'].startswith('上市融資金額官方優先') else '')
        print('✓ ' + s)
    for w in warn:
        print('⚠ ' + w)
    M['amt_official'] = True
    return 0


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else '.'
    pj = os.path.join(site, 'docs', 'data', 'mkt_overlay.json')
    J = json.load(open(pj))
    rc = patch(J['maint'], site)
    if rc:
        return rc
    tmp = pj + '.tmp'
    json.dump(J, open(tmp, 'w'), ensure_ascii=False)   # 先寫暫存檔，成功才換掉
    json.load(open(tmp)); os.replace(tmp, pj)
    print(f'✓ 已改 {pj}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
