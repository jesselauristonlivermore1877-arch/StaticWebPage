/* research/preview_b/watch_ext.js ── 看盤區兩個新區塊（11-16 晚【新】裁示；W 出預覽 docs/preview/watch_newsval/，11-16 晚 Evans「通通先上」→ 已接進會員站 index.html）
   預覽與正式版載入同一支檔、呼叫同一個函式，不另寫：
   ① nfMount(root, F, NV)：「盤中資金」併「產業快訊」——族群資金曲線（F＝dash.flow，s1 每分鐘累計主動淨買，億元）＋消息直線（NV＝dash_live.news_view()）＋族群多空燈號。
   ② vdMount(root, D, SRC)：看盤區新標籤「估值」——雲端AM 估值拆解 v2（70a99b89）同一段程式，只把資料改成參數傳入（正式檔 docs/data/val_decomp.json）。
   樣式一律 nf-／vd- 前綴，不碰會員站既有樣式。
   ⚠ 本檔由 watch_ext.tpl.js＋StaticWebPage docs/preview/val_decomp/index.html 組出來（估值那段是 AM 原程式）；改 nfMount 改 tpl，改估值改 AM 的頁再重組。 */
(function () {
var NF_CSS = `
.nf-wrap{font:14px/1.55 system-ui,-apple-system,"Noto Sans TC",sans-serif;color:#e6e8eb}
.nf-wrap h4{margin:12px 0 6px;font-size:15px}
.nf-note{color:#9aa3ad;font-size:12.5px;white-space:normal}
.nf-row{display:grid;grid-template-columns:minmax(0,10em) 4.6em 4.6em minmax(0,1fr);gap:8px;align-items:center;padding:5px 4px;border-top:1px solid #26303d;cursor:pointer}
.nf-row.on{background:#18202b}
.nf-nm{font-weight:600;overflow-wrap:anywhere}.nf-nm small{color:#9aa3ad;font-weight:400}
.nf-net{text-align:right;font-variant-numeric:tabular-nums}
.nf-u{color:#e5484d}.nf-d{color:#2fb36b}
.nf-lamp{font-size:12px;border-radius:5px;padding:0 6px;border:1px solid;white-space:nowrap;text-align:center}
.nf-lamp.b{color:#fff;background:#e5484d;border-color:#e5484d}.nf-lamp.s{color:#fff;background:#2fb36b;border-color:#2fb36b}
.nf-lamp.m{color:#d6a54a;border-color:#d6a54a}.nf-lamp.n{color:#5d6773;border-color:#26303d}
.nf-sp svg{display:block;width:100%;height:30px}
.nf-sub{padding:4px 6px 8px 12px;background:#141a22;border-top:1px dashed #26303d}
.nf-it{padding:4px 0;border-top:1px solid #1d2530;white-space:normal}
.nf-it:first-child{border-top:0}
.nf-it a{color:#e6e8eb;text-decoration:none}.nf-it a:hover{text-decoration:underline}
.nf-t{color:#9aa3ad;font-variant-numeric:tabular-nums;margin-right:6px}
.nf-src{color:#9aa3ad;font-size:12px;margin-left:4px}
.nf-ch{display:inline-block;font-size:11.5px;border-radius:4px;padding:0 5px;margin:2px 4px 0 0;border:1px solid #26303d;color:#9aa3ad}
.nf-ch.b{color:#e5484d;border-color:#e5484d}.nf-ch.s{color:#2fb36b;border-color:#2fb36b}
.nf-more{margin-top:6px;background:#161c24;color:#e6e8eb;border:1px solid #26303d;border-radius:6px;padding:3px 10px;cursor:pointer}
@media (max-width:560px){.nf-row{grid-template-columns:minmax(0,1fr) 4.6em 4.4em}.nf-sp{grid-column:1/-1}}
` + `
.vd-root{--vd-bg:#11151b;--vd-ink:#e6e8eb;--vd-ink2:#9aa3ad;--vd-line:#26303d;--vd-card:#161c24;--vd-acc:#d6a54a;--vd-up:#e5484d;--vd-dn:#2fb36b;--vd-eps:#6f9be0;--vd-pe:#d6a54a;--vd-hl:#2e2715;--vd-hlb:#a67c2c}
.vd-root *{box-sizing:border-box}
.vd-root{background:var(--vd-bg);color:var(--vd-ink);font:14px/1.6 system-ui,-apple-system,"Noto Sans TC",sans-serif;border-radius:10px}
.vd-main{max-width:1100px;margin:0 auto;padding:20px 16px 48px}
.vd-h1{font-size:21px;margin:0 0 6px}
.vd-lead{font-size:16px;margin:0 0 6px;font-weight:600}
.vd-m{color:var(--vd-ink2);font-size:13px;margin:0 0 12px}
.vd-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.vd-tab{border:1px solid var(--vd-line);background:var(--vd-card);color:var(--vd-ink);border-radius:18px;padding:5px 14px;font-size:14px;cursor:pointer}
.vd-tab[aria-pressed="true"]{background:var(--vd-acc);border-color:var(--vd-acc);color:#fff;font-weight:700}
.vd-sum{background:var(--vd-hl);border:1px solid var(--vd-hlb);border-radius:10px;padding:10px 12px;margin:8px 0 12px;font-size:14px}
.vd-card{background:var(--vd-card);border:1px solid var(--vd-line);border-radius:10px;overflow:hidden}
.vd-row{display:grid;grid-template-columns:110px minmax(0,1.6fr) repeat(3,minmax(0,1fr)) minmax(0,1.3fr);gap:6px;align-items:center;padding:9px 12px;border-top:1px solid var(--vd-line);cursor:pointer}
.vd-row:first-child{border-top:0}
.vd-hd{cursor:default;font-size:12px;color:var(--vd-ink2);background:transparent}
.vd-row.vd-cmp{background:var(--vd-hl);box-shadow:inset 4px 0 0 var(--vd-hlb)}
.vd-row.vd-few{opacity:.62}
.vd-g{font-weight:700;overflow-wrap:anywhere}.vd-g small{font-weight:400;color:var(--vd-ink2)}
.vd-n{text-align:right;font-variant-numeric:tabular-nums}
.vd-tag{display:inline-block;border-radius:6px;padding:1px 7px;font-size:12px;font-weight:700;white-space:nowrap;border:1px solid currentColor}
.vd-s0{color:#ffd88a;background:#4a3812;border-color:#a67c2c}
.vd-s1{color:#fff;background:var(--vd-dn);border-color:var(--vd-dn)}
.vd-s2{color:var(--vd-dn)}
.vd-s3{color:var(--vd-ink2)}
.vd-s4{color:#fff;background:var(--vd-up);border-color:var(--vd-up)}
.vd-up{color:var(--vd-up)}.vd-dn{color:var(--vd-dn)}
.vd-tg{font-size:13px;color:var(--vd-ink2)}
.vd-exp{display:none;padding:6px 12px 12px;border-top:1px dashed var(--vd-line);background:var(--vd-bg)}
.vd-exp.vd-open{display:block}
.vd-st{display:grid;grid-template-columns:120px minmax(0,1fr) minmax(0,1fr);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--vd-line);white-space:normal}
.vd-st:last-child{border-bottom:0}
.vd-nm{font-weight:700;font-size:14px}.vd-nm small{display:block;font-weight:400;color:var(--vd-ink2);font-size:12px}
.vd-bar{position:relative;height:18px;background:transparent;border-left:0}
.vd-axis{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--vd-ink2)}
.vd-seg{position:absolute;height:8px}
.vd-seg.vd-e{background:var(--vd-eps);top:1px}.vd-seg.vd-p{background:var(--vd-pe);top:9px}
.vd-mark{position:absolute;top:-3px;width:3px;height:24px;background:var(--vd-ink)}
.vd-txt{font-size:12.5px;color:var(--vd-ink2);margin-top:3px;font-variant-numeric:tabular-nums}
.vd-txt b{color:var(--vd-ink)}
.vd-leg{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--vd-ink2);margin:8px 0}
.vd-leg i{display:inline-block;width:12px;height:12px;vertical-align:-1px;margin-right:4px}
.vd-rule{font-size:13px;color:var(--vd-ink2);margin:14px 0 0}
.vd-rule li{margin:2px 0}
.vd-foot{margin-top:18px;font-size:13px;color:var(--vd-ink2);border-top:1px solid var(--vd-line);padding-top:10px}
.vd-lbl{display:none}
@media (max-width:760px){
  .vd-hd{display:none}
  .vd-row{grid-template-columns:repeat(3,minmax(0,1fr));gap:4px 8px}
  .vd-row>.vd-c-st{grid-column:1/2}.vd-row>.vd-c-g{grid-column:2/4}
  .vd-row>.vd-c-tg{grid-column:1/4}
  .vd-n{text-align:left}
  .vd-lbl{display:block;font-size:11px;color:var(--vd-ink2)}
  .vd-st{grid-template-columns:minmax(0,1fr)}
}
.vd-sw{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0;font-size:13px;color:var(--vd-ink2)}
.vd-sw .vd-tab{font-size:13px;padding:3px 11px}
.vd-bench{font-size:12.5px;color:var(--vd-ink2);margin:4px 0 0}
.vd-hot{display:inline-block;font-size:11.5px;font-weight:700;color:#fff;background:var(--vd-dn);border-radius:5px;padding:0 6px;margin-left:4px;white-space:nowrap}
.vd-irc{display:inline-block;font-size:11.5px;color:var(--vd-eps);border:1px solid var(--vd-eps);border-radius:5px;padding:0 6px;margin-left:4px;white-space:nowrap}
.vd-ir{grid-column:1/-1;font-size:12.5px;background:var(--vd-card);border:1px solid var(--vd-line);border-radius:8px;padding:6px 10px;white-space:normal}
.vd-ir ul{margin:4px 0 0;padding-left:18px}.vd-ir li{margin:2px 0}
.vd-ir a{color:var(--vd-acc)}
.vd-ir .vd-q{color:var(--vd-ink)}
`;
function addCss() { if (document.getElementById("nf-css")) return; var s = document.createElement("style"); s.id = "nf-css"; s.textContent = NF_CSS; document.head.appendChild(s); }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function sg(v, d) { return v == null || !isFinite(v) ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(d); }
var NF_W = 271;                                                                   /* s1 第 0 格＝09:00，一分一格到 13:30 */
function hmIdx(hm) { var m = /^(\d\d):(\d\d)$/.exec(hm || ""); if (!m) return null; var i = (+m[1]) * 60 + (+m[2]) - 540; return i >= 0 && i < NF_W ? i : null; }
function lampOf(L) {                                                              /* 只數「領先」消息；落後資料（財報創高類）不算 */
  if (!L || !(L.bull + L.bear)) return ["n", "—", "今天沒有對到產業鏈對照表的領先消息"];
  var t = "領先消息 偏多 " + L.bull + "、偏空 " + L.bear + (L.lag ? "（另有落後資料 " + L.lag + " 則不計）" : "");
  return L.bull > L.bear ? ["b", "偏多 " + L.bull, t] : L.bear > L.bull ? ["s", "偏空 " + L.bear, t] : ["m", "分歧", t];
}
function newsOf(NV, sec) { return (NV.items || []).filter(function (x) { return (x.groups || []).indexOf(sec) >= 0 || (x.chain || []).some(function (c) { return c[0] === sec; }); }); }
function dirOf(x, sec) { var c = (x.chain || []).filter(function (c) { return !sec || c[0] === sec; }); if (!c.length) return ""; var b = c.some(function (z) { return z[1] === "偏多"; }), s = c.some(function (z) { return z[1] === "偏空"; }); return b && !s ? "b" : s && !b ? "s" : "m"; }
function spark(a, marks) {
  var W = 300, H = 30; a = (a || []).map(function (v) { return v == null ? null : +v; });
  var n = 0; for (var i = a.length - 1; i >= 0; i--) if (a[i] != null && a[i] !== 0) { n = i + 1; break; }
  var seg = a.slice(0, Math.max(n, 2)), vs = seg.filter(function (v) { return v != null; }), mx = Math.max.apply(null, vs.map(Math.abs).concat([1e-9]));
  var x = function (i) { return (i / (NF_W - 1) * W).toFixed(1); }, y = function (v) { return (H / 2 - v / mx * (H / 2 - 2)).toFixed(1); };
  var p = seg.map(function (v, i) { return x(i) + "," + y(v || 0); }).join(" "), last = vs.length ? vs[vs.length - 1] : 0;
  var h = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none"><line x1="0" x2="' + W + '" y1="' + H / 2 + '" y2="' + H / 2 + '" stroke="#26303d"/>';
  marks.forEach(function (m) { h += '<line x1="' + x(m[0]) + '" x2="' + x(m[0]) + '" y1="0" y2="' + H + '" stroke="' + (m[1] === "b" ? "#e5484d" : m[1] === "s" ? "#2fb36b" : "#d6a54a") + '" stroke-width="1.5" vector-effect="non-scaling-stroke" opacity=".8"><title>' + esc(m[2]) + "</title></line>"; });
  return h + '<polyline fill="none" stroke="' + (last >= 0 ? "#e5484d" : "#2fb36b") + '" stroke-width="1.3" vector-effect="non-scaling-stroke" points="' + p + '"/></svg>';
}
function item(x, sec) {
  var ch = (x.chain || []).filter(function (c) { return !sec || c[0] === sec; }).map(function (c) { return '<span class="nf-ch ' + (c[1] === "偏多" ? "b" : "s") + '" title="對照表規則 ' + esc(c[2]) + '">' + esc(c[0]) + " " + c[1] + (c[3] === "落後" ? "・落後資料" : "") + "</span>"; }).join("");
  return '<div class="nf-it"><span class="nf-t">' + esc(x.hm) + '</span><a href="' + esc(x.u) + '" target="_blank" rel="noopener">' + esc(x.t) + '</a><span class="nf-src">' + esc(x.s) + "</span>" + (ch ? "<div>" + ch + "</div>" : "") + "</div>";
}
window.nfMount = function (root, F, NV) {
  addCss(); NV = NV || {items: [], lamps: {}}; var open = window.__nfOpen || null, K = 12;   /* 會員站每分鐘重畫、root 會換 → 展開的族群記在全域 */
  if (!F || F.err || !F.sectors) { root.innerHTML = '<div class="nf-wrap"><div class="nf-note">還沒有資金流向資料。</div></div>'; return; }
  var secs = F.sectors.slice().sort(function (p, q) { return q.net - p.net; });
  var h = '<div class="nf-wrap"><h4>盤中資金＋產業快訊（依族群）</h4><div class="nf-note">曲線＝當天 09:00 起每分鐘累計主動淨買（外盤−內盤成交金額，億元）；直線＝該族群產業消息的發布時間（<b class="nf-u">紅＝對照表判偏多</b>、<b class="nf-d">綠＝偏空</b>、黃＝方向不明；盤前、盤後的消息不畫線、列在清單）。燈號＝今天對到產業鏈對照表的「領先」消息偏多／偏空則數（財報創高等落後資料不計），只是標記、不下結論。點族群看消息。</div>';
  secs.forEach(function (g) {
    var L = lampOf((NV.lamps || {})[g.sector]), ns = newsOf(NV, g.sector);
    var marks = ns.map(function (x) { return [hmIdx(x.hm), dirOf(x, g.sector), x.hm + " " + x.t]; }).filter(function (m) { return m[0] != null; });
    h += '<div class="nf-row' + (open === g.sector ? " on" : "") + '" data-s="' + esc(g.sector) + '"><span class="nf-nm">' + esc(g.sector) + " <small>" + g.n + " 檔" + (ns.length ? "・消息 " + ns.length : "") + '</small></span><span class="nf-lamp ' + L[0] + '" title="' + esc(L[2]) + '">' + L[1] + '</span><span class="nf-net ' + (g.net > 0 ? "nf-u" : g.net < 0 ? "nf-d" : "") + '">' + sg(g.net, 1) + '</span><span class="nf-sp">' + spark(g.s1 || g.s5, marks) + "</span></div>";
    if (open === g.sector) h += '<div class="nf-sub">' + (ns.length ? ns.map(function (x) { return item(x, g.sector); }).join("") : '<div class="nf-note">今天沒有這個族群的產業消息。</div>') + "</div>";
  });
  var all = NV.items || [];
  h += '<h4>產業快訊（全部，新到舊）</h4><div class="nf-note">來源：經濟日報、工商時報、MoneyDJ、中央社、鉅亨（只取標題與連結）；每 3 分鐘更新' + (NV.made ? "，最後抓取 " + esc(NV.made.slice(11)) : "") + "；只留產業／公司事件。</div>";
  h += "<div>" + (all.length ? all.map(function (x, i) { return (i >= K ? '<div class="nf-x" hidden>' : "<div>") + item(x) + "</div>"; }).join("") : '<div class="nf-note">今天還沒有產業消息。</div>') + "</div>" + (all.length > K ? '<button class="nf-more">more（還有 ' + (all.length - K) + " 則）</button>" : "") + "</div>";
  root.innerHTML = h;
  root.querySelectorAll(".nf-row").forEach(function (r) { r.onclick = function () { window.__nfOpen = window.__nfOpen === r.dataset.s ? null : r.dataset.s; window.nfMount(root, F, NV); }; });
  var mb = root.querySelector(".nf-more"); if (mb) mb.onclick = function () { var xs = root.querySelectorAll(".nf-x"), hid = xs.length && xs[0].hidden; xs.forEach(function (e) { e.hidden = !hid; }); mb.textContent = hid ? "收起" : "more（還有 " + xs.length + " 則）"; };
};
/* ── ② 估值（雲端AM val_decomp v2 同一段程式；資料由參數傳入） ── */
window.vdMount = function (root, d, SRC) {
  addCss();
  root.innerHTML = '<div class="vd-root"><main class="vd-main"><h1 class="vd-h1">估值拆解</h1><p class="vd-lead">股價＝EPS × 本益比：這段漲跌是 EPS 變了，還是市場給的本益比變了</p><p class="vd-m" id="vd-asof">載入中…</p><div class="vd-tabs" id="vd-tabs" role="group" aria-label="期間"></div><div class="vd-sw" id="vd-mode" role="group" aria-label="口徑">口徑：</div><div class="vd-sw" id="vd-agg" role="group" aria-label="彙總">彙總：</div><div class="vd-sum" id="vd-sum"></div><div class="vd-leg"><span><i style="background:var(--vd-eps)"></i>EPS 貢獻（明年 EPS 共識變化）</span><span><i style="background:var(--vd-pe)"></i>本益比貢獻（前瞻本益比變化）</span><span><i style="background:var(--vd-ink);width:3px"></i>股價變化（兩段相加）</span></div><div class="vd-card" id="vd-tbl"></div><ul class="vd-rule" id="vd-rule"></ul><div class="vd-foot">整理市場分析師公開預估，非本站建議；共識資料自 2026-09-25 起。法說引句逐字取自本站法說擷取（公開資訊觀測站簡報、法說會錄音整理），不改寫。<br>EPS＝分析師明年 EPS 共識；本益比＝收盤（還原價）÷ 明年 EPS 共識；目標本益比＝分析師目標價中位數 ÷ 明年 EPS 共識。「相對大盤」＝族群值減全體有效個股的同口徑值（中位數或市值加權）。族群依目前細類回算，細類不到 3 檔的併回大類「・其他」；族群的 EPS、本益比、股價各自彙總，三者不一定剛好相乘，個股則剛好相乘。</div></main></div>';
  var $v = function (id) { return root.querySelector("#" + id); }, $vA = function (q) { return root.querySelectorAll(q); };
  var ST=["估值壓縮","雙殺","EPS 下修主導","其他","雙擊"];
var STX={"估值壓縮":"EPS 持平或上修、本益比下修","雙殺":"EPS 與本益比同步下修","EPS 下修主導":"EPS 下修，本益比沒有明顯下修","其他":"變化不大或方向不一","雙擊":"EPS 上修＋本益比擴張"};
var STR={"估值壓縮":"EPS 沒落後大盤、本益比卻比大盤多修","雙殺":"EPS 與本益比都落後大盤","EPS 下修主導":"EPS 落後大盤，本益比沒有比大盤差","其他":"跟大盤差不多","雙擊":"EPS 與本益比都強過大盤"};
function pc(x){return x==null?null:(Math.exp(x/100)-1)*100}
function f(x,d,pp){if(x==null)return"—";var v=pp?x:pc(x);d=d==null?1:d;var s=(v>0?"+":"")+v.toFixed(d)+(pp?"":"%");return '<span class="'+(v>0.05?"vd-up":v<-0.05?"vd-dn":"")+'">'+s+"</span>"}
function tag(s,rel){return '<span class="vd-tag vd-s'+ST.indexOf(s)+'" title="'+(rel?STR:STX)[s]+'">'+s+"</span>"}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function n2(x){return x==null?"—":(+x).toFixed(2)}
function md(s){return s?s.slice(5).replace("-","/"):""}
var D,cur="base",mode="rel",agg="med";
function bar(dE,dPE,scale){
  var w=function(x){return Math.abs(x)/scale*50};
  var h='<div class="vd-bar"><div class="vd-axis"></div>';
  var e1=50+dE/scale*50;
  h+='<div class="vd-seg vd-e" style="left:'+Math.min(50,e1)+'%;width:'+w(dE)+'%"></div>';
  var p1=e1+dPE/scale*50;
  h+='<div class="vd-seg vd-p" style="left:'+Math.min(e1,p1)+'%;width:'+w(dPE)+'%"></div>';
  h+='<div class="vd-mark" style="left:calc('+Math.max(0,Math.min(100,p1))+'% - 1px)"></div></div>';
  return h;
}
function sw(id,opts,get,set){var el=$v(id);opts.forEach(function(o){var b=document.createElement("button");b.className="vd-tab";b.dataset.v=o[0];b.textContent=o[1];b.onclick=function(){set(o[0]);render()};el.appendChild(b)});el._get=get}
function rows(){var G=D.groups[cur].slice(),k=mode+"_"+agg;
  G.sort(function(a,b){return (a.few-b.few)||(ST.indexOf(a.st[k])-ST.indexOf(b.st[k]))||((a[mode][agg].dPE||0)-(b[mode][agg].dPE||0))});return G}
function render(){
  var P=D.periods[cur],k=mode+"_"+agg,rel=mode==="rel",B=D.bench[cur][agg];
  $vA("#vd-tabs .vd-tab").forEach(function(b){b.setAttribute("aria-pressed",b.dataset.k===cur?"true":"false")});
  [["vd-mode",mode],["vd-agg",agg]].forEach(function(x){$vA("#"+x[0]+" .vd-tab").forEach(function(b){b.setAttribute("aria-pressed",b.dataset.v===x[1]?"true":"false")})});
  var G=rows();
  var cmp=G.filter(function(r){return r.st[k]==="估值壓縮"&&!r.few});
  var aname=agg==="med"?"中位數":"市值加權";
  $v("vd-sum").innerHTML="<b>"+P.label+"（股價 "+md(P.t0)+"～"+md(P.t1)+"）</b>："+
   (cmp.length?(rel?"<b>比大盤壓縮得更兇</b>的族群 ":"「估值壓縮」族群 ")+cmp.length+" 個："+cmp.slice(0,8).map(function(r){return esc(r.g)}).join("、")+(cmp.length>8?" 等":""):(rel?"沒有族群比大盤壓縮得更兇。":"目前沒有族群落在「估值壓縮」。"))+
   '<div class="vd-bench">大盤（'+D.bench[cur].n+" 檔"+aname+"）：EPS "+f(B.dE)+"、本益比 "+f(B.dPE)+"、股價 "+f(B.dP)+(rel?"；下表是族群減掉這組數字（百分點）":"")+"</div>"+
   '<div class="vd-bench">'+G.filter(function(r){return !r.few}).length+" 個族群（成員 ≥ "+D.rule.GRP_MIN_N+" 檔）："+ST.map(function(s){var n=G.filter(function(r){return r.st[k]===s&&!r.few}).length;return n?s+" "+n:null}).filter(Boolean).join("　")+"</div>";
  var u=rel?"（相對大盤）":"";
  var h='<div class="vd-row vd-hd"><div>狀態'+u+'</div><div>族群（檔數）</div><div class="vd-n">EPS</div><div class="vd-n">本益比</div><div class="vd-n">股價</div><div>分析師目標價＝EPS × 目標本益比（中位數，至 '+md(P.c1)+'）</div></div>';
  G.forEach(function(r,i){
    var v=r[mode][agg],hot=rel&&r.st[k]==="估值壓縮"&&!r.few;
    var cls="vd-row"+(r.st[k]==="估值壓縮"&&!r.few?" vd-cmp":"")+(r.few?" vd-few":"");
    h+='<div class="'+cls+'" data-i="'+i+'" role="button" tabindex="0" aria-expanded="false"><div class="vd-c-st">'+tag(r.st[k],rel)+'</div><div class="vd-c-g vd-g">'+esc(r.g)+' <small>'+r.n+' 檔'+(r.merged?"・併回大類":"")+(r.few?"・樣本少":"")+'</small>'+(hot?'<span class="vd-hot">比大盤壓縮得更兇</span>':"")+(r.ir90?'<span class="vd-irc" title="近 '+D.ir_rule.days+' 天最近一次法說提到產能／擴產／資本支出">近 '+D.ir_rule.days+' 天 '+r.ir90+' 檔法說提到產能</span>':"")+'</div>'+
      '<div class="vd-n"><span class="vd-lbl">EPS'+u+'</span>'+f(v.dE,1,rel)+'</div><div class="vd-n"><span class="vd-lbl">本益比'+u+'</span>'+f(v.dPE,1,rel)+'</div><div class="vd-n"><span class="vd-lbl">股價'+u+'</span>'+f(v.dP,1,rel)+'</div>'+
      '<div class="vd-c-tg vd-tg">目標價 '+f(r.dT)+'・目標本益比 '+f(r.dTPE)+'</div></div><div class="vd-exp" id="vd-x'+i+'"></div>';
  });
  $v("vd-tbl").innerHTML=h;
  $vA(".vd-row[data-i]").forEach(function(el){
    function tog(){var i=+el.dataset.i,x=$v("vd-x"+i);var o=!x.classList.contains("vd-open");
      if(o&&!x.innerHTML)x.innerHTML=members(G[i]);x.classList.toggle("vd-open",o);el.setAttribute("aria-expanded",o)}
    el.addEventListener("click",tog);el.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();tog()}});
  });
}
function irBlock(s){
  var v=s.ir;if(!v)return '<div class="vd-ir">法說：本站法說擷取還沒有這檔的資料。</div>';
  var url={};(v.src||[]).forEach(function(x){url[x.src]=x.url});
  var src=(v.src||[]).map(function(x){return x.url?'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.src)+'</a>':esc(x.src)}).join("、");
  var h='<div class="vd-ir"><b>最近一次法說 '+esc(v.date)+'</b>（'+src+'）'+(v.in90?"":"・超過 "+D.ir_rule.days+" 天");
  if(!v.q.length)return h+'：沒有提到產能／擴產／資本支出。</div>';
  h+='<ul>'+v.q.map(function(q){return '<li><span class="vd-q">「'+esc(q.t)+'」</span> <small>— '+esc(q.sec||"")+'・'+esc(q.src)+(q.ts?" "+esc(q.ts):"")+'</small></li>'}).join("")+'</ul>'+(v.more?'<small>另有 '+v.more+' 句未列出</small>':"");
  return h+'</div>';
}
function members(r){
  var rows=r.codes.map(function(c){return[c,D.stocks[c]]});
  var sc=10;rows.forEach(function(x){var p=x[1].p[cur].px;sc=Math.max(sc,Math.abs(p.dE),Math.abs(p.dE+p.dPE),Math.abs(p.dPE));var t=x[1].p[cur].tg;if(t)sc=Math.max(sc,Math.abs(t.dE),Math.abs(t.dE+t.dTPE),Math.abs(t.dTPE))});
  sc=Math.ceil(sc/10)*10;
  return rows.map(function(x){
    var c=x[0],s=x[1],p=s.p[cur].px,t=s.p[cur].tg;
    var h='<div class="vd-st"><div class="vd-nm">'+esc(s.nm)+' '+c+'<small>'+esc(s.sub||"")+'</small>'+tag(p.st)+'</div>';
    h+='<div>'+bar(p.dE,p.dPE,sc)+'<div class="vd-txt">股價 <b>'+f(p.dP)+'</b>（'+p.p0+'→'+p.p1+'）＝EPS '+f(p.dE)+'（'+n2(p.e0)+'→'+n2(p.e1)+'）× 本益比 '+f(p.dPE)+'（'+n2(p.pe0)+'→'+n2(p.pe1)+' 倍）'+(p.b!==D.periods[cur].t0?"・起點 "+md(p.b):"")+'</div></div>';
    h+='<div>'+(t?bar(t.dE,t.dTPE,sc)+'<div class="vd-txt">目標價中位 <b>'+f(t.dT)+'</b>（'+t.m0+'→'+t.m1+'，'+t.n+' 家）＝EPS '+f(t.dE)+' × 目標本益比 '+f(t.dTPE)+'（'+n2(t.t0)+'→'+n2(t.t1)+' 倍）</div>':'<div class="vd-txt">目標價資料不足</div>')+'</div>';
    h+=irBlock(s)+'</div>';
    return h;
  }).join("")+'<div class="vd-txt">個股為絕對值。左：股價拆解（收盤至 '+md(D.periods[cur].t1)+'）　右：分析師目標價拆解（共識至 '+md(D.periods[cur].c1)+'）　條長為對數尺度、全寬 ±'+sc+'（對數 %）；上條 EPS、下條本益比接在 EPS 後面，終點＝黑線＝股價</div>';
}

  D=d;if(d.default){mode=d.default.mode||mode;agg=d.default.agg||agg}
  $v("vd-asof").textContent="收盤資料至 "+d.asof_px+"、分析師共識至 "+d.asof_cons+"；"+Object.keys(d.stocks).length+" 檔（目標價與明年 EPS 家數皆 ≥ "+d.rule.MIN_N+"）。「自 9/25」的股價起點是日K庫第一個 ≥ 9/25 的交易日（"+d.periods.base.t0+"）。資料來源："+SRC+"。";
  var t=$v("vd-tabs");
  Object.keys(d.periods).forEach(function(k){var b=document.createElement("button");b.className="vd-tab";b.dataset.k=k;b.textContent=d.periods[k].label;b.onclick=function(){cur=k;render()};t.appendChild(b)});
  sw("vd-mode",[["rel","相對大盤"],["abs","絕對值"]],null,function(v){mode=v});
  sw("vd-agg",[["med","中位數"],["cw","市值加權"]],null,function(v){agg=v});
  var R=d.rule;
  $v("vd-rule").innerHTML="<li><b>狀態門檻</b>（v1 定的，看過 v1 結果沒有改）：EPS 持平帶 ±"+R.EPS_FLAT+"%，本益比變動門檻 "+R.PE_TH+"%（對數）；相對大盤時用同一組門檻判斷相對值。</li>"+
    ST.map(function(s){return"<li>"+tag(s)+" 絕對："+STX[s]+"；相對："+STR[s]+"</li>"}).join("")+"<li>成員不到 "+R.GRP_MIN_N+" 檔的族群標「樣本少」、排在最後。點族群列可展開個股與最近一次法說講產能的原文。</li>";
  render();
};
})();
