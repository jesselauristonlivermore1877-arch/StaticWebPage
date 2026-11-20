# -*- coding: utf-8 -*-
"""個股／族群融資維持率頁面（讀 stock_maint.py 的 data.json → index.html；不打網路）
由 site_tools/stock_maint.py 呼叫；也可單獨跑：python site_tools/stock_maint_page.py <data.json> <index.html>
"""
import json, sys, html

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
        else:
            v2 = '尚無可校準日'
        ok = (s.get('bal_match') or 0) >= 99.9 and (s['err20_max'] or 99) < 2
        out.append(f'<div class="hi"><div class="ht"><b>{nm}</b><span class="tag {"ok" if ok else "ng"}">{"兩條都過" if ok else "未過／未驗"}</span></div>'
                   f'<div class="hm">① 另一份原始資料重算：{v1}</div><div class="hm">② 全市場推估合計 vs 官方融資金額：{v2}</div></div>')
    return '<div class="how">' + ''.join(out) + '</div>'


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


def build(d):
    tw = d['mkts']['twse']; ot = d['mkts']['otc']
    payload = {m: {'date': d['mkts'][m]['date'], 'rows': d['mkts'][m]['rows'], 'sec': d['mkts'][m]['sectors'],
                   'ratio': d['mkts'][m]['summary']['ratio']} for m in MKT_NAME}
    js_data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
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
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>個股融資維持率</title><style>
:root{{--bg:#F4F6F4;--card:#fff;--ink:#0F161D;--ink2:#44515E;--line:#DDE3E0;--up:#E5484D;--dn:#12A366;--acc:#B0842F;--raise:#EDF0EE;--bad:#C8323A;--badbg:#FCE9EA;--warnbg:#FBF3E2}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#000;--card:#111;--ink:#F5F5F5;--ink2:#A3A3A3;--line:#2A2A2A;--acc:#D9A441;--raise:#1E1E1E;--bad:#FF6B70;--badbg:#3A1416;--warnbg:#2E2410}}}}
:root[data-theme="dark"]{{--bg:#000;--card:#111;--ink:#F5F5F5;--ink2:#A3A3A3;--line:#2A2A2A;--acc:#D9A441;--raise:#1E1E1E;--bad:#FF6B70;--badbg:#3A1416;--warnbg:#2E2410}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Noto Sans TC","Microsoft JhengHei",sans-serif}}
.w{{max-width:1120px;margin:0 auto;padding:16px}} h1{{font-size:22px;margin:4px 0 10px}} h2{{font-size:18px;margin:0 0 6px}} h3{{font-size:15px;margin:14px 0 6px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:14px;min-width:0}}
li,p{{overflow-wrap:anywhere}} .m{{color:var(--ink2);font-size:13px}}
.alert{{border:2px solid var(--bad);background:var(--badbg);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:15px}}
.alert b{{color:var(--bad)}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
th,td{{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}} th:first-child,td:first-child{{text-align:left}}
th{{color:var(--ink2);font-weight:600;font-size:13px;background:var(--raise)}}
th.s{{cursor:pointer;user-select:none}} th.s:hover{{color:var(--ink)}} th.s .ar{{font-size:11px;margin-left:2px;color:var(--acc)}}
td.l,th.l{{text-align:left}} td.nm{{max-width:9em;overflow:hidden;text-overflow:ellipsis}}
#st td:first-child,#st th:first-child{{position:sticky;left:0;background:var(--card);z-index:1}} #st th:first-child{{background:var(--raise)}}
.bad{{color:var(--bad);font-weight:700}} .warn{{background:var(--warnbg)}} .badrow{{background:var(--badbg)}}
.how{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(420px,100%),1fr));gap:10px}} .hi{{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--raise)}}
.ht{{display:flex;justify-content:space-between;gap:8px;align-items:baseline}} .hm{{font-size:13px;color:var(--ink2);margin-top:6px;overflow-wrap:anywhere}}
.tag{{font-size:12px;border-radius:6px;padding:0 8px;color:#fff;white-space:nowrap}} .tag.ok{{background:var(--dn)}} .tag.ng{{background:var(--acc)}}
.bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0 10px}}
.seg{{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}} .seg button{{border:0;background:var(--card);color:var(--ink);padding:5px 14px;font:inherit;cursor:pointer}}
.seg button.on{{background:var(--acc);color:#fff}}
input[type=search]{{font:inherit;padding:5px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);width:min(220px,100%)}}
label.ck{{font-size:13px;color:var(--ink2);white-space:nowrap}}
tr.sec{{cursor:pointer}} tr.sec:hover td{{background:var(--raise)}} tr.sub td{{background:var(--raise);font-size:13px}}
.more{{font:inherit;font-size:13px;margin-top:8px;padding:4px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);cursor:pointer}}
details{{margin:6px 0}} summary{{cursor:pointer;font-size:14px}}
.foot{{font-size:12px;color:var(--ink2);margin-top:8px;overflow-wrap:anywhere}}
</style></head><body><div class="w"><h1>個股／族群融資維持率（本站推估・預覽）</h1>
<div class="alert"><b>注意：</b>130% 斷頭是「整戶」計算，不是單一股票；本表是每檔股票全體融資戶的平均推估，個別投資人成本不同。<br>
全部數字都是<b>本站推估</b>（證交所、櫃買只公布全市場融資金額，不公布個股），不構成買賣建議。</div>

<div class="card"><h2>驗證結果（照實寫）</h2>{ver_block(d)}
<p class="m">{"" if nfull else "目前 margin_full（逐檔融資買進）還沒進 repo，上市 ETF 逐檔只有 7/16～8/25 與 11/11～11/20 零星日子、上櫃只有 11/19～11/20，所以能校準的日子很少；回補進來後重跑即更新。"}</p></div>

<div class="card"><h2>① 個股融資維持率</h2>
<div class="bar"><span class="seg" id="mk"><button data-m="twse" class="on">上市</button><button data-m="otc">上櫃</button></span>
<input type="search" id="q" placeholder="搜尋代號或名稱" aria-label="搜尋代號或名稱">
<label class="ck"><input type="checkbox" id="small" checked> 隱藏融資 &lt; 100 張</label></div>
<p class="m" id="info"></p>
<div class="tw"><table id="st"><thead><tr>
<th class="s l" data-k="0">代號</th><th class="l">名稱</th><th class="s l" data-k="2">族群</th><th class="s" data-k="3">融資張數</th><th class="s" data-k="4">融資市值（億）</th>
<th class="s" data-k="5">推估融資成本（元）</th><th class="s" data-k="9">收盤</th><th class="s" data-k="6">推估維持率</th><th class="s" data-k="7">股價再跌幾 % 到 130%</th><th class="s" data-k="8">近 5 日融資增減（張）</th>
</tr></thead><tbody></tbody></table></div><button class="more" id="more" hidden>顯示全部</button>
<div class="foot">點欄位名稱排序（再點一次反向）；預設依推估維持率由低到高。紅底＝推估維持率低於 130%；黃底＝130%～150%。「股價再跌幾 %」＝（維持率−130）÷ 維持率；已低於 130% 的顯示「已低於」。
推估融資成本＝本站逐日累推的融資買進平均價（元／股）。ETF 不列入本表（只用在校準）。</div></div>

<div class="card"><h2>② 族群融資維持率</h2>
<p class="m">族群＝本站族群表「細類」（目前 {d["sector_n"]} 檔有分類，其他歸「未分類」）；族群維持率＝族群融資市值合計 ÷ 族群推估融資金額合計。點一列展開成分股。</p>
<div class="tw"><table id="gt"><thead><tr>
<th class="s l" data-k="0">族群</th><th class="s l" data-k="1">大類</th><th class="s" data-k="2">檔數</th><th class="s" data-k="3">融資市值（億）</th><th class="s" data-k="4">推估融資金額（億）</th>
<th class="s" data-k="5">族群維持率</th><th class="s" data-k="6">維持率 &lt; 130% 檔數</th></tr></thead><tbody></tbody></table></div></div>

<div class="card"><h2>③ 怎麼算（本站推估）</h2>
<ol class="m" style="padding-left:20px;margin:4px 0">
<li>證交所、櫃買不公布個股融資金額，本站逐檔逐日累推：今日金額＝昨日金額 ×（今日餘額 − 今日買進）÷ 昨日餘額 ＋ 今日買進張數 × 1000 × 當日均價（成交金額 ÷ 成交股數）× 成數；起點（{md(tw["start"])}）＝ 餘額 × 1000 × 收盤 × 成數。</li>
<li>「今日買進」有證交所／櫃買逐檔融資買進的日子用真的買進；沒有的日子用退路：買進 ≈ max(今日餘額 − 昨日餘額, 0)（會低估週轉，下跌時推估成本偏高、維持率偏低）。</li>
<li><b>成數為本站校準推估</b>：法規上限上市 6 成、上櫃 5 成，但券商可只借 4、3 成，所以先用 6／5 成累推，再用證交所／櫃買公布的融資總金額（含 ETF，分子也含 ETF）逐日校準出「實際平均成數」，套回各股。上市目前約 {f(tw["summary"]["ratio"] * 100, 1)}%、上櫃約 {f(ot["summary"]["ratio"] * 100, 1)}%。</li>
<li>個股推估維持率＝融資張數 × 1000 × 收盤 ÷ 推估融資金額；族群維持率＝族群融資市值合計 ÷ 族群推估金額合計。</li>
<li>已知限制：除權息、減資、分割造成的張數變動會被當成買賣；新上市／斷檔後重新起算時，成本先以當天收盤代入。</li></ol>
<h3>校準紀錄（近 20 個校準日）</h3><p class="m">上市</p>{cal_table(d, "twse")}<p class="m">上櫃</p>{cal_table(d, "otc")}
<h3>抽樣 5 檔逐日累推過程（前 3 天＋最後 3 天）</h3>{traces}
</div>
<div class="foot">資料：證交所 MI_MARGN、櫃買融資融券餘額（逐檔融資張數）、本站日K（收盤、成交金額、成交股數）、證交所／櫃買公布融資金額。資料日：上市 {md(tw["date"])}、上櫃 {md(ot["date"])}。程式：site_tools/stock_maint.py。<b>歷史統計，非預測，不構成買賣建議。</b></div>
</div>
<script>
const D={js_data};
let mkt='twse',sk=6,sd=1,lim=200,gk=5,gd=1;const open=new Set();
const $=s=>document.querySelector(s);
const fm=(v,n)=>v==null?'—':v.toLocaleString('zh-TW',{{minimumFractionDigits:n,maximumFractionDigits:n}});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
function cmp(k,d){{return (a,b)=>{{const x=a[k],y=b[k];if(x==null)return 1;if(y==null)return -1;return (typeof x==='string'?x.localeCompare(y,'zh-Hant'):x-y)*d}}}}
function cls(m){{return m<130?'badrow':m<150?'warn':''}}
function gap(r){{return r[6]<130?'<span class="bad">已低於</span>':fm(r[7],1)+'%'}}
function rowsHtml(rs){{return rs.map(r=>`<tr class="${{cls(r[6])}}"><td>${{esc(r[0])}}</td><td class="l nm" title="${{esc(r[1])}}">${{esc(r[1])}}</td><td class="l">${{esc(r[2])}}</td><td>${{fm(r[3],0)}}</td><td>${{fm(r[4],2)}}</td><td>${{fm(r[5],2)}}</td><td>${{fm(r[9],2)}}</td><td class="${{r[6]<130?'bad':''}}">${{fm(r[6],1)}}%</td><td>${{gap(r)}}</td><td>${{r[8]==null?'—':(r[8]>0?'+':'')+fm(r[8],0)}}</td></tr>`).join('')}}
function arrows(tb,k,d){{document.querySelectorAll(tb+' th.s').forEach(th=>{{th.querySelector('.ar')?.remove();if(+th.dataset.k===k)th.insertAdjacentHTML('beforeend',`<span class="ar">${{d>0?'▲':'▼'}}</span>`)}})}}
function drawS(){{const q=$('#q').value.trim(),sm=$('#small').checked;let rs=D[mkt].rows.filter(r=>(!sm||r[3]>=100)&&(!q||r[0].includes(q)||r[1].includes(q)));
rs.sort(cmp(sk,sd));const lo=rs.filter(r=>r[6]<130).length;
$('#info').textContent=`資料日 ${{D[mkt].date}}・${{rs.length}} 檔（推估維持率低於 130%：${{lo}} 檔）・校準後平均成數約 ${{(D[mkt].ratio*100).toFixed(1)}}%`;
$('#st tbody').innerHTML=rowsHtml(rs.slice(0,lim));$('#more').hidden=rs.length<=lim;$('#more').textContent=`顯示全部 ${{rs.length}} 檔`;arrows('#st',sk,sd)}}
function drawG(){{const by=Object.fromEntries(D[mkt].rows.map(r=>[r[0],r]));const gs=D[mkt].sec.slice().sort(cmp(gk,gd));let h='';
for(const g of gs){{h+=`<tr class="sec" data-g="${{esc(g[0])}}"><td>${{open.has(g[0])?'▾':'▸'}} ${{esc(g[0])}}</td><td class="l">${{esc(g[1])}}</td><td>${{g[2]}}</td><td>${{fm(g[3],2)}}</td><td>${{fm(g[4],2)}}</td><td class="${{g[5]<130?'bad':''}}">${{fm(g[5],1)}}%</td><td>${{g[6]}}</td></tr>`;
if(open.has(g[0])){{const cs=g[7].map(c=>by[c]).filter(Boolean).sort(cmp(6,1));h+=cs.map(r=>`<tr class="sub"><td>　${{esc(r[0])}} ${{esc(r[1])}}</td><td class="l"></td><td></td><td>${{fm(r[4],2)}}</td><td>${{fm(r[10],2)}}</td><td class="${{r[6]<130?'bad':''}}">${{fm(r[6],1)}}%</td><td>${{gap(r)}}</td></tr>`).join('')}}}}
$('#gt tbody').innerHTML=h;arrows('#gt',gk,gd)}}
document.querySelectorAll('#st th.s').forEach(th=>th.onclick=()=>{{const k=+th.dataset.k;sd=k===sk?-sd:(k===4||k===3?-1:1);sk=k;drawS()}});
document.querySelectorAll('#gt th.s').forEach(th=>th.onclick=()=>{{const k=+th.dataset.k;gd=k===gk?-gd:(k===3||k===4||k===2||k===6?-1:1);gk=k;drawG()}});
$('#gt tbody').onclick=e=>{{const tr=e.target.closest('tr.sec');if(!tr)return;const g=tr.dataset.g;open.has(g)?open.delete(g):open.add(g);drawG()}};
$('#mk').onclick=e=>{{const b=e.target.closest('button');if(!b)return;mkt=b.dataset.m;document.querySelectorAll('#mk button').forEach(x=>x.classList.toggle('on',x===b));open.clear();lim=200;drawS();drawG()}};
$('#q').oninput=()=>{{lim=200;drawS()}};$('#small').onchange=drawS;$('#more').onclick=()=>{{lim=1e9;drawS()}};
drawS();drawG();
</script></body></html>'''


def write(d, path):
    open(path, 'w').write(build(d))


if __name__ == '__main__':
    write(json.load(open(sys.argv[1])), sys.argv[2])
