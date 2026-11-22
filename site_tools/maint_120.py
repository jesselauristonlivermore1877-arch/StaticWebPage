# -*- coding: utf-8 -*-
"""融資維持率門檻 130%→120%（市場傳聞）影響推估 —— 雲端舊27，2026-11-22；【舊】總指揮派工（Evans 11-22 指定工商時報該文）

只讀本 repo 的檔、不打網路；口徑跟網站「籌碼 → 維持率」同一套（docs/data/stock_maint.json＝site_tools/stock_maint.py 產出；
校準成數，不用法定 6 成）。大盤維持率＝docs/data/mkt_overlay.json maint（同「市場動態」卡）。
核對（另一份原始資料重算）：
  ① 個股融資市值：data/margin_full/<twse|tpex>_<日>.json 今日餘額（證交所 MI_MARGN／櫃買）× data/bars/daily.npz 收盤，逐檔比 stock_maint 的融資市值
  ② 融資金額合計：個股＋ETF 推估金額加總 vs 官方融資總金額（mkt_overlay；上市＝證交所 MI_MARGN）
  ③ 大盤維持率：Σ融資市值 ÷ Σ推估金額 vs mkt_overlay 的 est／est_ex
  ④ 事件統計：加權收盤（data/nsf/yahoo_twii.json）、上市融資金額（data/margin_total/twse.json）跟 data/margin_amt_hist.json 重疊日比對
核對不過就不出檔（exit 2）。
用法：python site_tools/maint_120.py --preview docs/preview/maint_120
"""
import argparse, json, os, sys, datetime as dt, html
import numpy as np

SITE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
MK = {'twse': '上市', 'otc': '上櫃'}
FILE_MKT = {'twse': 'twse', 'otc': 'tpex'}
# 官方先例（只收官方出處，程式打開核對過原文；雲端舊27 11-22 核對）
EVENTS = [
    {'d': '2015-05-04', 'kind': '門檻提高', 'what': '信用交易整戶擔保維持率由 120% 提高至 130%（配合 2015-06-01 漲跌幅由 7% 放寬為 10%，提前 1 個月先行調整）',
     'src': '金管會出版品〈證券市場揚升計畫〉專題（民國 104 年 12 月 16 日出版）',
     'u': 'https://www.fsc.gov.tw/fckdowndoc?file=%2F%E5%B0%88%E9%A1%8C%E4%B8%80%282%29.pdf&flag=doc'},
    {'d': '2020-03-19', 'kind': '放寬補繳', 'what': '放寬信用交易追繳差額之抵繳擔保品範圍（3 個月）：經授信機構同意，得以其他具流動性的擔保品補繳融資自備款或融券保證金差額；門檻 130% 未改',
     'src': '金管會新聞稿 2020-03-18', 'u': 'https://www.sfb.gov.tw/ch/home.jsp?id=95&parentpath=0,2&mcustomize=news_view.jsp&dataserno=202003180001&dtable=News'},
    {'d': '2025-04-07', 'kind': '放寬補繳', 'what': '暫行措施（2025-04-07～04-11，之後延長）：得以其他多元擔保品補繳融資自備款或融券保證金差額；門檻 130% 未改；2025-05-23 宣布恢復',
     'src': '金管會新聞稿 2025-04-06、2025-05-23', 'u': 'https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2&mcustomize=news_view.jsp&dataserno=202504060002&dtable=News',
     'u2': 'https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2&mcustomize=news_view.jsp&dataserno=202505230003&dtable=News'},
    {'d': '2026-11-09', 'kind': '放寬補繳', 'what': '最低融券保證金成數 90%→130%、多元擔保品補繳融資自備款或融券保證金差額等；門檻 130% 未改（11-21 再宣布全面禁止平盤以下放空等 5 項，也沒有調整維持率）',
     'src': '金管會新聞稿 2026-11-06、2026-11-21', 'u': 'https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2&mcustomize=news_view.jsp&dataserno=202611060002&dtable=News',
     'u2': 'https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2&mcustomize=news_view.jsp&dataserno=202611210001&dtable=News'},
]
RUMOR = {'src': '工商時報', 'date': '2026-11-22 03:00', 'title': '證交所急召十券商！今討論融資維持率是否降至120％備受矚目',
         'u': 'https://www.ctee.com.tw/news/20261122700045-430201', 'dash': 151.78, 'call_n': 6462, 'call_amt': 64.64}
BANDS = [(0, 120, '低於 120%'), (120, 130, '120%～130%'), (130, 140, '130%～140%'), (140, 1e9, '140% 以上')]


def J(p):
    return json.load(open(os.path.join(SITE, p), encoding='utf-8'))


def band_stats(rows):
    """rows：stock_maint 列（[3]張、[4]融資市值億、[6]推估維持率、[10]推估金額億）"""
    out = []
    tot = sum(r[10] for r in rows)
    for lo, hi, nm in BANDS:
        s = [r for r in rows if lo <= r[6] < hi]
        out.append({'band': nm, 'n': len(s), 'amt': round(sum(r[10] for r in s), 1), 'mv': round(sum(r[4] for r in s), 1),
                    'pct': round(sum(r[10] for r in s) / tot * 100, 1) if tot else 0})
    return out, round(tot, 1)


def verify_mv(mkt, date, rows):
    """① margin_full 今日餘額 × daily.npz 收盤 重算融資市值"""
    p = os.path.join(SITE, 'data/margin_full', '%s_%s.json' % (FILE_MKT[mkt], date))
    if not os.path.exists(p):
        return {'ok': None, 'why': '沒有 %s' % os.path.basename(p)}
    full = json.load(open(p))['rows']
    z = np.load(os.path.join(SITE, 'data/bars/daily.npz'), allow_pickle=True)
    di = [str(x) for x in z['dates']].index(date)
    ci = {str(c): i for i, c in enumerate(z['codes'])}
    n = bad = 0; mx = 0.0; worst = None
    for r in rows:
        c = r[0]
        if c not in full or c not in ci:
            continue
        cl = float(z['close'][di, ci[c]])
        if not np.isfinite(cl) or cl <= 0:
            continue
        mv2 = full[c][4] * 1000 * cl / 1e8
        n += 1
        d = abs(mv2 - r[4]) / r[4] if r[4] >= 0.01 else 0.0     # 0.01 億以下的檔四捨五入誤差大，只看絕對差
        if d > mx:
            mx, worst = d, (c, r[4], round(mv2, 3))
        if abs(mv2 - r[4]) > 0.002 + r[4] * 0.002:
            bad += 1
    return {'ok': n > 100 and bad <= n * 0.01, 'n': n, 'bad': bad, 'max_rel': round(mx * 100, 3), 'worst': worst}


def series_events():
    y = J('data/nsf/yahoo_twii.json')['chart']['result'][0]
    cl = y['indicators']['quote'][0]['close']
    tw = {}
    for t, c in zip(y['timestamp'], cl):
        if c:
            tw[dt.datetime.fromtimestamp(t + 8 * 3600, dt.timezone.utc).strftime('%Y-%m-%d')] = c
    mt = {d: v[1] for d, v in J('data/margin_total/twse.json')['days'].items()}
    # ④ 核對：margin_total vs margin_amt_hist 重疊日
    hist = J('data/margin_amt_hist.json')
    both = [d for d in hist if d in mt]
    mxd = max((abs(mt[d] / hist[d] - 1) * 100 for d in both), default=None)
    chk = {'n': len(both), 'max_pct': None if mxd is None else round(mxd, 3), 'ok': bool(both) and mxd < 0.1}
    D = sorted(tw)
    res = []
    for e in EVENTS:
        i0 = next((i for i, d in enumerate(D) if d >= e['d']), None)
        if i0 is None or i0 == 0:
            continue
        b = D[i0 - 1]
        row = {'d': e['d'], 'base': b, 'tw0': round(tw[b], 2), 'm0': mt.get(b)}
        for h in (5, 20, 60):
            j = i0 - 1 + h
            if j < len(D):
                dj = D[j]
                row['tw%d' % h] = round((tw[dj] / tw[b] - 1) * 100, 1)
                row['m%d' % h] = None if (mt.get(b) is None or mt.get(dj) is None) else round((mt[dj] / mt[b] - 1) * 100, 1)
                row['d%d' % h] = dj
            else:
                row['tw%d' % h] = row['m%d' % h] = None
        res.append(row)
    return res, chk


def build():
    sm = J('docs/data/stock_maint.json')
    mo = J('docs/data/mkt_overlay.json')['maint']
    out = {'gen': 'site_tools/maint_120.py', 'rumor': RUMOR, 'events': EVENTS, 'mkts': {}, 'chk': {}}
    fails = []
    for m in ('twse', 'otc'):
        M = sm['mkts'][m]
        stocks, etfs = M['rows'], M['etf']
        bs, ts = band_stats(stocks)
        be, te = band_stats(etfs)
        ba, ta = band_stats(stocks + etfs)
        # 大盤：mkt_overlay（網站市場動態卡）
        ol = mo[m]['last']; f = mo[m]['fields']
        est = ol[f.index('est')]
        est_ex = ol[f.index('est_ex')] if 'est_ex' in f else None
        # 上櫃 mkt_overlay 沒有 est_ex → 用 stock_maint board 最後一天（同一支程式算的）
        bd = M['board'][-1]
        if est_ex is None:
            est_ex = bd.get('maint_ex')
        mvs = sum(r[4] for r in stocks) + sum(r[4] for r in etfs)
        amts = sum(r[10] for r in stocks) + sum(r[10] for r in etfs)
        mv_ex = sum(r[4] for r in stocks)
        # ② ③ 核對
        off = ol[f.index('margin_yi')]
        c2 = abs(amts / off - 1) * 100
        c3 = abs(mvs / amts * 100 - est)
        c3x = abs(mv_ex / ts * 100 - est_ex)
        v1 = verify_mv(m, M['date'], stocks)
        ck = {'mv_recalc': v1, 'amt_vs_official_pct': round(c2, 3), 'official_amt': off, 'sum_amt': round(amts, 1),
              'maint_recalc': round(mvs / amts * 100, 2), 'maint_overlay': est, 'maint_ex_recalc': round(mv_ex / ts * 100, 2), 'maint_ex_overlay': est_ex}
        ck['ok'] = (v1['ok'] is not False) and c2 < 0.5 and c3 < 0.3 and c3x < 0.3
        if not ck['ok']:
            fails.append(m)
        out['chk'][m] = ck
        mk = {'date': M['date'], 'stocks': bs, 'etf': be, 'all': ba, 'tot': {'stocks': ts, 'etf': te, 'all': ta},
              'maint': est, 'maint_ex': est_ex, 'off_amt': off}
        for k, v in (('all', est), ('ex', est_ex)):
            mk['to130_' + k] = round((1 - 130 / v) * 100, 1) if v else None
            mk['to120_' + k] = round((1 - 120 / v) * 100, 1) if v else None
        if m == 'otc':
            mk['official'] = ol[f.index('official')]
        # 族群（股票，同網站族群表：融資 100 張以上的個股合計）：融資金額前 20 大族群
        sec = sorted(M['sec'], key=lambda s: -s[4])[:20]
        mk['sec'] = [{'name': s[0], 'cls': s[1], 'n': s[2], 'mv': s[3], 'amt': s[4], 'maint': s[5],
                      'to130': round((1 - 130 / s[5]) * 100, 1), 'to120': round((1 - 120 / s[5]) * 100, 1)} for s in sec]
        out['mkts'][m] = mk
    # 上市＋上櫃合計（本站推估，含 ETF）
    tw, ot = out['mkts']['twse'], out['mkts']['otc']
    mv_all = tw['maint'] * tw['off_amt'] / 100 + ot['maint'] * ot['off_amt'] / 100
    out['combined'] = {'maint': round(mv_all / (tw['off_amt'] + ot['off_amt']) * 100, 2), 'amt': round(tw['off_amt'] + ot['off_amt'], 1),
                       'official_whole': ot.get('official')}
    ev, c4 = series_events()
    out['ev_stats'] = ev; out['chk']['events'] = c4
    if not c4['ok']:
        fails.append('events')
    out['passed'] = not fails; out['fail'] = fails
    return out


def fmt(x, nd=1):
    return '—' if x is None else ('{:,.%df}' % nd).format(x)


def page(o):
    E = html.escape
    tw, ot = o['mkts']['twse'], o['mkts']['otc']
    R = o['rumor']
    def band_tbl(mk, lab):
        h = ['<table class="m1-t"><thead><tr><th>推估維持率</th><th>組別</th><th>檔數</th><th>推估融資金額（億）</th><th>融資市值（億）</th><th>占該組融資金額</th></tr></thead><tbody>']
        for key, nm in (('stocks', '股票（扣 ETF）'), ('etf', 'ETF'), ('all', '合計（含 ETF）')):
            for b in mk[key]:
                hl = ' class="m1-hl"' if b['band'] == '120%～130%' else ''
                h.append('<tr%s><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s%%</td></tr>' % (hl, b['band'], nm, b['n'], fmt(b['amt']), fmt(b['mv']), fmt(b['pct'])))
        h.append('</tbody></table>')
        return '<h3>%s（%s）</h3>' % (lab, mk['date']) + ''.join(h)
    def mid(mk, key):
        return next(b for b in mk[key] if b['band'] == '120%～130%')
    s_tw, s_ot = mid(tw, 'all'), mid(ot, 'all')
    x_tw, x_ot = mid(tw, 'stocks'), mid(ot, 'stocks')
    lo_tw = next(b for b in tw['all'] if b['band'] == '低於 120%'); lo_ot = next(b for b in ot['all'] if b['band'] == '低於 120%')
    mkt_rows = ''
    for lab, mk in (('上市', tw), ('上櫃', ot)):
        for k, nm in (('all', '含 ETF'), ('ex', '扣 ETF')):
            v = mk['maint'] if k == 'all' else mk['maint_ex']
            mkt_rows += '<tr><td>%s %s</td><td>%s%%</td><td>%s%%</td><td>%s%%</td></tr>' % (lab, nm, fmt(v, 2), fmt(-mk['to130_' + k]) if mk['to130_' + k] > 0 else '已低於', fmt(-mk['to120_' + k]) if mk['to120_' + k] > 0 else '已低於')
    sec_rows = ''
    for lab, mk in (('上市', tw), ('上櫃', ot)):
        for s in sorted(mk['sec'], key=lambda s: s['maint']):
            sec_rows += '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s%%</td><td>%s</td><td>%s</td></tr>' % (
                lab, E(s['name']), s['n'], fmt(s['amt']), fmt(s['maint']),
                ('%s%%' % fmt(-s['to130'])) if s['to130'] > 0 else '已低於', ('%s%%' % fmt(-s['to120'])) if s['to120'] > 0 else '已低於')
    ev_rows = ''
    st = {x['d']: x for x in o['ev_stats']}
    for e in o['events']:
        x = st.get(e['d'], {})
        links = '<a href="%s">%s</a>' % (E(e['u']), E(e['src'])) + ((' ／ <a href="%s">後續</a>' % E(e['u2'])) if e.get('u2') else '')
        def cell(k):
            v = x.get(k)
            return '—' if v is None else ('%+.1f%%' % v)
        ev_rows += '<tr><td>%s</td><td>%s</td><td class="m1-w">%s<br><span class="m1-s">%s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            e['d'], e['kind'], E(e['what']), links, cell('tw5'), cell('tw20'), cell('tw60'), cell('m5'), cell('m20'), cell('m60'))
    ck = o['chk']
    def ckline(m):
        c = ck[m]; v = c['mv_recalc']
        return '<li>%s：① 融資市值逐檔重算 %s 檔、超過 0.2%% 差的 %s 檔（最大相對差 %s%%）；② 推估融資金額合計 %s 億 vs 官方 %s 億（差 %s%%）；③ 大盤維持率重算含 ETF %s%% vs 網站 %s%%、扣 ETF %s%% vs 網站 %s%% → %s</li>' % (
            MK[m], v.get('n'), v.get('bad'), v.get('max_rel'), fmt(c['sum_amt']), fmt(c['official_amt']), c['amt_vs_official_pct'],
            c['maint_recalc'], c['maint_overlay'], c['maint_ex_recalc'], c['maint_ex_overlay'], '通過' if c['ok'] else '<b>未過</b>')
    c4 = ck['events']
    cb = o['combined']
    diff_dash = R['dash'] - (cb['official_whole'] or 0)
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>維持率門檻情境</title><style>
:root{{--bg:#f6f5f1;--ink:#1d1d1b;--ink2:#5c5b57;--line:#dcd9d0;--acc:#b0842f;--card:#fff;--hl:#fbf1dc;--warn:#b3261e}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16171a;--ink:#ecebe7;--ink2:#a4a29c;--line:#34363b;--acc:#d6a54a;--card:#1f2125;--hl:#3a3220;--warn:#f2b8b5}}}}
:root[data-theme="dark"]{{--bg:#16171a;--ink:#ecebe7;--ink2:#a4a29c;--line:#34363b;--acc:#d6a54a;--card:#1f2125;--hl:#3a3220;--warn:#f2b8b5}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 system-ui,-apple-system,"Noto Sans TC",sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:0 0 8px}} h3{{font-size:15px;margin:12px 0 6px}}
.m1-m{{color:var(--ink2);font-size:13px;margin:0 0 14px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:14px}}
.m1-rumor{{border-color:var(--warn)}} .m1-tag{{display:inline-block;border:1px solid var(--warn);color:var(--warn);border-radius:4px;padding:0 6px;font-size:13px;font-weight:700}}
.m1-k{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:8px 0}}
.m1-k div{{border:1px solid var(--line);border-radius:8px;padding:8px 10px}} .m1-k b{{display:block;font-size:20px}} .m1-k span{{color:var(--ink2);font-size:12px}}
.m1-x{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
.m1-t{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}
.m1-t th,.m1-t td{{border-bottom:1px solid var(--line);padding:4px 6px;text-align:right;white-space:nowrap}}
.m1-t th:first-child,.m1-t td:first-child,.m1-t td.m1-w{{text-align:left}} .m1-t td.m1-w{{white-space:normal;min-width:260px}}
.m1-hl td{{background:var(--hl);font-weight:700}} .m1-s{{color:var(--ink2);font-size:12px}}
a{{color:var(--acc)}} ul{{padding-left:20px;margin:6px 0}} li{{margin:3px 0}}
.m1-foot{{color:var(--ink2);font-size:13px;text-align:center;margin-top:18px}}
</style></head><body><main>
<h1>融資維持率門檻 130%→120%：若實施的情境分析</h1>
<p class="m1-m"><span class="m1-tag">市場傳聞，未經官方證實</span> 現行門檻仍是 130%，本頁只推估「若改成 120%」的情境｜資料日 上市 {tw['date']}／上櫃 {ot['date']}｜歷史統計與推估，非投資建議｜產生：{o['gen']}</p>

<section class="m1-rumor"><h2><span class="m1-tag">市場傳聞，未經官方證實</span> 目前狀態</h2>
<ul><li>{E(R['src'])} {R['date']}〈<a href="{E(R['u'])}">{E(R['title'])}</a>〉：報導稱證交所通知券商開會，討論整戶擔保維持率由 130% 降到 120%。報導未引用官方公告或官員原話。</li>
<li>官方現況：證券商辦理融資融券業務操作辦法第 54 條仍是「整戶擔保維持率低於 130% 應通知補繳」。金管會 2026-11-06、11-21 宣布的穩定措施都<b>沒有</b>調整維持率門檻。</li>
<li>本站每 15 分鐘檢查行政院、財政部、金管會、央行、證交所、期交所、集保結算所新聞稿；標題一出現維持率調整字眼就發通知，確認後才把這件事寫進「官方穩定市場措施」與根因追蹤。</li></ul></section>

<section><h2>重點</h2><div class="m1-k">
<div><span>上市＋上櫃 推估維持率落在 120%～130% 的融資金額</span><b>{fmt(s_tw['amt']+s_ot['amt'])} 億</b><span>占全體融資金額 {fmt((s_tw['amt']+s_ot['amt'])/(tw['tot']['all']+ot['tot']['all'])*100)}%（{s_tw['n']+s_ot['n']} 檔，含 ETF）</span></div>
<div><span>同上，扣 ETF（只算股票）</span><b>{fmt(x_tw['amt']+x_ot['amt'])} 億</b><span>{x_tw['n']+x_ot['n']} 檔</span></div>
<div><span>推估維持率已低於 120%（門檻降了也仍在追繳線下）</span><b>{fmt(lo_tw['amt']+lo_ot['amt'])} 億</b><span>{lo_tw['n']+lo_ot['n']} 檔，含 ETF</span></div>
<div><span>大盤推估維持率（上市含 ETF／上櫃含 ETF）</span><b>{fmt(tw['maint'],2)}%／{fmt(ot['maint'],2)}%</b><span>再跌 {fmt(tw['to120_all'])}%／{fmt(ot['to120_all'])}% 碰到 120%</span></div>
</div>
<p class="m1-s">「門檻從 130% 降到 120% 後暫時不用追繳」的規模，本表用「推估維持率落在 120%～130% 的個股融資金額」代表。130%／120% 是<b>整戶</b>計算（投資人帳戶裡所有融資、融券、抵繳品合在一起），本表是每檔「全體融資戶平均」推估，個別投資人差很多：同一檔裡有人遠高於平均、有人已經低於 120%。</p></section>

<section><h2>一、各維持率區間的融資規模</h2><div class="m1-x">{band_tbl(tw,'上市')}{band_tbl(ot,'上櫃')}</div>
<p class="m1-s">推估融資金額＝網站「籌碼 → 維持率」同一套（逐檔累推、再用官方融資總金額逐日校準成數，上市 {sm_ratio(o,'twse')}、上櫃 {sm_ratio(o,'otc')}；不用法定 6 成／5 成）。占比分母＝該組全部推估融資金額。</p></section>

<section><h2>二、大盤再跌多少會碰到 130%／120%</h2><div class="m1-x"><table class="m1-t"><thead><tr><th>市場</th><th>推估維持率</th><th>碰到 130% 的跌幅</th><th>碰到 120% 的跌幅</th></tr></thead><tbody>{mkt_rows}</tbody></table></div>
<p class="m1-s">算法：融資金額不變、融資部位市值同比例下跌，維持率 V 跌到門檻 T 的跌幅＝1 − T÷V。只用融資這一側，不含融券與抵繳品。</p>
<h3>族群（各市場融資金額前 20 大，依推估維持率由低到高）</h3><div class="m1-x"><table class="m1-t"><thead><tr><th>市場</th><th>族群</th><th>檔數</th><th>推估融資金額（億）</th><th>推估維持率</th><th>碰到 130%</th><th>碰到 120%</th></tr></thead><tbody>{sec_rows}</tbody></table></div>
<p class="m1-s">族群＝網站族群表同一份（依目前分類；只計融資 100 張以上個股）。</p></section>

<section><h2>三、跟報導數字比對</h2><ul>
<li>報導：證交所台股儀表板 11/20 整體擔保維持率 {R['dash']}%。本站落地的同一個官方數字（證交所全市場擔保維持率，經櫃買儀表板落地）11/20＝<b>{fmt(cb['official_whole'],2)}%</b>，差 {fmt(diff_dash,2)} 個百分點，原因未查明（可能是取值時點不同），照實列出。</li>
<li>本站推估：上市含 ETF {fmt(tw['maint'],2)}%、扣 ETF {fmt(tw['maint_ex'],2)}%；上櫃含 ETF {fmt(ot['maint'],2)}%、扣 ETF {fmt(ot['maint_ex'],2)}%；上市＋上櫃合計 {fmt(cb['maint'],2)}%。</li>
<li>為什麼官方數字比較高：官方是<b>整戶</b>口徑，公式＝（融資擔保品市值＋融券擔保品及保證金＋抵繳品市值）÷（融資金額＋融券標的市值）（操作辦法第 53 條），融券那一側（賣出價款＋保證金，最低成數 11-09 起 130%、11-23 起 150%）和抵繳品都會把比率拉高；本站只算融資這一側、按證券別推估，所以比較低。兩者走勢可比，水準不可直接相減。</li>
<li>報導另引民間估算（含 ETF 138.42%、扣 ETF 119.53%），口徑未公開，本站不比對。</li></ul></section>

<section><h2>四、歷史上主管機關調整維持率／追繳的先例（只列官方出處）</h2>
<p>官方紀錄中<b>未查到「暫時調降整戶擔保維持率門檻」的先例</b>；查到的是 2015 年把門檻由 120% <b>提高</b>到 130%，以及三次「放寬補繳擔保品範圍」（門檻不變）。</p>
<div class="m1-x"><table class="m1-t"><thead><tr><th>生效日</th><th>類型</th><th>內容與官方出處</th><th>加權 5 日</th><th>加權 20 日</th><th>加權 60 日</th><th>上市融資 5 日</th><th>20 日</th><th>60 日</th></tr></thead><tbody>{ev_rows}</tbody></table></div>
<p class="m1-s">變化＝生效日前一個交易日收盤 → 之後第 5／20／60 個交易日；「—」＝還沒到。樣本只有 4 件、性質各不相同（一次提高門檻、三次放寬補繳），而且都在大跌當中或剛過，<b>只描述、不下結論</b>。加權＝本站加權收盤檔；上市融資＝證交所 MI_MARGN 融資金額。</p></section>

<section><h2>核對（另一份原始資料重算）</h2><ul>{ckline('twse')}{ckline('otc')}
<li>事件統計的上市融資金額檔跟 margin_amt_hist 重疊 {c4['n']} 天，最大差 {c4['max_pct']}% → {'通過' if c4['ok'] else '<b>未過</b>'}</li></ul></section>
<p class="m1-foot">歷史統計與推估，非投資建議。不含任何買賣建議或預測。</p>
</main></body></html>'''


def sm_ratio(o, m):
    r = J('docs/data/stock_maint.json')['mkts'][m]['ratio']
    return '%.1f%%' % (r * 100)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview', required=True)
    a = ap.parse_args()
    o = build()
    for m in ('twse', 'otc'):
        print(MK[m], json.dumps(o['chk'][m], ensure_ascii=False))
    print('事件核對', o['chk']['events'])
    if not o['passed']:
        print('✗ 核對未過：', o['fail']); sys.exit(2)
    d = os.path.join(SITE, a.preview); os.makedirs(d, exist_ok=True)
    json.dump(o, open(os.path.join(d, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(page(o))
    print('✓', d)
