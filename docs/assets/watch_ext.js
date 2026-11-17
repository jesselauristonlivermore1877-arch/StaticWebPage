/* research/preview_b/watch_ext.js ── 看盤區兩個新區塊（11-16 晚【新】裁示；W 出預覽 docs/preview/watch_newsval/，11-16 晚 Evans「通通先上」→ 已接進會員站 index.html）
   預覽與正式版載入同一支檔、呼叫同一個函式，不另寫：
   ① nfMount(root, F, NV)：「盤中資金」併「產業快訊」——族群資金曲線（F＝dash.flow，s1 每分鐘累計主動淨買，億元）＋消息直線（NV＝dash_live.news_view()）＋族群多空燈號。
   （11-17 W：原本的 ② vdMount「估值」已拿掉——會員站估值頁籤 7fff321c 已拆、Market Insight 改用 docs/assets/vd3.js（雲端舊21），預覽 val_decomp 已刪。）
   樣式一律 nf- 前綴，不碰會員站既有樣式。
   ⚠ 本檔由 watch_ext.tpl.js 原樣複製出來（tools/watch_newsval_preview.py）；改 nfMount 改 tpl 再重組。 */
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
})();
