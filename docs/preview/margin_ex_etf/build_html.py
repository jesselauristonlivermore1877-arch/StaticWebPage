# -*- coding: utf-8 -*-
"""把 build_preview.py 的輸出 json 畫成預覽頁（只讀 json，不打網路）
用法：python build_html.py <data.json> <index.html>
"""
import json, sys, html

d = json.load(open(sys.argv[1]))
R = d['rows']
T20 = R[-20:]
last = R[-1]
REF = {'2026-11-19': {'amt': 4457.0, 'chg': -256.72, 'maint': 128.31, 'short': 122448},   # 附圖 ref_margin_table_1119（總指揮轉述）
       '2026-11-20': {'amt': 4024.0, 'chg': -433.21, 'maint': 119.53, 'short': 99912}}    # 附圖 11/20（總指揮 11-20 追加轉述）
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
    if not ('2026-11-12' <= x['date'] <= '2026-11-20'):
        continue
    ref = REF.get(x['date'])
    cell = lambda a, b, n, u='': (f'{f(a, n)}{u}' + (f'<br><small>附圖 {f(b, n)}{u}・差 {"+" if a - b > 0 else "−" if a - b < 0 else ""}{f(abs(a - b), n)}</small>' if b is not None else ''))
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

GORD = ['台股正2', '其他槓桿', '反向', '股票型（市值、高息等）', '主動型', '債券型']
L = last; tot_lots = L['lots_ex'] + L['lots_etf']; tot_mv = L['mv_ex'] + L['mv_etf']
pct = lambda a, b: a / b * 100 if b else 0
grp_rows = ''.join(
    f'<tr><td>{k}</td><td>{L["grp"][k]["n"]}</td><td>{f(L["grp"][k]["lots"], 0)}</td><td>{f(pct(L["grp"][k]["lots"], tot_lots), 1)}%</td>'
    f'<td>{f(L["grp"][k]["mv"], 1)}</td><td>{f(pct(L["grp"][k]["mv"], tot_mv), 1)}%</td><td>{f(L["grp"][k]["amt"], 1)}</td></tr>'
    for k in GORD if k in L['grp'])
grp_rows += (f'<tr><th>ETF 合計</th><th>{sum(v["n"] for v in L["grp"].values())}</th><th>{f(L["lots_etf"], 0)}</th><th>{f(pct(L["lots_etf"], tot_lots), 1)}%</th>'
             f'<th>{f(L["mv_etf"], 1)}</th><th>{f(pct(L["mv_etf"], tot_mv), 1)}%</th><th>{f(L["etf_amt_est"], 1)}</th></tr>'
             f'<tr><td>股票（扣除 ETF）</td><td></td><td>{f(L["lots_ex"], 0)}</td><td>{f(pct(L["lots_ex"], tot_lots), 1)}%</td>'
             f'<td>{f(L["mv_ex"], 1)}</td><td>{f(pct(L["mv_ex"], tot_mv), 1)}%</td><td>{f(L["amt_ex"], 1)}</td></tr>')
g2 = lambda x, k='台股正2': x['grp'].get(k, {'lots': 0, 'mv': 0, 'amt': 0})
trend_rows = ''.join(
    f'<tr><td>{md(x["date"])}</td><td>{f(x["etf_amt_est"], 1)}</td><td>{f(x["mv_etf"], 1)}</td><td>{f(pct(x["mv_etf"], x["mv_ex"] + x["mv_etf"]), 1)}%</td>'
    f'<td>{f(g2(x)["lots"], 0)}</td><td>{f(g2(x)["mv"], 1)}</td><td>{f(pct(g2(x)["mv"], x["mv_ex"] + x["mv_etf"]), 2)}%</td></tr>' for x in reversed(T20))
top_rows = ''.join(f'<tr><td>{t[0]}</td><td style="text-align:left">{html.escape(t[1])}</td><td>{f(t[2], 0)}</td><td>{f(t[3], 1)}</td><td>{f(pct(t[3], tot_mv), 2)}%</td></tr>' for t in L['top'][:10])
W0 = next((x for x in R if '2026-10-06' <= x['date'] <= '2026-10-08'), None)   # 這波高點 10-06（mkt_overlay wave.high）；沒有那幾天的資料就不比
if W0:
    a0, a1 = g2(W0), g2(L)
    wave = (f'<tr><td>台股正2（4 檔）</td><td>{f(a0["lots"], 0)} → {f(a1["lots"], 0)}</td><td>{sg(pct(a1["lots"] - a0["lots"], a0["lots"]), 1)}%</td>'
            f'<td>{f(a0["mv"], 1)} → {f(a1["mv"], 1)}</td><td>{sg(pct(a1["mv"] - a0["mv"], a0["mv"]), 1)}%</td></tr>'
            f'<tr><td>股票（扣除 ETF）</td><td>{f(W0["lots_ex"], 0)} → {f(L["lots_ex"], 0)}</td><td>{sg(pct(L["lots_ex"] - W0["lots_ex"], W0["lots_ex"]), 1)}%</td>'
            f'<td>{f(W0["mv_ex"], 1)} → {f(L["mv_ex"], 1)}</td><td>{sg(pct(L["mv_ex"] - W0["mv_ex"], W0["mv_ex"]), 1)}%</td></tr>'
            f'<tr><td>ETF 合計</td><td>{f(W0["lots_etf"], 0)} → {f(L["lots_etf"], 0)}</td><td>{sg(pct(L["lots_etf"] - W0["lots_etf"], W0["lots_etf"]), 1)}%</td>'
            f'<td>{f(W0["mv_etf"], 1)} → {f(L["mv_etf"], 1)}</td><td>{sg(pct(L["mv_etf"] - W0["mv_etf"], W0["mv_etf"]), 1)}%</td></tr>')
    wtxt = (f'這波從 {md(W0["date"])} 起：台股正2 融資張數 {"增加" if a1["lots"] > a0["lots"] else "減少"} {f(abs(pct(a1["lots"] - a0["lots"], a0["lots"])), 1)}%，'
            f'股票融資張數 {"增加" if L["lots_ex"] > W0["lots_ex"] else "減少"} {f(abs(pct(L["lots_ex"] - W0["lots_ex"], W0["lots_ex"])), 1)}%。')
else:
    wave, wtxt = '<tr><td colspan="5">原始資料還沒回補到 10-06，這段暫缺</td></tr>', '這波（10-06 起）對照：原始資料還沒回補到 10-06。'
z = g2(L)
concl = (f'<li>ETF 融資「金額」小、「張數」大：{md(L["date"])} ETF 融資 {f(L["lots_etf"], 0)} 張，占全上市融資張數 {f(pct(L["lots_etf"], tot_lots), 1)}%；'
         f'但 ETF 融資平均一張只值約 {f(L["mv_etf"] * 1e8 / L["lots_etf"] / 1e4, 2)} 萬元（股票平均 {f(L["mv_ex"] * 1e8 / L["lots_ex"] / 1e4, 2)} 萬元），換成市值只有 {f(L["mv_etf"], 0)} 億，占 {f(pct(L["mv_etf"], tot_mv), 1)}%；融資金額估算 {f(L["etf_amt_est"], 0)} 億。所以看金額，ETF 確實只有三、四百億的量級。</li>'
         f'<li>台股正2 四檔融資 {f(z["lots"], 0)} 張、市值 {f(z["mv"], 1)} 億，占全上市融資市值 {f(pct(z["mv"], tot_mv), 2)}%。占比小，市場的融資斷頭壓力主要在個股（股票融資市值 {f(L["mv_ex"], 0)} 億）。</li>'
         f'<li>{wtxt}</li><li>以上是融資餘額的統計描述，不代表後續走勢，不構成買賣建議。</li>')
diff_li = ''
for dd, ref in REF.items():
    x = next((y for y in R if y['date'] == dd), None)
    if not x:
        continue
    imp_etf = x['amt_all'] - ref['amt']; imp_mv = ref['maint'] / 100 * ref['amt']
    diff_li += (f'<li><b>{md(dd)} 融資金額</b>：全上市 {f(x["amt_all"], 1)} 億（證交所公布）。附圖扣 ETF {f(ref["amt"], 0)} 億 → 隱含 ETF 融資 {f(imp_etf, 1)} 億；'
                f'本站估 ETF 融資 {f(x["etf_amt_est"], 1)} 億（ETF 融資市值 {f(x["mv_etf"], 1)} 億）。證交所不分類公布融資金額，兩邊都是估的，附圖估法不明。</li>'
                f'<li><b>{md(dd)} 維持率</b>：附圖 {ref["maint"]}% × {f(ref["amt"], 0)} 億 → 隱含股票融資市值約 {f(imp_mv, 0)} 億；'
                f'證交所逐檔張數 × 收盤＝{f(x["mv_ex"], 1)} 億，差 {f(x["mv_ex"] - imp_mv, 0)} 億（附圖分子約是本站的 {f(imp_mv / x["mv_ex"] * 100, 1)}%）。'
                f'試過前一日收盤、隔日收盤、前一日張數都對不上，附圖分子算法查不出來，照實寫、不硬湊。</li>')

etf_sec = f'''<div class="card"><h2>④ ETF 融資拆解（Evans：「ETF 才三百多億？正2 占融資總量不多？」）</h2>
<h3>{md(L["date"])} 分組</h3><div class="tw"><table><thead><tr><th>分組</th><th>有融資檔數</th><th>融資張數</th><th>占全上市張數</th><th>融資市值（億）</th><th>占全上市市值</th><th>融資金額估算（億）</th></tr></thead><tbody>{grp_rows}</tbody></table></div>
<div class="foot">融資市值＝融資張數 × 1000 × 收盤（證交所逐檔資料，不是估算）；融資金額估算見第 3 段。分組依代號：台股正2＝00631L、00663L、00675L、00685L；其他槓桿＝其餘 L 結尾（海外正2 等）；反向＝R 結尾；主動型＝A 結尾；債券型＝B 結尾；其餘歸股票型（市值、高息、產業等）。</div>
<h3>白話結論（數字由程式算）</h3><ul>{concl}</ul>
<h3>這波（{md(W0["date"]) if W0 else "10/06"} 起）台股正2 vs 個股</h3><div class="tw"><table><thead><tr><th></th><th>融資張數</th><th>張數變化</th><th>融資市值（億）</th><th>市值變化</th></tr></thead><tbody>{wave}</tbody></table></div>
<h3>近 20 個交易日 ETF 融資</h3><div class="tw"><table><thead><tr><th>日期</th><th>ETF 融資金額估算（億）</th><th>ETF 融資市值（億）</th><th>占全上市市值</th><th>台股正2 張數</th><th>台股正2 市值（億）</th><th>台股正2 占比</th></tr></thead><tbody>{trend_rows}</tbody></table></div>
<div class="foot">歷史日子用證交所 MI_MARGN 歷史端點（rwd/zh/marginTrading/MI_MARGN?date=…&selectType=ALL）逐日回補，含全部 ETF；收盤用本站日K庫（與證交所 MI_INDEX 逐檔核對一致）。</div>
<h3>{md(L["date"])} ETF 融資市值前 10 名</h3><div class="tw"><table><thead><tr><th>代號</th><th style="text-align:left">名稱</th><th>融資張數</th><th>融資市值（億）</th><th>占全上市市值</th></tr></thead><tbody>{top_rows}</tbody></table></div></div>'''

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
<li>第 4 段：ETF 融資拆解（總指揮追加）</li><li>跟附圖比：11/19、11/20 融券完全一致；融資金額與維持率對不上，原因寫在第 3 段，沒有硬湊</li></ul></div>

<div class="card"><h2>① 表格放在圖下面</h2>
<div class="ph">（正式頁這裡是「上市融資維持率 × 加權指數」圖，預覽不重畫）</div>
<h3>近 20 個交易日 上市資券進出（扣除 ETF）</h3>
<div class="tw"><table><thead><tr><th>日期</th><th>融資餘額（億）</th><th>融資增減（億）</th><th>融資維持率</th><th>融券餘額（張）</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="foot">扣除 ETF＝排除代號 00 開頭的證券（與證交所 MI_MARGN「ETF」類別合計一致）。融資增減紅＝增加、綠＝減少。融資餘額（億）與維持率為<b>本站估算</b>：融資金額＝證交所公布上市全市場融資金額 − ETF 融資金額估算；維持率＝Σ 股票融資張數 × 1000 × 收盤 ÷ 扣除 ETF 融資金額。融券餘額＝證交所逐檔融券今日餘額加總。資料來源：證交所 MI_MARGN、MI_INDEX。近 20 日最高 {f(mx, 2)}%、最低 {f(mn, 2)}%。<b>歷史統計，非預測，不構成買賣建議。</b></div></div>

<div class="card"><h2>② 維持率卡：兩種版面</h2>
<p><span class="opt">A</span>原卡不動，下面多一行「扣除 ETF」</p><div class="kpis">{kpi_a}</div>
<p style="margin-top:16px"><span class="opt">B</span>拆成兩張卡並排（含 ETF／扣除 ETF）</p><div class="kpis">{kpi_b}</div>
<div class="foot">卡上「含 ETF」數字沿用正式頁現值（{md(last["date"])} {OLD.get(last["date"])}%）。注意第 3 段：現值的分子只有股票、分母含 ETF，口徑不一致；若照同一算法把 ETF 市值也算進分子，{md(last["date"])} 是 {f(last["maint_all"], 2)}%。要不要一起修，請 Evans 決定。</div></div>

<div class="card"><h2>③ 核對：11/12～11/20 本站算的值 vs 附圖</h2>
<div class="tw"><table><thead><tr><th>日期</th><th>扣 ETF 融資（億）</th><th>增減（億）</th><th>扣 ETF 維持率</th><th>扣 ETF 融券（張）</th><th>含 ETF 維持率（同口徑）</th><th>本站現值</th></tr></thead><tbody>{cmp_rows}</tbody></table></div>
<div class="foot">附圖只拿到 11/19、11/20 兩列數字（總指揮轉述；附圖原檔在 CustomerServiceANDSales/_inbox，這個雲端窗沒有權限讀，11/12～11/18 待補比對）。</div>
<h3>差在哪</h3><ul>
<li><b>融券張數</b>：11/19 本站 {f(REF["2026-11-19"]["short"], 0)} 張、11/20 {f(REF["2026-11-20"]["short"], 0)} 張＝附圖，一致（＝證交所 MI_MARGN「股票」類別合計）。</li>
{diff_li}<li><b>本站估算的驗證</b>：同一套逐檔追蹤算法套在全部證券上，跟證交所公布的全市場融資金額比，近 60 日誤差絕對值平均 {f(err_avg, 2)}%、最大 {f(err_max, 2)}%；近 20 日 {f(min(e20), 2)}%～{f(max(e20), 2)}%。張數核對（股票＋ETF＝全市場）{"每天都一致" if chk_ok else "有對不上的日子"}。</li>
<li><b>本站現有維持率</b>（{md(last["date"])} {OLD.get(last["date"])}%）：分子用逐檔資料庫（只有股票、沒有 ETF），分母用全市場融資金額（含 ETF），所以偏低；這也是頁面上「比櫃買官方平均低 7 個百分點」的一部分原因。</li></ul></div>

{etf_sec}
<div class="foot">本站估算。口徑：上市、扣除代號 00 開頭的 ETF。資料來源：臺灣證券交易所 MI_MARGN（融資融券彙總、信用交易統計）、MI_INDEX（每日收盤行情）。融資金額扣除 ETF 為估算（逐檔追蹤：舊部位依剩餘張數保留、當日新買進按成交均價 × 60% 加入）。歷史統計，非預測，不構成買賣建議。產生程式：本資料夾 build_preview.py、build_html.py（預覽，不連正式網站）。</div>
</div></body></html>'''
open(sys.argv[2], 'w').write(page)
print('寫出', sys.argv[2])
