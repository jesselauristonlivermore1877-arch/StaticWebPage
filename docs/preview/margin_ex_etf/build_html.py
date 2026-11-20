# -*- coding: utf-8 -*-
"""把 build_preview.py 的輸出 json 畫成預覽頁（只讀 json，不打網路）
用法：python build_html.py <data.json> <index.html>
"""
import json, sys, html

d = json.load(open(sys.argv[1]))
R = d['rows']
T20 = R[-20:]
last = R[-1]
REF = {'2026-11-19': {'amt': 4457.0, 'chg': -256.72, 'maint': 128.31, 'short': 122448}}   # 附圖（Evans 11-20 給）只有這一列數字可用
import os
_MO = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../data/mkt_overlay.json')))['maint']['twse']
OLD = {r[0]: r[1] for r in _MO['rows']}   # 本站現有維持率（docs/data/mkt_overlay.json maint.twse）
PCT = _MO.get('pct')


def f(v, n=1):
    return f'{v:,.{n}f}'


def sg(v, n=2):
    cls = 'up' if v > 0 else 'dn' if v < 0 else ''
    return f'<span class="{cls}">{"+" if v > 0 else "−" if v < 0 else ""}{f(abs(v), n)}</span>'


def md(s):
    return s[5:].replace('-', '/')


rows = ''.join(
    f'<tr><td>{md(x["date"])}</td><td>{f(x["amt_ex"], 1)}</td><td>{sg(x["chg_ex"]) if "chg_ex" in x else "—"}</td>'
    f'<td>{f(x["maint_ex"], 2)}%</td><td>{f(x["short_ex"], 0)}</td></tr>' for x in reversed(T20))

cmp_rows = ''
for x in R:
    if not ('2026-11-12' <= x['date'] <= '2026-11-19'):
        continue
    ref = REF.get(x['date'])
    cell = lambda a, b, n, u='': (f'{f(a, n)}{u}' + (f'<br><small>附圖 {f(b, n)}{u}・差 {sg(a - b, n)}</small>' if b is not None else ''))
    cmp_rows += (f'<tr><td>{md(x["date"])}</td><td>{cell(x["amt_ex"], ref and ref["amt"], 1)}</td>'
                 f'<td>{cell(x.get("chg_ex", 0), ref and ref["chg"], 2)}</td><td>{cell(x["maint_ex"], ref and ref["maint"], 2, "%")}</td>'
                 f'<td>{cell(x["short_ex"], ref and ref["short"], 0)}</td><td>{f(x["maint_all"], 2)}%</td><td>{OLD.get(x["date"], "—")}</td></tr>')

errs = [abs(x['model_err_pct']) for x in R[-60:]]
err_max, err_avg = max(errs), sum(errs) / len(errs)
e20 = [x['model_err_pct'] for x in T20]
chk_ok = all(x['chk_lots'] == 0 and x['chk_short'] == 0 for x in R)
mx = max(x['maint_ex'] for x in T20); mn = min(x['maint_ex'] for x in T20)

kpi_a = f'''<div class="kpi"><div class="lab">上市融資維持率</div><div class="num">{f(OLD.get(last["date"], last["maint_all"]), 1)}<small>%</small></div>
<div class="sub">本站估算・位於歷史第 {PCT} 百分位</div><div class="sub2">扣除 ETF：<b>{f(last["maint_ex"], 1)}%</b>（融資 {f(last["amt_ex"], 0)} 億）</div></div>'''
kpi_b = f'''<div class="kpi"><div class="lab">上市融資維持率（含 ETF）</div><div class="num">{f(OLD.get(last["date"], last["maint_all"]), 1)}<small>%</small></div><div class="sub">本站估算・位於歷史第 {PCT} 百分位</div></div>
<div class="kpi"><div class="lab">上市融資維持率（扣除 ETF）</div><div class="num">{f(last["maint_ex"], 1)}<small>%</small></div><div class="sub">本站估算・融資 {f(last["amt_ex"], 0)} 億・{md(last["date"])} 單日 {sg(last["chg_ex"])} 億</div></div>'''

page = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>扣除 ETF 資券進出</title><style>
:root{{--bg:#F4F6F4;--card:#fff;--ink:#0F161D;--ink2:#44515E;--line:#DDE3E0;--up:#E5484D;--dn:#12A366;--acc:#B0842F;--raise:#EDF0EE}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#000;--card:#111;--ink:#F5F5F5;--ink2:#A3A3A3;--line:#2A2A2A;--acc:#D9A441;--raise:#1E1E1E}}}}
:root[data-theme="dark"]{{--bg:#000;--card:#111;--ink:#F5F5F5;--ink2:#A3A3A3;--line:#2A2A2A;--acc:#D9A441;--raise:#1E1E1E}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Noto Sans TC","Microsoft JhengHei",sans-serif}}
.w{{max-width:1120px;margin:0 auto;padding:16px}} h1{{font-size:22px;margin:4px 0 10px}} h2{{font-size:18px;margin:0 0 6px}} h3{{font-size:15px;margin:14px 0 6px}}
.n,.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:14px;min-width:0}}
.n ul{{margin:4px 0 0;padding-left:20px}} .m{{color:var(--ink2);font-size:13px}}
.up{{color:var(--up)}} .dn{{color:var(--dn)}}
.ph{{border:1px dashed var(--line);border-radius:8px;padding:28px 12px;text-align:center;color:var(--ink2);font-size:13px;background:var(--raise)}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
th,td{{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}} th:first-child,td:first-child{{text-align:left}}
th{{color:var(--ink2);font-weight:600;font-size:13px;background:var(--raise)}} small{{color:var(--ink2);font-size:12px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(240px,100%),1fr));gap:10px}}
.kpi{{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--raise)}} .kpi .lab{{font-size:13px;color:var(--ink2)}}
.kpi .num{{font-size:28px;font-weight:700;line-height:1.2}} .kpi .num small{{font-size:14px;color:var(--ink2);margin-left:2px}} .kpi .sub{{font-size:12px;color:var(--ink2)}}
.kpi .sub2{{font-size:13px;margin-top:4px;padding-top:4px;border-top:1px dashed var(--line)}}
.opt{{display:inline-block;background:var(--acc);color:#fff;border-radius:6px;padding:0 8px;font-size:13px;margin-right:6px}}
.foot{{font-size:12px;color:var(--ink2);margin-top:8px;overflow-wrap:anywhere}}
</style></head><body><div class="w"><h1>上市台股扣除 ETF 資券進出（預覽）</h1>
<div class="n"><b>要看的重點</b><ul>
<li>位置：籌碼組「融資×指數＋市場體感」頁籤，第一張「上市融資維持率 × 加權指數」圖下面，加一張近 20 個交易日的表（下面第 1 段）</li>
<li>維持率卡要不要多一個「扣除 ETF」數字：第 2 段有 A、B 兩種版面請選</li>
<li>融資張數、融券張數是證交所逐檔加總，不是估算；<b>融資金額扣除 ETF 是本站估算</b>（證交所只公布全市場融資金額，不分股票／ETF），算法與誤差寫在第 3 段</li>
<li>跟附圖比：11/19 融券 122,448 張完全一致；融資金額與維持率對不上，原因寫在第 3 段，沒有硬湊</li></ul></div>

<div class="card"><h2>① 表格放在圖下面</h2>
<div class="ph">（正式頁這裡是「上市融資維持率 × 加權指數」圖，預覽不重畫）</div>
<h3>近 20 個交易日 上市資券進出（扣除 ETF）</h3>
<div class="tw"><table><thead><tr><th>日期</th><th>融資餘額（億）</th><th>融資增減（億）</th><th>融資維持率</th><th>融券餘額（張）</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="foot">扣除 ETF＝排除代號 00 開頭的證券（與證交所 MI_MARGN「ETF」類別合計一致）。融資增減紅＝增加、綠＝減少。融資餘額（億）與維持率為<b>本站估算</b>：融資金額＝證交所公布上市全市場融資金額 − ETF 融資金額估算；維持率＝Σ 股票融資張數 × 1000 × 收盤 ÷ 扣除 ETF 融資金額。融券餘額＝證交所逐檔融券今日餘額加總。資料來源：證交所 MI_MARGN、MI_INDEX。近 20 日最高 {f(mx, 2)}%、最低 {f(mn, 2)}%。<b>歷史統計，非預測，不構成買賣建議。</b></div></div>

<div class="card"><h2>② 維持率卡：兩種版面</h2>
<p><span class="opt">A</span>原卡不動，下面多一行「扣除 ETF」</p><div class="kpis">{kpi_a}</div>
<p style="margin-top:16px"><span class="opt">B</span>拆成兩張卡並排（含 ETF／扣除 ETF）</p><div class="kpis">{kpi_b}</div>
<div class="foot">卡上「含 ETF」數字沿用正式頁現值（{md(last["date"])} {OLD.get(last["date"])}%）。注意第 3 段：現值的分子只有股票、分母含 ETF，口徑不一致；若照同一算法把 ETF 市值也算進分子，{md(last["date"])} 是 {f(last["maint_all"], 2)}%。要不要一起修，請 Evans 決定。</div></div>

<div class="card"><h2>③ 核對：11/12～11/19 本站算的值 vs 附圖</h2>
<div class="tw"><table><thead><tr><th>日期</th><th>扣 ETF 融資（億）</th><th>增減（億）</th><th>扣 ETF 維持率</th><th>扣 ETF 融券（張）</th><th>含 ETF 維持率（同口徑）</th><th>本站現值</th></tr></thead><tbody>{cmp_rows}</tbody></table></div>
<div class="foot">附圖只拿到 11/19 這一列數字（附圖原檔在 CustomerServiceANDSales/_inbox，這個雲端窗沒有權限讀，11/12～11/18 待補比對）。</div>
<h3>差在哪</h3><ul>
<li><b>融券張數</b>：11/19 本站 {f(REF["2026-11-19"]["short"], 0)} 張＝附圖，一致（＝證交所 MI_MARGN「股票」類別合計）。</li>
<li><b>融資金額</b>：證交所不分類公布融資金額，扣 ETF 一定是估的。本站估 ETF 融資 {f([x for x in R if x["date"]=="2026-11-19"][0]["etf_amt_est"], 1)} 億；附圖隱含 ETF 融資 {f(4843.68 - 4457, 1)} 億（全市場 4,843.7 − 4,457）。附圖用什麼估法不知道。</li>
<li><b>維持率</b>：附圖 128.31% × 4,457 億＝股票融資市值約 5,719 億，但 11/19 證交所逐檔張數 × 證交所收盤＝6,606.9 億（差 888 億）。試過：前一日收盤、隔日（11/20）收盤、前一日張數，都對不上 128.31%；附圖分子的算法查不出來，照實寫。</li>
<li><b>本站估算的驗證</b>：同一套逐檔追蹤算法套在全部證券上，跟證交所公布的全市場融資金額比，近 60 日誤差絕對值平均 {f(err_avg, 2)}%、最大 {f(err_max, 2)}%；近 20 日 {f(min(e20), 2)}%～{f(max(e20), 2)}%。張數核對（股票＋ETF＝全市場）{"每天都一致" if chk_ok else "有對不上的日子"}。</li>
<li><b>本站現有維持率</b>（{md(last["date"])} {OLD.get(last["date"])}%）：分子用逐檔資料庫（只有股票、沒有 ETF），分母用全市場融資金額（含 ETF），所以偏低；這也是頁面上「比櫃買官方平均低 7 個百分點」的一部分原因。</li></ul></div>

<div class="foot">本站估算。口徑：上市、扣除代號 00 開頭的 ETF。資料來源：臺灣證券交易所 MI_MARGN（融資融券彙總、信用交易統計）、MI_INDEX（每日收盤行情）。融資金額扣除 ETF 為估算（逐檔追蹤：舊部位依剩餘張數保留、當日新買進按成交均價 × 60% 加入）。歷史統計，非預測，不構成買賣建議。產生程式：本資料夾 build_preview.py、build_html.py（預覽，不連正式網站）。</div>
</div></body></html>'''
open(sys.argv[2], 'w').write(page)
print('寫出', sys.argv[2])
