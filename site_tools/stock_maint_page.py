# -*- coding: utf-8 -*-
"""個股／族群融資維持率頁面（讀 stock_maint.py 的 data.json → index.html；不打網路）
由 site_tools/stock_maint.py 呼叫；也可單獨跑：python site_tools/stock_maint_page.py <data.json> <index.html>
"""
import json, sys, html, re

MKT_NAME = {'twse': '上市', 'otc': '上櫃'}


def f(v, n=1):
    return '—' if v is None else f'{v:,.{n}f}'


def md(s):
    return s[5:].replace('-', '/') if s else '—'


def ver_block(d):
    """驗證結果（頁面第一段，照實寫）"""
    out = []
    for m, nm in MKT_NAME.items():
        x = d['mkts'][m]; s = x['summary']
        cal = [c for c in x['cal'] if c['k_raw'] is not None]
        if s.get('bal_match') is not None:
            v1 = (f'margin_full 逐檔重算：{x["n_full"]} 個交易日，融資餘額張數與本站 margin.npz 一致率 {s["bal_match"]}%'
                  f'（不一致 {s["bal_diff"]} 筆）；「前日餘額＋買進−賣出−現金償還≠今日餘額」{s["flow_bad"]} 筆；'
                  f'最後一天「真的買進」累推 vs「餘額變化近似」累推，全市場合計差 {f(s.get("real_vs_approx_pct"), 2)}%')
        else:
            v1 = ('<b>尚未驗證</b>：證交所／櫃買逐檔「融資買進」（data/margin_full）回補還沒進 repo，'
                  '目前全部用退路「買進≈max(今日餘額−昨日餘額, 0)」累推；資料進來後重跑本程式就會自動改用真的買進並填上這一條')
        if cal:
            v2 = (f'可校準日 {s["n_cal_days"]} 天（要同時有官方融資金額與 ETF 逐檔）。用前一個校準日的成數推今天：'
                  f'{s["within2"]}/{s["n_pred"]} 天誤差 &lt; 2%，近 20 個校準日最大誤差 <b>{f(s["err20_max"], 2)}%</b>，'
                  f'最近一天 {f(s["err_pred_last"], 2)}%；不校準（直接套 {int(x["r0"] * 10)} 成）最近一天差 {f(s["err_r0_last"], 1)}%。'
                  f'目前校準後實際平均成數約 <b>{f(s["ratio"] * 100, 1)}%</b>（{md(s["k_from"])} 校準）')
            # 近 20 個校準日超標的日子逐一寫明（含官方金額單日變化），照實標示、不另設例外
            c20 = cal[-20:]
            bad = []
            for i, c in enumerate(c20):
                e = c.get('err_pred')
                if e is not None and abs(e) >= 2:
                    j = cal.index(c)
                    chg = (c['official'] / cal[j - 1]['official'] - 1) * 100 if j > 0 and cal[j - 1]['official'] else None
                    bad.append(f'{md(c["date"])}（誤差 {f(e, 2)}%' + (f'，官方{nm}融資金額單日 {f(chg, 1)}%' if chg is not None else '') + '）')
            if bad:
                n_ok = sum(1 for c in c20 if c.get('err_pred') is not None and abs(c['err_pred']) < 2)
                n_all = sum(1 for c in c20 if c.get('err_pred') is not None)
                v2 += (f'。<b>近 20 個校準日 {n_ok}/{n_all} 天 &lt; 2%，超標的是：{"、".join(bad)}</b>；'
                       '照實標「未過」，不改門檻、不設急跌例外，之後每天自動重算')
        else:
            v2 = '尚無可校準日'
        ok = (s.get('bal_match') or 0) >= 99.9 and (s['err20_max'] or 99) < 2
        out.append(f'<div class="hi"><div class="ht"><b>{nm}</b><span class="tag {"ok" if ok else "ng"}">{"兩條都過" if ok else ("②未過" if (s.get("bal_match") or 0) >= 99.9 and cal else "未過／未驗")}</span></div>'
                   f'<div class="hm">① 另一份原始資料重算：{v1}</div><div class="hm">② 全市場推估合計 vs 官方融資金額：{v2}</div></div>')
    return '<div class="how">' + ''.join(out) + '</div>'


def skip_note(d):
    out = ''
    for m, nm in MKT_NAME.items():
        sk = d['mkts'][m].get('skipped') or []
        if sk:
            out += (f'{nm}本站日K 有 {len(sk)} 天缺（覆蓋不到一半，最近：{"、".join(md(x) for x in sk[-3:])}），這些日子不當交易日、'
                    f'當天的融資買進併入下一個交易日；{nm}資料日為 {md(d["mkts"][m]["date"])}。')
    return out


def ca_block(d):
    rows = ''
    for m, nm in MKT_NAME.items():
        for c, n, k, ed, td, fct, pb, b in d['mkts'][m].get('ca', []):
            if pb:
                rows += f'<tr><td>{nm} {html.escape(c)}</td><td class="l">{html.escape(n)}</td><td class="l">{k}</td><td>{md(td)}</td><td>×{fct:g}</td><td>{f(pb, 0)}</td><td>{f(b, 0)}</td></tr>'
    n_all = sum(len(d['mkts'][m].get('ca', [])) for m in MKT_NAME)
    return ('<details class="card"><summary>減資／面額變更調整紀錄</summary><div class="in">'
            f'<p class="m">資料期間共 {n_all} 件減資、面額變更（來源 data/corp_actions.json），下表列出事件前一日仍有融資餘額的股票；其餘當天融資已歸零，不影響推估。</p>'
            '<div class="tw"><table><thead><tr><th>股票</th><th class="l">名稱</th><th class="l">事件</th><th>生效日</th><th>張數換算</th><th>前一日張數</th><th>當天張數</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></div></details>')


def off_block(d):
    c = d.get('off_cmp') or {}
    if not c.get('n'):
        return ''
    mon = '、'.join(f'{k}：{v:+.2f}%' for k, v in c['monthly'].items())
    return ('<details class="card"><summary>上市官方融資金額：兩份資料比對</summary><div class="in"><p class="m">'
            '上市融資金額優先用證交所逐日公布值（data/margin_amt_hist.json）；那份沒有的日子（'
            f'{md(c["only_overlay"][0]) if c["only_overlay"] else "—"} 起共 {len(c["only_overlay"])} 天）才用本站維持率資料檔（docs/data/mkt_overlay.json）的融資金額。'
            f'兩份重疊 {c["n"]} 天（{md(c["start"])}～{md(c["end"])}）：差異超過 0.1% 的有 {c["n_gt01"]} 天，從 {md(c["first_gt01"]) if c["first_gt01"] else "—"} 開始；'
            f'最大差 {c["max_pct"]:+.2f}%（{md(c["max_date"])}），平均 {c["mean_abs"]:.2f}%；最近一個重疊日 {md(c["last_date"])} 差 {c["last_pct"]:+.2f}%。各月最大差：{mon}。</p></div></details>')


def cal_table(d, m):
    x = d['mkts'][m]
    cal = [c for c in x['cal'] if c['k_raw'] is not None][-20:]
    if not cal:
        return '<p class="m">尚無可校準日。</p>'
    tr = ''.join(f'<tr><td>{md(c["date"])}</td><td>{f(c["official"], 1)}</td><td>{f(c["sumV"], 1)}</td><td>{f(c["err_r0"], 2)}%</td>'
                 f'<td>{f(c["k_raw"] * x["r0"] * 100, 1)}%</td><td>{f(c["err_pred"], 2) + "%" if c["err_pred"] is not None else "—"}</td></tr>'
                 for c in reversed(cal))
    return ('<div class="tw"><table><thead><tr><th>日期</th><th>官方融資金額（億）</th>'
            f'<th>累推合計（{int(x["r0"] * 10)} 成，億）</th><th>不校準誤差</th><th>校準後成數</th><th>前日成數推今日誤差</th></tr></thead>'
            f'<tbody>{tr}</tbody></table></div>')


def fail_mkts(d):
    """沒過驗證的市場名稱（11-21 雲端新19：頁籤標「上櫃驗證未過」，不只寫「驗證未過」）"""
    return [nm for m, nm in MKT_NAME.items() if not ((d['mkts'][m]['summary'].get('bal_match') or 0) >= 99.9 and (d['mkts'][m]['summary']['err20_max'] or 99) < 2)]


def passed(d):
    return all((d['mkts'][m]['summary'].get('bal_match') or 0) >= 99.9 and (d['mkts'][m]['summary']['err20_max'] or 99) < 2 for m in MKT_NAME)


def legal_block(d):
    """白話：為什麼以法定成數計會低估維持率、本站怎麼回推實際成數、限制（Evans 11-21 裁示 4）。數字全由程式帶入"""
    li = []
    for m, nm in MKT_NAME.items():
        x = d['mkts'][m]; c = next((y for y in reversed(x['cal']) if y['official'] and y['k_raw'] is not None), None)
        if not c:
            continue
        li.append(f'{nm} {md(c["date"])}：全部證券照法定 {int(x["r0"] * 10)} 成累推，融資金額合計約 {f(c["sumV"], 0)} 億，'
                  f'但{"證交所" if m == "twse" else "櫃買中心"}公布的融資總金額只有 {f(c["official"], 0)} 億（{"多" if c["sumV"] >= c["official"] else "少"}約 {f(abs(c["sumV"] / c["official"] - 1) * 100, 1)}%）'
                  f'→ 回推實際平均成數約 {f(c["ratio"] * 100, 1)}%（＝{int(x["r0"] * 10)} 成 × {f(c["official"], 0)} ÷ {f(c["sumV"], 0)}）')
    return ('<div class="card"><h2>為什麼本站維持率比「以法定成數計」高</h2><ul class="m" style="padding-left:20px;margin:4px 0">'
            '<li>官方只公布全市場融資總金額，不公布每一檔借了多少錢，所以各家都要自己推估。常見做法是假設每筆融資都借到法定上限（上市 6 成、上櫃 5 成）。'
            '但券商實際常只借 4、5 成，借得少 → 欠款少 → 維持率其實比較高；照上限算會把欠款算多、維持率算低。</li>'
            + ''.join(f'<li>{t}。</li>' for t in li) +
            '<li>本站主數字用這個回推出來的實際平均成數（逐日校準，上市、上櫃分開，股票和 ETF 同一個成數），所以加總起來剛好等於官方融資總金額；'
            '個股／ETF 表另附「以法定成數計」一欄（不校準），方便跟其他來源對照：主數字 ＝ 以法定成數計 × 法定成數 ÷ 實際平均成數。</li>'
            '<li><b>限制</b>：實際平均成數是全市場平均值，每家券商、每個客戶借的成數都不同；某一檔股票的融資戶如果多半借滿上限，'
            '真實維持率會比本站主數字低、接近「以法定成數計」那一欄。兩欄都是推估，可以當範圍看。</li></ul></div>')


def help_html(d):
    """「說明與驗證」整段（預覽頁與網站「籌碼 → 維持率」共用同一段；網站版由 public() 加 mt- 前綴）"""
    tw = d['mkts']['twse']; ot = d['mkts']['otc']
    nfull = tw['n_full'] + ot['n_full']
    traces = ''
    for m, nm in MKT_NAME.items():
        for t in d['mkts'][m]['traces']:
            tr = ''.join(f'<tr><td>{md(s["date"])}</td><td>{f(s["prev"], 0)}</td><td>{f(s["bal"], 0)}</td>'
                         f'<td>{f(s["buy"], 0) if s["buy"] is not None else "—"}</td><td>{f(s["buy_approx"], 0)}</td>'
                         f'<td>{f(s["avgp"], 2)}</td><td>{f(s["close"], 2)}</td><td>{f(s["V"], 2)}</td><td>{f(s["amt"], 2)}</td>'
                         f'<td>{f(s["maint"], 1)}%</td><td>{"重起" if s["restart"] else ""}</td></tr>' for s in t['steps'])
            traces += (f'<details><summary>{nm} {html.escape(t["code"])} {html.escape(t["name"])}</summary><div class="tw"><table><thead><tr>'
                       '<th>日期</th><th>昨日餘額</th><th>今日餘額</th><th>真的買進</th><th>近似買進</th><th>均價</th><th>收盤</th>'
                       '<th>累推（百萬，法規成數）</th><th>推估金額（百萬）</th><th>推估維持率</th><th></th></tr></thead>'
                       f'<tbody>{tr}</tbody></table></div></details>')
    return f'''{legal_block(d)}<div class="card"><h2>驗證結果（照實寫）</h2>{ver_block(d)}
<p class="m">{skip_note(d)}{"" if nfull else "目前 margin_full（逐檔融資買進）還沒進 repo，上市 ETF 逐檔只有 7/16～8/25 與 11/11～11/20 零星日子、上櫃只有 11/19～11/20，所以能校準的日子很少；回補進來後重跑即更新。"}</p></div>
<details class="card"><summary>怎麼算（本站推估）</summary><div class="in"><ol class="m" style="padding-left:20px;margin:4px 0">
<li>證交所、櫃買不公布個股融資金額，本站逐檔逐日累推：今日金額＝昨日金額 ×（今日餘額 − 今日買進）÷ 昨日餘額 ＋ 今日買進張數 × 1000 × 當日均價（成交金額 ÷ 成交股數）× 成數；起點（{md(tw["start"])}）＝ 餘額 × 1000 × 收盤 × 成數。</li>
<li>「今日買進」有證交所／櫃買逐檔融資買進的日子用真的買進；沒有的日子用退路：買進 ≈ max(今日餘額 − 昨日餘額, 0)（會低估週轉，下跌時推估成本偏高、維持率偏低）。</li>
<li><b>成數為本站校準推估</b>：法規上限上市 6 成、上櫃 5 成，但券商可只借 4、3 成，所以先用 6／5 成累推，再用證交所／櫃買公布的融資總金額（含 ETF，分子也含 ETF）逐日校準出「實際平均成數」，套回各股。上市目前約 {f(tw["summary"]["ratio"] * 100, 1)}%、上櫃約 {f(ot["summary"]["ratio"] * 100, 1)}%。</li>
<li>個股推估維持率＝融資張數 × 1000 × 收盤 ÷ 推估融資金額；「再跌幾 % 到追繳門檻」＝（維持率 − 門檻）÷ 維持率；門檻依資料日（證交所 115/11/23 公告：11/24 起 120%，之前 130%）。族群維持率＝族群融資市值合計 ÷ 族群推估金額合計。</li>
<li><b>ETF</b>：跟股票同一套（逐檔累推、同一個校準成數），全部 ETF 推估金額合計＝市場動態「上市融資維持率」卡「扣除 ETF」用的 ETF 融資金額，卡、「大盤」、個股／ETF 表三處同一份數字；ETF 推估維持率＝融資張數 × 1000 × 收盤 ÷ ETF 推估融資金額。分組：主動式＝代號 A、D、T 結尾；被動式再分台股正2（00631L、00663L、00675L、00685L）、其他槓桿（其餘 L 結尾）、反向（R）、債券（B）、期貨商品（U）、市值高息等（其餘）。</li>
<li>減資、面額變更：生效當天證交所／櫃買會把融資張數換算（例：面額變更 1 換 4 張），本站先把前一日張數照比例換算再累推，不當成買賣；融資金額不變。配股：融資張數不會調整、融資金額也不變，所以不調整（配到的股票不在融資擔保品裡）。現金股利不調整。</li><li>已知限制：新上市／斷檔後重新起算時，成本先以當天收盤代入；沒有逐檔融資買進資料的日子用退路（買進 ≈ 餘額增加量）。</li></ol></div></details>{ca_block(d)}{off_block(d)}
<details class="card"><summary>校準紀錄（近 20 個校準日）</summary><div class="in"><p class="m">上市</p>{cal_table(d, "twse")}<p class="m">上櫃</p>{cal_table(d, "otc")}</div></details>
<details class="card"><summary>抽樣 5 檔逐日累推過程（前 3 天＋最後 3 天）</summary><div class="in">{traces}</div></details>
<p class="foot">資料：證交所 MI_MARGN、櫃買融資融券餘額（逐檔融資張數）、本站日K（收盤、成交金額、成交股數）、證交所／櫃買公布融資金額。資料日：上市 {md(tw["date"])}、上櫃 {md(ot["date"])}。<b>歷史統計，非預測，不構成買賣建議。</b></p>
'''


def build(d):
    tw = d['mkts']['twse']; ot = d['mkts']['otc']
    cl = tw.get('call', 130.0)   # 🔴 11-23 雲端舊34：追繳門檻依資料日
    payload = {m: {'date': d['mkts'][m]['date'], 'rows': d['mkts'][m]['rows'], 'sec': d['mkts'][m]['sectors'],
                   'ratio': d['mkts'][m]['summary']['ratio']} for m in MKT_NAME}
    js_data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    nfull = tw['n_full'] + ot['n_full']
    pz = passed(d)
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>個股融資維持率</title><style>
:root{{--bg:#F4F6F4;--card:#fff;--ink:#0F161D;--ink2:#44515E;--line:#DDE3E0;--up:#E5484D;--dn:#12A366;--acc:#B0842F;--raise:#EDF0EE;--bad:#C8323A;--badbg:#FCE9EA;--warnbg:#FBF3E2}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#000;--card:#111;--ink:#F5F5F5;--ink2:#A3A3A3;--line:#2A2A2A;--acc:#D9A441;--raise:#1E1E1E;--bad:#FF6B70;--badbg:#3A1416;--warnbg:#2E2410}}}}
:root[data-theme="dark"]{{--bg:#000;--card:#111;--ink:#F5F5F5;--ink2:#A3A3A3;--line:#2A2A2A;--acc:#D9A441;--raise:#1E1E1E;--bad:#FF6B70;--badbg:#3A1416;--warnbg:#2E2410}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Noto Sans TC","Microsoft JhengHei",sans-serif}}
.w{{max-width:1120px;margin:0 auto;padding:12px 16px 24px}} h1{{font-size:19px;margin:2px 0 6px}} h2{{font-size:17px;margin:0 0 6px}} h3{{font-size:15px;margin:14px 0 6px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:12px;min-width:0}}
li,p{{overflow-wrap:anywhere}} .m{{color:var(--ink2);font-size:13px}}
.alert{{border-left:4px solid var(--bad);background:var(--badbg);border-radius:6px;padding:6px 10px;margin:0 0 8px;font-size:13px}}
.tabs{{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:0 0 10px;position:sticky;top:0;background:var(--bg);z-index:3}}
.tabs button{{border:0;background:none;color:var(--ink2);font:inherit;font-weight:600;padding:8px 12px;border-bottom:3px solid transparent;cursor:pointer;white-space:nowrap}}
.tabs button.on{{color:var(--ink);border-bottom-color:var(--acc)}} .tabs small{{font-weight:400;font-size:11px;color:var(--acc)}}
.pane{{display:none}} .pane.on{{display:block}}
.bar{{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;margin:0 0 8px}}
.seg{{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}} .seg button{{border:0;border-left:1px solid var(--line);background:var(--card);color:var(--ink);padding:4px 10px;font:inherit;font-size:13px;cursor:pointer;white-space:nowrap}}
.seg button:first-child{{border-left:0}} .seg button.on{{background:var(--acc);color:#fff}}
.lab{{font-size:12px;color:var(--ink2)}}
input[type=search]{{font:inherit;font-size:13px;padding:4px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);width:min(160px,100%)}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
th,td{{padding:6px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}} th:first-child,td:first-child{{text-align:left}}
th{{color:var(--ink2);font-weight:600;font-size:13px;background:var(--raise)}}
th.s{{cursor:pointer;user-select:none}} th.s:hover{{color:var(--ink)}} .ar{{font-size:11px;margin-left:2px;color:var(--acc)}}
td.l,th.l{{text-align:left}} td.nm{{max-width:8em;overflow:hidden;text-overflow:ellipsis}}
.stk td:first-child,.stk th:first-child{{position:sticky;left:0;background:var(--card);z-index:1}} .stk th:first-child{{background:var(--raise)}}
.bad{{color:var(--bad);font-weight:700}} tr.warn td{{background:var(--warnbg)}} tr.badrow td{{background:var(--badbg)}}
.how{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(420px,100%),1fr));gap:10px}} .hi{{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--raise)}}
.ht{{display:flex;justify-content:space-between;gap:8px;align-items:baseline}} .hm{{font-size:13px;color:var(--ink2);margin-top:6px;overflow-wrap:anywhere}}
.tag{{font-size:12px;border-radius:6px;padding:0 8px;color:#fff;white-space:nowrap}} .tag.ok{{background:var(--dn)}} .tag.ng{{background:var(--acc)}}
tr.sec{{cursor:pointer}} tr.sec:hover td{{background:var(--raise)}} tr.sub td{{background:var(--raise);font-size:13px}}
.more{{font:inherit;font-size:13px;margin-top:8px;padding:5px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);cursor:pointer}}
details{{margin:6px 0}} summary{{cursor:pointer;font-size:14px;font-weight:600}} details .in{{padding:4px 0 0}}
.src{{font-size:11px;color:var(--ink2);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-left:4px;font-weight:400}}
.foot{{font-size:12px;color:var(--ink2);margin-top:8px;overflow-wrap:anywhere}}
</style></head><body><div class="w"><h1>個股／族群融資維持率（本站推估）</h1>
<p class="alert"><b>{cl:g}% 斷頭是「整戶」計算，不是單一股票</b>；本表是每檔股票全體融資戶的平均推估，個別投資人成本不同。</p>
<nav class="tabs" id="tabs"><button data-p="pS" class="on">個股</button><button data-p="pG">族群</button><button data-p="pH">說明與驗證 <small>{"已驗證" if pz else "驗證未過"}</small></button></nav>

<section class="pane on" id="pS">
<div class="bar"><span class="seg" data-g="mkt"><button data-v="twse" class="on">上市</button><button data-v="otc">上櫃</button></span>
<span class="seg" data-g="flt"><button data-v="all" class="on">全部</button><button data-v="lt">&lt; {cl:g}%</button><button data-v="mid">{cl:g}～150%</button></span>
<span class="seg" data-g="srt"><button data-v="6" class="on">維持率</button><button data-v="7">離 {cl:g}%</button><button data-v="4">融資市值</button></span>
<input type="search" id="q" placeholder="搜尋代號／名稱" aria-label="搜尋代號或名稱"></div>
<p class="m" id="info"></p>
<div class="tw"><table class="stk" id="st"><thead><tr>
<th class="s l" data-k="0">代號</th><th class="l">名稱</th><th class="s" data-k="6">推估維持率</th><th class="s" data-k="7">再跌幾 % 到 {cl:g}%</th><th class="s" data-k="4">融資市值（億）</th>
<th class="s" data-k="3">融資張數</th><th class="s" data-k="5">推估成本（元）</th><th class="s" data-k="9">收盤</th><th class="s" data-k="8">近 5 日增減（張）</th><th class="s l" data-k="2">族群</th>
</tr></thead><tbody></tbody></table></div><button class="more" id="more" hidden></button>
<p class="foot">本站推估；紅底＝推估維持率 &lt; {cl:g}%、黃底＝{cl:g}～150%；只列融資 ≥ 100 張的股票（不含 ETF）。成數為本站校準推估，算法見「說明與驗證」。歷史統計，非預測，不構成買賣建議。</p>
</section>

<section class="pane" id="pG">
<div class="bar"><span class="seg" data-g="mkt"><button data-v="twse" class="on">上市</button><button data-v="otc">上櫃</button></span>
<span class="seg" data-g="gsrt"><button data-v="5" class="on">族群維持率</button><button data-v="6">&lt; {cl:g}% 檔數</button><button data-v="3">融資市值</button></span>
<span class="seg" data-g="src"><button data-v="all" class="on">全部</button><button data-v="本站">本站族群</button><button data-v="官方">官方產業別</button></span></div>
<p class="m">分類來源：本站追蹤池有分類的股票用本站族群（融資 ≥ 100 張中上市 {d["sector_cov"]["twse"]["本站"]} 檔、上櫃 {d["sector_cov"]["otc"]["本站"]} 檔），其他用證交所／櫃買公布的官方產業別（標「官方」；上市 {d["sector_cov"]["twse"]["官方"]} 檔、上櫃 {d["sector_cov"]["otc"]["官方"]} 檔）；未分類剩上市 {d["sector_cov"]["twse"]["未分類"]} 檔、上櫃 {d["sector_cov"]["otc"]["未分類"]} 檔。</p><p class="m" id="ginfo"></p>
<div class="tw"><table class="stk" id="gt"><thead><tr>
<th class="s l" data-k="0">族群</th><th class="s" data-k="5">族群維持率</th><th class="s" data-k="6">&lt; {cl:g}% 檔數</th><th class="s" data-k="2">檔數</th><th class="s" data-k="3">融資市值（億）</th><th class="s" data-k="4">推估金額（億）</th><th class="s l" data-k="1">大類</th></tr></thead><tbody></tbody></table></div>
<button class="more" id="gmore" hidden></button>
<p class="foot">點一列展開成分股。族群＝本站族群表「細類」，沒有的用官方產業別；族群維持率＝族群融資市值合計 ÷ 族群推估融資金額合計。本站推估，歷史統計，非預測。</p>
</section>

<section class="pane" id="pH">
{help_html(d)}</section>
</div>
<script>
const D={js_data};const CL={cl:g};
const S={{mkt:'twse',flt:'all',sk:6,sd:1,lim:30,gk:5,gd:1,glim:30,src:'all'}};const open=new Set();
const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
const fm=(v,n)=>v==null?'—':v.toLocaleString('zh-TW',{{minimumFractionDigits:n,maximumFractionDigits:n}});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
const DESC=new Set([3,4,8]),GDESC=new Set([2,3,4,6]);
function cmp(k,d){{return (a,b)=>{{const x=a[k],y=b[k];if(x==null)return 1;if(y==null)return -1;return (typeof x==='string'?x.localeCompare(y,'zh-Hant'):x-y)*d}}}}
function cls(m){{return m<CL?'badrow':m<150?'warn':''}}
function gap(r){{return r[6]<CL?'<span class="bad">已低於</span>':fm(r[7],1)+'%'}}
function arrows(tb,k,d){{$$(tb+' th.s').forEach(th=>{{th.querySelector('.ar')?.remove();if(+th.dataset.k===k)th.insertAdjacentHTML('beforeend',`<span class="ar">${{d>0?'▲':'▼'}}</span>`)}})}}
function segSync(){{$$('.seg').forEach(sg=>{{const g=sg.dataset.g;const v=g==='srt'?String(S.sk):g==='gsrt'?String(S.gk):S[g];sg.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===v))}})}}
function drawS(){{const q=$('#q').value.trim();let rs=D[S.mkt].rows.filter(r=>r[3]>=100&&(!q||r[0].includes(q)||r[1].includes(q)));
const lo=rs.filter(r=>r[6]<CL).length,mid=rs.filter(r=>r[6]>=CL&&r[6]<150).length;
if(S.flt==='lt')rs=rs.filter(r=>r[6]<CL);else if(S.flt==='mid')rs=rs.filter(r=>r[6]>=CL&&r[6]<150);
rs.sort(cmp(S.sk,S.sd));
$('#info').textContent=`資料日 ${{D[S.mkt].date}}・融資 ≥ 100 張 ${{D[S.mkt].rows.filter(r=>r[3]>=100).length}} 檔：< ${{CL}}% ${{lo}} 檔、${{CL}}～150% ${{mid}} 檔・校準成數約 ${{(D[S.mkt].ratio*100).toFixed(1)}}%`;
$('#st tbody').innerHTML=rs.slice(0,S.lim).map(r=>`<tr class="${{cls(r[6])}}"><td>${{esc(r[0])}}</td><td class="l nm" title="${{esc(r[1])}}">${{esc(r[1])}}</td><td class="${{r[6]<CL?'bad':''}}">${{fm(r[6],1)}}%</td><td>${{gap(r)}}</td><td>${{fm(r[4],2)}}</td><td>${{fm(r[3],0)}}</td><td>${{fm(r[5],2)}}</td><td>${{fm(r[9],2)}}</td><td>${{r[8]==null?'—':(r[8]>0?'+':'')+fm(r[8],0)}}</td><td class="l">${{esc(r[2])}}${{r[11]==='官方'?'<small class="src">官方</small>':''}}</td></tr>`).join('')||'<tr><td colspan="10" class="l m">沒有符合的股票</td></tr>';
const mb=$('#more');mb.hidden=rs.length<=S.lim;mb.textContent=`顯示更多（${{Math.min(S.lim,rs.length)}} / ${{rs.length}}）`;arrows('#st',S.sk,S.sd);segSync()}}
function drawG(){{const by=Object.fromEntries(D[S.mkt].rows.map(r=>[r[0],r]));let gs=D[S.mkt].sec.filter(g=>S.src==='all'||g[8]===S.src).sort(cmp(S.gk,S.gd));
$('#ginfo').textContent=`資料日 ${{D[S.mkt].date}}・${{gs.length}} 個族群`;let h='';
for(const g of gs.slice(0,S.glim)){{h+=`<tr class="sec" data-g="${{esc(g[0])}}"><td>${{open.has(g[0])?'▾':'▸'}} ${{esc(g[0])}}${{g[8]==='官方'?'<small class="src">官方</small>':''}}</td><td class="${{g[5]<CL?'bad':''}}">${{fm(g[5],1)}}%</td><td>${{g[6]}}</td><td>${{g[2]}}</td><td>${{fm(g[3],2)}}</td><td>${{fm(g[4],2)}}</td><td class="l">${{esc(g[1])}}</td></tr>`;
if(open.has(g[0])){{const cs=g[7].map(c=>by[c]).filter(Boolean).sort(cmp(6,1));h+=cs.map(r=>`<tr class="sub"><td>　${{esc(r[0])}} ${{esc(r[1])}}</td><td class="${{r[6]<CL?'bad':''}}">${{fm(r[6],1)}}%</td><td>${{gap(r)}}</td><td></td><td>${{fm(r[4],2)}}</td><td>${{fm(r[10],2)}}</td><td class="l"></td></tr>`).join('')}}}}
$('#gt tbody').innerHTML=h;const mb=$('#gmore');mb.hidden=gs.length<=S.glim;mb.textContent=`顯示更多（${{Math.min(S.glim,gs.length)}} / ${{gs.length}}）`;arrows('#gt',S.gk,S.gd);segSync()}}
$('#tabs').onclick=e=>{{const b=e.target.closest('button');if(!b)return;$$('#tabs button').forEach(x=>x.classList.toggle('on',x===b));$$('.pane').forEach(p=>p.classList.toggle('on',p.id===b.dataset.p))}};
$$('.seg').forEach(sg=>sg.onclick=e=>{{const b=e.target.closest('button');if(!b)return;const g=sg.dataset.g,v=b.dataset.v;
if(g==='srt'){{S.sk=+v;S.sd=DESC.has(S.sk)?-1:1}}else if(g==='gsrt'){{S.gk=+v;S.gd=GDESC.has(S.gk)?-1:1}}else S[g]=v;
if(g==='mkt'){{open.clear();S.lim=30;S.glim=30}}if(g==='flt')S.lim=30;drawS();drawG()}});
$$('#st th.s').forEach(th=>th.onclick=()=>{{const k=+th.dataset.k;S.sd=k===S.sk?-S.sd:(DESC.has(k)?-1:1);S.sk=k;drawS()}});
$$('#gt th.s').forEach(th=>th.onclick=()=>{{const k=+th.dataset.k;S.gd=k===S.gk?-S.gd:(GDESC.has(k)?-1:1);S.gk=k;drawG()}});
$('#gt tbody').onclick=e=>{{const tr=e.target.closest('tr.sec');if(!tr)return;const g=tr.dataset.g;open.has(g)?open.delete(g):open.add(g);drawG()}};
$('#q').oninput=()=>{{S.lim=30;drawS()}};$('#more').onclick=()=>{{S.lim+=50;drawS()}};$('#gmore').onclick=()=>{{S.glim+=50;drawG()}};
drawS();drawG();
</script></body></html>'''


def mt_prefix(h):
    """class 一律加 mt- 前綴（網站模組慣例，不碰既有樣式）"""
    return re.sub(r'class="([^"]*)"', lambda m: 'class="' + ' '.join('mt-' + c for c in m.group(1).split()) + '"', h)


def public(d):
    """正式檔 docs/data/stock_maint.json 的內容（網站讀這份）：表格資料＋說明與驗證 HTML"""
    return {'gen': 'site_tools/stock_maint.py', 'passed': passed(d), 'fail': fail_mkts(d), 'sector_cov': d['sector_cov'],
            'mkts': {m: {'date': d['mkts'][m]['date'], 'rows': d['mkts'][m]['rows'], 'sec': d['mkts'][m]['sectors'],
                         'ratio': d['mkts'][m]['summary']['ratio'], 'r0': d['mkts'][m]['r0'],
                         'call': d['mkts'][m].get('call', 130.0),   # 🔴 11-23 雲端舊34：資料日的追繳門檻（%）
                         # 雲端新18：ETF 個別（欄位同 rows）、ETF 分組、「大盤」20 日資券進出
                         'etf': d['mkts'][m].get('etf_rows', []), 'esec': d['mkts'][m].get('etf_sec', []),
                         'board': d['mkts'][m].get('board', []), 'etf_cal': d['mkts'][m].get('etf_cal')} for m in MKT_NAME},
            'etf_groups': d.get('etf_groups'), 'etf_start': d.get('etf_start'),
            'help': mt_prefix(help_html(d))}


def write(d, path):
    open(path, 'w').write(build(d))


if __name__ == '__main__':
    write(json.load(open(sys.argv[1])), sys.argv[2])
