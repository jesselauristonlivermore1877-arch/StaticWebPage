/* 估值拆解 v3（圖版）── 雲端舊19 2026-11-17（Evans 11-17：估值拆解要視覺化、圖像化）
   vd3Mount(root, D, SRC)：介面跟 v2 的 vdMount（assets/watch_ext.js）相同，資料由參數傳入（正式檔 docs/data/val_decomp.json）。
   預覽 docs/preview/val_decomp/v3/ 與日後正式套版載入這同一支檔、呼叫同一個函式，不另寫。
   口徑：只讀 val_decomp.json 的欄位畫圖，不重算估值；不顯示目標價。
   圖：① 族群地圖（點圖：橫軸 EPS 貢獻、縱軸本益比貢獻）② 族群拆解（瀑布橫條：EPS 段接本益比段，黑線＝股價）
       ③ 點族群展開個股拆解（同樣瀑布橫條，個股三者剛好相乘）＋最近一次法說講產能的原文。
   樣式一律 vd- 前綴，並限定在 .vd-v3 底下，不碰其他樣式。 */
(function () {
var VD_CSS = `
.vd-v3{--vd-bg:#f6f5f1;--vd-ink:#1d1d1b;--vd-ink2:#5c5b57;--vd-line:#dcd9d0;--vd-card:#fff;--vd-grid:#ebe8e0;--vd-acc:#b0842f;
  --vd-up:#c8372d;--vd-dn:#1f8a4c;--vd-eps:#3d6fb6;--vd-pe:#c08a1e;--vd-hl:#fff4dc;--vd-hlb:#e3b65a;
  --vd-k0:#c77700;--vd-k1:#1f7a45;--vd-k2:#58a57c;--vd-k3:#9a9890;--vd-k4:#c8372d}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .vd-v3{--vd-bg:#16171a;--vd-ink:#ecebe7;--vd-ink2:#a4a29c;--vd-line:#34363b;--vd-card:#1f2125;--vd-grid:#2b2d32;--vd-acc:#d6a54a;
  --vd-up:#ef6a5e;--vd-dn:#4cbf7b;--vd-eps:#6f9be0;--vd-pe:#d6a54a;--vd-hl:#3a2f18;--vd-hlb:#a67c2c;
  --vd-k0:#f0b03c;--vd-k1:#3fae6c;--vd-k2:#93d3ad;--vd-k3:#85847f;--vd-k4:#ef6a5e}}
[data-theme="dark"] .vd-v3{--vd-bg:#16171a;--vd-ink:#ecebe7;--vd-ink2:#a4a29c;--vd-line:#34363b;--vd-card:#1f2125;--vd-grid:#2b2d32;--vd-acc:#d6a54a;
  --vd-up:#ef6a5e;--vd-dn:#4cbf7b;--vd-eps:#6f9be0;--vd-pe:#d6a54a;--vd-hl:#3a2f18;--vd-hlb:#a67c2c;
  --vd-k0:#f0b03c;--vd-k1:#3fae6c;--vd-k2:#93d3ad;--vd-k3:#85847f;--vd-k4:#ef6a5e}
.vd-v3{background:var(--vd-bg);color:var(--vd-ink);font:15px/1.6 system-ui,-apple-system,"Noto Sans TC",sans-serif;white-space:normal}
.vd-v3 *{box-sizing:border-box}
.vd-v3 .vd-main{max-width:1100px;margin:0 auto;padding:16px 0 40px}
.vd-v3 .vd-h1{font-size:21px;margin:0 0 6px}
.vd-v3 .vd-h2{font-size:17px;margin:22px 0 4px}
.vd-v3 .vd-lead{font-size:16px;margin:0 0 6px;font-weight:600}
.vd-v3 .vd-m{color:var(--vd-ink2);font-size:13px;margin:0 0 10px}
.vd-v3 .vd-tabs,.vd-v3 .vd-sw{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0;font-size:13px;color:var(--vd-ink2)}
.vd-v3 .vd-tab{border:1px solid var(--vd-line);background:var(--vd-card);color:var(--vd-ink);border-radius:18px;padding:5px 14px;font-size:14px;cursor:pointer;font-family:inherit}
.vd-v3 .vd-sw .vd-tab{font-size:13px;padding:3px 11px}
.vd-v3 .vd-tab[aria-pressed="true"]{background:var(--vd-acc);border-color:var(--vd-acc);color:#fff;font-weight:700}
.vd-v3 .vd-sum{background:var(--vd-hl);border:1px solid var(--vd-hlb);border-radius:10px;padding:10px 12px;margin:8px 0 6px;font-size:14px}
.vd-v3 .vd-bench{font-size:12.5px;color:var(--vd-ink2);margin:4px 0 0}
.vd-v3 .vd-up{color:var(--vd-up)}.vd-v3 .vd-dn{color:var(--vd-dn)}
.vd-v3 .vd-tag{display:inline-block;border-radius:6px;padding:0 7px;font-size:12px;font-weight:700;white-space:nowrap;border:1px solid currentColor;line-height:1.6}
.vd-v3 .vd-s0{color:#8a5a00;background:#fde9bf;border-color:#e3b65a}
.vd-v3 .vd-s1{color:#fff;background:var(--vd-k1);border-color:var(--vd-k1)}
.vd-v3 .vd-s2{color:var(--vd-dn)}
.vd-v3 .vd-s3{color:var(--vd-ink2)}
.vd-v3 .vd-s4{color:#fff;background:var(--vd-k4);border-color:var(--vd-k4)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .vd-v3 .vd-s0{color:#ffd88a;background:#4a3812}:root:not([data-theme="light"]) .vd-v3 .vd-s1{color:#0d1a12}}
[data-theme="dark"] .vd-v3 .vd-s0{color:#ffd88a;background:#4a3812}
[data-theme="dark"] .vd-v3 .vd-s1{color:#0d1a12}
.vd-v3 .vd-leg{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:12.5px;color:var(--vd-ink2);margin:6px 0}
.vd-v3 .vd-leg i{display:inline-block;width:12px;height:12px;vertical-align:-1px;margin-right:4px;border-radius:2px}
.vd-v3 .vd-leg i.vd-dot{border-radius:50%}
.vd-v3 .vd-leg i.vd-ln{width:3px;border-radius:0}
.vd-v3 .vd-leg i.vd-dash{width:0;border-left:2px dashed var(--vd-ink2);border-radius:0}
.vd-v3 .vd-card{background:var(--vd-card);border:1px solid var(--vd-line);border-radius:10px;padding:8px 12px}
.vd-v3 .vd-note{font-size:12.5px;color:var(--vd-ink2);margin:4px 0}
.vd-v3 .vd-map{position:relative}
.vd-v3 .vd-map svg,.vd-v3 .vd-plot svg,.vd-v3 .vd-ax svg{display:block;overflow:visible}
.vd-v3 .vd-pt{cursor:pointer}
.vd-v3 .vd-pt:focus{outline:none}
.vd-v3 .vd-pt:focus .vd-dt,.vd-v3 .vd-pt.vd-on .vd-dt{stroke:var(--vd-ink);stroke-width:2.5}
.vd-v3 .vd-pick{font-size:13px;min-height:1.6em;margin:2px 0 0}
.vd-v3 .vd-r{display:grid;grid-template-columns:minmax(0,15.5em) minmax(0,1fr);column-gap:14px;align-items:center;padding:7px 0;border-top:1px solid var(--vd-line)}
.vd-v3 .vd-r.vd-hd{border-top:0;padding:0}
.vd-v3 .vd-r[data-i]{cursor:pointer}
.vd-v3 .vd-r[data-i]:hover{background:var(--vd-bg)}
.vd-v3 .vd-r{padding-left:8px;padding-right:4px}
.vd-v3 .vd-r.vd-cmp{background:var(--vd-hl);box-shadow:inset 4px 0 0 var(--vd-hlb)}
.vd-v3 .vd-r.vd-few{opacity:.62}
.vd-v3 .vd-lab{grid-row:1/3;font-size:14px;overflow-wrap:anywhere;line-height:1.45}
.vd-v3 .vd-lab b{font-weight:700}
.vd-v3 .vd-lab small{color:var(--vd-ink2);font-size:12px}
.vd-v3 .vd-plot{min-width:0}
.vd-v3 .vd-num{font-size:12.5px;color:var(--vd-ink2);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.vd-v3 .vd-num b{color:var(--vd-ink)}
.vd-v3 .vd-hd .vd-lab{font-size:12px;color:var(--vd-ink2)}
.vd-v3 .vd-hot{display:inline-block;font-size:11.5px;font-weight:700;color:#fff;background:var(--vd-dn);border-radius:5px;padding:0 6px;margin-left:4px;white-space:nowrap}
.vd-v3 .vd-irc{display:inline-block;font-size:11.5px;color:var(--vd-eps);border:1px solid var(--vd-eps);border-radius:5px;padding:0 6px;margin-left:4px;white-space:nowrap}
.vd-v3 .vd-exp{display:none;padding:6px 0 12px 12px;border-left:3px solid var(--vd-line);margin:0 0 6px}
.vd-v3 .vd-exp.vd-open{display:block}
.vd-v3 .vd-mh{font-size:13px;font-weight:700;margin:4px 0}
.vd-v3 .vd-ir{grid-column:1/-1;font-size:12.5px;background:var(--vd-bg);border:1px solid var(--vd-line);border-radius:8px;padding:6px 10px;margin-top:6px}
.vd-v3 .vd-ir ul{margin:4px 0 0;padding-left:18px}.vd-v3 .vd-ir li{margin:2px 0}
.vd-v3 .vd-ir a{color:var(--vd-acc)}
.vd-v3 .vd-ir .vd-q{color:var(--vd-ink)}
.vd-v3 .vd-rule{font-size:13px;color:var(--vd-ink2);margin:14px 0 0;padding-left:20px}
.vd-v3 .vd-rule li{margin:2px 0}
.vd-v3 .vd-foot{margin-top:18px;font-size:13px;color:var(--vd-ink2);border-top:1px solid var(--vd-line);padding-top:10px}
@media (max-width:640px){
  .vd-v3 .vd-r{grid-template-columns:minmax(0,1fr)}
  .vd-v3 .vd-lab{grid-row:auto}
  .vd-v3 .vd-hd .vd-lab{display:none}
  .vd-v3 .vd-exp{padding-left:8px}
}
`;
function vdCss() { if (document.getElementById("vd-v3-css")) return; var s = document.createElement("style"); s.id = "vd-v3-css"; s.textContent = VD_CSS; document.head.appendChild(s); }

var ST = ["估值壓縮", "雙殺", "EPS 下修主導", "其他", "雙擊"];
var STX = {"估值壓縮": "EPS 持平或上修、本益比下修", "雙殺": "EPS 與本益比同步下修", "EPS 下修主導": "EPS 下修，本益比沒有明顯下修", "其他": "變化不大或方向不一", "雙擊": "EPS 上修＋本益比擴張"};
var STR = {"估值壓縮": "EPS 沒落後大盤、本益比卻比大盤多修", "雙殺": "EPS 與本益比都落後大盤", "EPS 下修主導": "EPS 落後大盤，本益比沒有比大盤差", "其他": "跟大盤差不多", "雙擊": "EPS 與本益比都強過大盤"};
var NS = "http://www.w3.org/2000/svg";
/* 資料是對數 %（ln 比值×100）；絕對值顯示時換成 %，相對大盤顯示百分點（同 v2） */
function vdPc(x) { return x == null ? null : (Math.exp(x / 100) - 1) * 100; }
function vdLn(p) { return Math.log(1 + p / 100) * 100; }
function vdFmt(x, d, pp) { if (x == null) return "—"; var v = pp ? x : vdPc(x); d = d == null ? 1 : d; var a = Math.abs(v).toFixed(d); return (+a === 0 ? "" : v > 0 ? "+" : "−") + a + (pp ? "" : "%"); }
function vdF(x, d, pp) { if (x == null) return "—"; var v = pp ? x : vdPc(x); return '<span class="' + (v > 0.05 ? "vd-up" : v < -0.05 ? "vd-dn" : "") + '">' + vdFmt(x, d, pp) + "</span>"; }
function vdEsc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function vdN2(x) { return x == null ? "—" : (+x).toFixed(2); }
function vdMd(s) { return s ? s.slice(5).replace("-", "/") : ""; }
function vdTag(s, rel) { return '<span class="vd-tag vd-s' + ST.indexOf(s) + '" title="' + (rel ? STR : STX)[s] + '">' + s + "</span>"; }
function vdNice(x) { if (!(x > 0)) return 1; var p = Math.pow(10, Math.floor(Math.log10(x))), m = x / p; return (m < 1.5 ? 1 : m < 3 ? 2 : m < 3.75 ? 2.5 : m < 7 ? 5 : 10) * p; }
/* 範圍：含 0，左右各留一點邊 */
function vdDom(vals) {
  var lo = 0, hi = 0; vals.forEach(function (v) { if (v != null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
  if (hi - lo < 4) { lo -= 2; hi += 2; }
  var pad = (hi - lo) * 0.05; return [lo - pad, hi + pad];
}
/* 刻度：絕對值用整齊的 % 再換回對數位置；相對大盤直接用百分點 */
function vdTicks(dom, pct, px) {
  var want = Math.max(2, Math.min(6, Math.floor(px / 70)));
  var a = pct ? vdPc(dom[0]) : dom[0], b = pct ? vdPc(dom[1]) : dom[1];
  var st = vdNice((b - a) / want), out = [];
  for (var t = Math.ceil(a / st) * st; t <= b + 1e-9; t += st) {
    var v = Math.abs(t) < 1e-9 ? 0 : t;
    if (pct && v <= -99) continue;
    out.push({v: pct ? vdLn(v) : v, t: (v > 0 ? "+" : v < 0 ? "−" : "") + +Math.abs(v).toFixed(st < 1 ? 1 : 0) + (pct ? "%" : "")});
  }
  /* 級距太粗時某一側會沒有刻度（例：−44%～+110% 只剩 0、+50、+100）→ 補一個不超過邊界的整齊值 */
  function floorNice(x) { var p = Math.pow(10, Math.floor(Math.log10(x))), m = x / p; return (m >= 5 ? 5 : m >= 4 ? 4 : m >= 2.5 ? 2.5 : m >= 2 ? 2 : 1) * p; }
  [[a, -1], [b, 1]].forEach(function (e) {
    var lim = Math.abs(e[0]); if (e[0] * e[1] <= 0 || lim < st * 0.3) return;
    if (out.some(function (t) { return t.v * e[1] > 0; })) return;
    var v = e[1] * floorNice(lim * 0.95); if (pct && v <= -99) return;
    var o = {v: pct ? vdLn(v) : v, t: (v > 0 ? "+" : "−") + +Math.abs(v).toFixed(Math.abs(v) < 1 ? 1 : 0) + (pct ? "%" : "")};
    if (e[1] < 0) out.unshift(o); else out.push(o);
  });
  return out;
}
/* 刻度字太擠時要省略：先留 0，其餘依序、跟已留的距離 ≥ gap 才留 */
function vdKeep(ts, pos, gap) {
  var kept = [], ok = {};
  ts.forEach(function (t, i) { if (t.v === 0) { kept.push(pos(t.v)); ok[i] = 1; } });
  ts.forEach(function (t, i) { var q = pos(t.v); if (ok[i] || kept.some(function (k) { return Math.abs(k - q) < gap; })) return; kept.push(q); ok[i] = 1; });
  return ok;
}
function vdEl(tag, at, txt) { var e = document.createElementNS(NS, tag); for (var k in at) e.setAttribute(k, at[k]); if (txt != null) e.textContent = txt; return e; }
function vdSvg(w, h) { return vdEl("svg", {width: w, height: h, viewBox: "0 0 " + w + " " + h, role: "img"}); }
var PADX = 8;
function vdX(dom, w) { return function (v) { return PADX + (v - dom[0]) / (dom[1] - dom[0]) * (w - 2 * PADX); }; }
/* 刻度列（放在橫條表頭與表尾） */
function vdAxis(box, dom, pct, w, cap) {
  var X = vdX(dom, w), s = vdSvg(w, 20), ts = vdTicks(dom, pct, w), ok = vdKeep(ts, X, 40);
  ts.forEach(function (t, i) {
    var x = X(t.v); if (!ok[i]) return;
    var an = x < 18 ? "start" : x > w - 18 ? "end" : "middle";
    s.appendChild(vdEl("line", {x1: x, x2: x, y1: 15, y2: 20, stroke: "var(--vd-ink2)"}));
    s.appendChild(vdEl("text", {x: x, y: 11, "text-anchor": an, "font-size": 11, fill: "var(--vd-ink2)"}, t.t));
  });
  box.innerHTML = ""; box.appendChild(s);
  if (cap) { var c = document.createElement("div"); c.className = "vd-note"; c.style.margin = "0"; c.textContent = cap; box.appendChild(c); }
}
/* 一列瀑布橫條：0 → EPS 段（上）→ 本益比段（下，接在 EPS 後面）；黑線＝股價；虛線＝大盤（選用） */
function vdBar(box, dom, pct, w, e, pe, p, bench) {
  var X = vdX(dom, w), H = 28, s = vdSvg(w, H);
  vdTicks(dom, pct, w).forEach(function (t) { s.appendChild(vdEl("line", {x1: X(t.v), x2: X(t.v), y1: 0, y2: H, stroke: "var(--vd-grid)"})); });
  var x0 = X(0), xe = X(e || 0), xp = X((e || 0) + (pe || 0));
  s.appendChild(vdEl("line", {x1: x0, x2: x0, y1: 0, y2: H, stroke: "var(--vd-ink2)", "stroke-width": 1}));
  if (bench != null) s.appendChild(vdEl("line", {x1: X(bench), x2: X(bench), y1: 0, y2: H, stroke: "var(--vd-ink2)", "stroke-width": 1.5, "stroke-dasharray": "3 3"}));
  function seg(a, b, y, col) { var l = Math.min(a, b), wd = Math.max(Math.abs(b - a), (a !== b ? 1.5 : 0)); if (wd) s.appendChild(vdEl("rect", {x: l, y: y, width: wd, height: 10, rx: 2, fill: col})); }
  seg(x0, xe, 3, "var(--vd-eps)");
  s.appendChild(vdEl("line", {x1: xe, x2: xe, y1: 13, y2: 15, stroke: "var(--vd-ink2)"}));
  seg(xe, xp, 15, "var(--vd-pe)");
  if (p != null) { var xm = Math.max(1.5, Math.min(w - 1.5, X(p))); s.appendChild(vdEl("rect", {x: xm - 1.5, y: 0, width: 3, height: H, fill: "var(--vd-ink)"})); }
  box.innerHTML = ""; box.appendChild(s);
}

window.vd3Mount = function (root, D, SRC) {
  vdCss();
  var cur = "base", mode = "rel", agg = "med", openI = {}, pick = null;
  if (D.default) { mode = D.default.mode || mode; agg = D.default.agg || agg; }
  root.innerHTML = '<div class="vd-v3"><div class="vd-main">' +
    '<h1 class="vd-h1">估值拆解</h1><p class="vd-lead">股價＝EPS × 本益比：這段漲跌是 EPS 變了，還是市場給的本益比變了</p>' +
    '<p class="vd-m vd-asof"></p>' +
    '<div class="vd-tabs vd-per" role="group" aria-label="期間"></div>' +
    '<div class="vd-sw vd-mode" role="group" aria-label="口徑">口徑：</div>' +
    '<div class="vd-sw vd-agg" role="group" aria-label="彙總">彙總：</div>' +
    '<div class="vd-sum"></div>' +
    '<h2 class="vd-h2">族群地圖：EPS 貢獻 × 本益比貢獻</h2>' +
    '<p class="vd-note vd-mapnote"></p>' +
    '<div class="vd-card"><div class="vd-map"></div><div class="vd-pick" aria-live="polite"></div></div>' +
    '<div class="vd-leg vd-stleg"></div>' +
    '<h2 class="vd-h2">族群拆解：股價＝EPS × 本益比</h2>' +
    '<div class="vd-leg"><span><i style="background:var(--vd-eps)"></i>EPS 貢獻（明年 EPS 共識變化）</span><span><i style="background:var(--vd-pe)"></i>本益比貢獻（前瞻本益比變化，接在 EPS 後面）</span><span><i class="vd-ln" style="background:var(--vd-ink)"></i>股價變化</span><span class="vd-bleg"><i class="vd-dash"></i>大盤股價變化</span></div>' +
    '<p class="vd-note vd-barnote"></p>' +
    '<div class="vd-card vd-list"></div>' +
    '<ul class="vd-rule"></ul>' +
    '<div class="vd-foot">整理市場分析師公開預估，非本站建議；共識資料自 2026-09-25 起。法說引句逐字取自本站法說擷取（公開資訊觀測站簡報、法說會錄音整理），不改寫。<br>' +
    'EPS＝分析師明年 EPS 共識；本益比＝收盤（還原價）÷ 明年 EPS 共識；目標本益比＝分析師目標價中位數 ÷ 明年 EPS 共識。「相對大盤」＝族群值減全體有效個股的同口徑值（中位數或市值加權）。族群依目前細類回算，細類不到 3 檔的併回大類「・其他」；族群的 EPS、本益比、股價各自彙總，三者不一定剛好相乘，個股則剛好相乘。</div>' +
    '</div></div>';
  var $ = function (q) { return root.querySelector(q); }, $$ = function (q) { return root.querySelectorAll(q); };

  $(".vd-asof").textContent = "收盤資料至 " + D.asof_px + "、分析師共識至 " + D.asof_cons + "；" + Object.keys(D.stocks).length + " 檔（目標價與明年 EPS 家數皆 ≥ " + D.rule.MIN_N + "）。「自 9/25」的股價起點是日K庫第一個 ≥ 9/25 的交易日（" + D.periods.base.t0 + "）。資料來源：" + SRC + "。";
  function btns(sel, opts, get, set) {
    var el = $(sel);
    opts.forEach(function (o) { var b = document.createElement("button"); b.className = "vd-tab"; b.dataset.v = o[0]; b.textContent = o[1]; b.onclick = function () { set(o[0]); openI = {}; pick = null; render(); }; el.appendChild(b); });
    el._get = get;
  }
  btns(".vd-per", Object.keys(D.periods).map(function (k) { return [k, D.periods[k].label]; }), function () { return cur; }, function (v) { cur = v; });
  btns(".vd-mode", [["rel", "相對大盤"], ["abs", "絕對值"]], function () { return mode; }, function (v) { mode = v; });
  btns(".vd-agg", [["med", "中位數"], ["cw", "市值加權"]], function () { return agg; }, function (v) { agg = v; });
  var R = D.rule;
  $(".vd-rule").innerHTML = "<li><b>狀態門檻</b>（v1 定的，沒有改）：EPS 持平帶 ±" + R.EPS_FLAT + "%，本益比變動門檻 " + R.PE_TH + "%（對數）；相對大盤時用同一組門檻判斷相對值。狀態直接取自資料檔，圖上不另行判斷。</li>" +
    ST.map(function (s) { return "<li>" + vdTag(s) + " 絕對：" + STX[s] + "；相對：" + STR[s] + "</li>"; }).join("") +
    "<li>成員不到 " + R.GRP_MIN_N + " 檔的族群標「樣本少」、排在最後，也不畫進族群地圖。點族群列（或地圖上的圓點）可展開個股與最近一次法說講產能的原文。</li>" +
    "<li>橫條與地圖都用對數尺度（EPS 段＋本益比段＝股價，個股剛好相等）；同一張圖內共用同一把尺，可以直接比長短。</li>";
  $(".vd-stleg").innerHTML = ST.map(function (s, i) { return '<span><i class="vd-dot" style="background:var(--vd-k' + i + ')"></i>' + s + "</span>"; }).join("");

  function rows() {
    var G = D.groups[cur].slice(), k = mode + "_" + agg;
    G.sort(function (a, b) { return (a.few - b.few) || (ST.indexOf(a.st[k]) - ST.indexOf(b.st[k])) || ((a[mode][agg].dPE || 0) - (b[mode][agg].dPE || 0)); });
    return G;
  }
  var G = [];
  function render() {
    var P = D.periods[cur], k = mode + "_" + agg, rel = mode === "rel", B = D.bench[cur][agg];
    [[".vd-per", cur], [".vd-mode", mode], [".vd-agg", agg]].forEach(function (x) { $$(x[0] + " .vd-tab").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.v === x[1] ? "true" : "false"); }); });
    G = rows();
    var cmp = G.filter(function (r) { return r.st[k] === "估值壓縮" && !r.few; });
    var aname = agg === "med" ? "中位數" : "市值加權";
    $(".vd-sum").innerHTML = "<b>" + P.label + "（股價 " + vdMd(P.t0) + "～" + vdMd(P.t1) + "）</b>：" +
      (cmp.length ? (rel ? "<b>比大盤壓縮得更兇</b>的族群 " : "「估值壓縮」族群 ") + cmp.length + " 個：" + cmp.slice(0, 8).map(function (r) { return vdEsc(r.g); }).join("、") + (cmp.length > 8 ? " 等" : "") : (rel ? "沒有族群比大盤壓縮得更兇。" : "目前沒有族群落在「估值壓縮」。")) +
      '<div class="vd-bench">大盤（' + D.bench[cur].n + " 檔" + aname + "）：EPS " + vdF(B.dE) + "、本益比 " + vdF(B.dPE) + "、股價 " + vdF(B.dP) + (rel ? "；下面兩張圖都是族群減掉這組數字（百分點），0＝跟大盤一樣" : "") + "</div>" +
      '<div class="vd-bench">' + G.filter(function (r) { return !r.few; }).length + " 個族群（成員 ≥ " + R.GRP_MIN_N + " 檔）：" + ST.map(function (s) { var n = G.filter(function (r) { return r.st[k] === s && !r.few; }).length; return n ? s + " " + n : null; }).filter(Boolean).join("　") + "</div>";
    var unit = rel ? "百分點（相對大盤）" : "%（" + aname + "）";
    $(".vd-mapnote").innerHTML = "橫軸＝EPS 貢獻、縱軸＝本益比貢獻，單位" + unit + "；" + (rel ? "原點＝大盤。" : "空心菱形＝大盤。") + "右下：EPS 往上、本益比往下；左下：兩者都往下；右上：兩者都往上。點圓點看數字、展開族群。";
    $(".vd-barnote").innerHTML = "單位" + unit + "。藍段從 0 畫到 EPS 貢獻，金段接著畫本益比貢獻，粗直線是族群股價變化" + (rel ? "（0＝大盤）" : "，虛線是大盤") + "；族群的三者各自彙總，粗直線不一定剛好落在金段終點。";
    $(".vd-bleg").style.display = rel ? "none" : "";
    var u = rel ? "（相對大盤，百分點）" : "";
    var h = '<div class="vd-r vd-hd"><div class="vd-lab">狀態・族群（檔數）</div><div class="vd-ax vd-ax-t"></div></div>';
    G.forEach(function (r, i) {
      var v = r[mode][agg], hot = rel && r.st[k] === "估值壓縮" && !r.few;
      var cls = "vd-r" + (r.st[k] === "估值壓縮" && !r.few ? " vd-cmp" : "") + (r.few ? " vd-few" : "");
      h += '<div class="' + cls + '" data-i="' + i + '" role="button" tabindex="0" aria-expanded="' + (openI[i] ? "true" : "false") + '">' +
        '<div class="vd-lab">' + vdTag(r.st[k], rel) + " <b>" + vdEsc(r.g) + "</b> <small>" + r.n + " 檔" + (r.merged ? "・併回大類" : "") + (r.few ? "・樣本少" : "") + "</small>" +
        (hot ? '<span class="vd-hot">比大盤壓縮得更兇</span>' : "") + (r.ir90 ? '<span class="vd-irc" title="近 ' + D.ir_rule.days + ' 天最近一次法說提到產能／擴產／資本支出">近 ' + D.ir_rule.days + " 天 " + r.ir90 + " 檔法說提到產能</span>" : "") + "</div>" +
        '<div class="vd-plot" data-g="' + i + '"></div>' +
        '<div class="vd-num">EPS ' + vdF(v.dE, 1, rel) + "・本益比 " + vdF(v.dPE, 1, rel) + "・股價 <b>" + vdF(v.dP, 1, rel) + "</b>" + u + "</div></div>" +
        '<div class="vd-exp' + (openI[i] ? " vd-open" : "") + '" data-x="' + i + '"></div>';
    });
    h += '<div class="vd-r vd-hd"><div class="vd-lab"></div><div class="vd-ax vd-ax-b"></div></div>';
    $(".vd-list").innerHTML = h;
    $$(".vd-r[data-i]").forEach(function (el) {
      function tog() { toggle(+el.dataset.i); }
      el.addEventListener("click", tog);
      el.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tog(); } });
    });
    Object.keys(openI).forEach(function (i) { fillMembers(+i); });
    draw();
  }
  function toggle(i, force) {
    var x = $('.vd-exp[data-x="' + i + '"]'), row = $('.vd-r[data-i="' + i + '"]'); if (!x) return;
    var o = force != null ? force : !openI[i];
    if (o) { openI[i] = 1; x.classList.add("vd-open"); fillMembers(i); } else { delete openI[i]; x.classList.remove("vd-open"); }
    row.setAttribute("aria-expanded", o ? "true" : "false");
  }
  /* 族群地圖（點圖） */
  function drawMap() {
    var box = $(".vd-map"), k = mode + "_" + agg, rel = mode === "rel", B = D.bench[cur][agg];
    var w = box.clientWidth; if (!w) return;
    var pts = G.map(function (r, i) { return {r: r, i: i, x: r[mode][agg].dE, y: r[mode][agg].dPE}; }).filter(function (p) { return !p.r.few && p.x != null && p.y != null; });
    var xs = pts.map(function (p) { return p.x; }), ys = pts.map(function (p) { return p.y; });
    if (!rel) { xs.push(B.dE); ys.push(B.dPE); }
    var narrow = w < 520, mL = 46, mR = 10, mT = 26, mB = 34;
    var H = Math.round(Math.max(260, Math.min(420, w * (narrow ? 0.95 : 0.55))));
    var dx = vdDom(xs), dy = vdDom(ys);
    var X = function (v) { return mL + (v - dx[0]) / (dx[1] - dx[0]) * (w - mL - mR); };
    var Y = function (v) { return mT + (dy[1] - v) / (dy[1] - dy[0]) * (H - mT - mB); };
    var s = vdSvg(w, H); s.setAttribute("aria-label", "族群地圖：橫軸 EPS 貢獻、縱軸本益比貢獻");
    var pct = !rel;
    var tx = vdTicks(dx, pct, w - mL - mR), okx = vdKeep(tx, X, 40);
    tx.forEach(function (t, i) {
      var x = X(t.v); s.appendChild(vdEl("line", {x1: x, x2: x, y1: mT, y2: H - mB, stroke: "var(--vd-grid)"}));
      if (okx[i]) { s.appendChild(vdEl("text", {x: x, y: H - mB + 15, "text-anchor": "middle", "font-size": 11, fill: "var(--vd-ink2)"}, t.t)); }
    });
    var ty = vdTicks(dy, pct, (H - mT - mB) * 1.4), oky = vdKeep(ty, Y, 18);
    ty.forEach(function (t, i) {
      var y = Y(t.v); s.appendChild(vdEl("line", {x1: mL, x2: w - mR, y1: y, y2: y, stroke: "var(--vd-grid)"}));
      if (oky[i]) { s.appendChild(vdEl("text", {x: mL - 6, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--vd-ink2)"}, t.t)); }
    });
    s.appendChild(vdEl("line", {x1: X(0), x2: X(0), y1: mT, y2: H - mB, stroke: "var(--vd-ink2)"}));
    s.appendChild(vdEl("line", {x1: mL, x2: w - mR, y1: Y(0), y2: Y(0), stroke: "var(--vd-ink2)"}));
    s.appendChild(vdEl("text", {x: w - mR, y: H - 4, "text-anchor": "end", "font-size": 11.5, fill: "var(--vd-ink)", "font-weight": 700}, "EPS 貢獻 →"));
    s.appendChild(vdEl("text", {x: 2, y: 13, "text-anchor": "start", "font-size": 11.5, fill: "var(--vd-ink)", "font-weight": 700}, "↑ 本益比貢獻"));
    /* 標籤：由極端值往內放，跟已放的標籤重疊就不寫字（圓點照畫，點了看名字） */
    var placed = [], fs = narrow ? 10.5 : 11.5, rr = narrow ? 5.5 : 6.5;
    var order = pts.slice().sort(function (a, b) { return (Math.abs(b.x) + Math.abs(b.y)) - (Math.abs(a.x) + Math.abs(a.y)); });
    var gl = vdEl("g", {}), gd = vdEl("g", {});
    order.forEach(function (p) {
      var cx = X(p.x), cy = Y(p.y), tw = p.r.g.length * fs * 0.98 + 4, gap = rr + (pick === p.i ? 7 : 3), right = cx + gap + tw <= w - mR;
      var bx0 = right ? cx + gap : cx - gap - tw, bb = [bx0, cy - fs * 0.7, bx0 + tw, cy + fs * 0.5];
      var hit = bx0 < mL || placed.some(function (q) { return !(bb[2] < q[0] || bb[0] > q[2] || bb[3] < q[1] || bb[1] > q[3]); }) ||
        pts.some(function (o) { if (o === p) return false; var ox = X(o.x), oy = Y(o.y); return ox + rr > bb[0] && ox - rr < bb[2] && oy + rr > bb[1] && oy - rr < bb[3]; });
      if (!hit) { placed.push(bb); gl.appendChild(vdEl("text", {x: right ? bx0 : bx0 + tw, y: cy + fs * 0.36, "text-anchor": right ? "start" : "end", "font-size": fs, fill: "var(--vd-ink)", "paint-order": "stroke", stroke: "var(--vd-card)", "stroke-width": 3, "stroke-linejoin": "round"}, p.r.g)); }
      var g = vdEl("g", {"class": "vd-pt" + (pick === p.i ? " vd-on" : ""), tabindex: 0, role: "button", "aria-label": p.r.g});
      g.appendChild(vdEl("title", {}, p.r.g + "：EPS " + vdFmt(p.x, 1, rel) + "、本益比 " + vdFmt(p.y, 1, rel) + "（" + p.r.st[k] + "）"));
      g.appendChild(vdEl("circle", {cx: cx, cy: cy, r: rr + 9, fill: "transparent"}));
      g.appendChild(vdEl("circle", {"class": "vd-dt", cx: cx, cy: cy, r: rr, fill: "var(--vd-k" + ST.indexOf(p.r.st[k]) + ")", stroke: "var(--vd-card)", "stroke-width": 1.5}));
      function go() { pick = p.i; showPick(); drawMap(); }
      g.addEventListener("click", go);
      g.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
      gd.appendChild(g);
    });
    s.appendChild(gl); s.appendChild(gd);
    if (!rel) {
      var bx = X(B.dE), by = Y(B.dPE);
      s.appendChild(vdEl("path", {d: "M" + bx + " " + (by - 7) + "L" + (bx + 7) + " " + by + "L" + bx + " " + (by + 7) + "L" + (bx - 7) + " " + by + "Z", fill: "var(--vd-card)", stroke: "var(--vd-ink)", "stroke-width": 2}));
      s.appendChild(vdEl("text", {x: bx + 10, y: by - 6, "font-size": 11.5, fill: "var(--vd-ink)", "font-weight": 700, "paint-order": "stroke", stroke: "var(--vd-card)", "stroke-width": 3}, "大盤"));
    }
    box.innerHTML = ""; box.appendChild(s);
  }
  function showPick() {
    var el = $(".vd-pick"), rel = mode === "rel", k = mode + "_" + agg;
    if (pick == null || !G[pick]) { el.innerHTML = '<span style="color:var(--vd-ink2)">點地圖上的圓點：這裡顯示族群數字，並可展開下面的個股拆解。</span>'; return; }
    var r = G[pick], v = r[mode][agg];
    el.innerHTML = vdTag(r.st[k], rel) + " <b>" + vdEsc(r.g) + "</b>（" + r.n + " 檔）EPS " + vdF(v.dE, 1, rel) + "・本益比 " + vdF(v.dPE, 1, rel) + "・股價 " + vdF(v.dP, 1, rel) +
      ' <button class="vd-tab vd-go" style="font-size:12px;padding:1px 10px">看個股拆解 ↓</button>';
    el.querySelector(".vd-go").onclick = function () { toggle(pick, true); var row = $('.vd-r[data-i="' + pick + '"]'); if (row && row.scrollIntoView) row.scrollIntoView({behavior: "smooth", block: "start"}); };
  }
  /* 族群拆解橫條：所有族群同一把尺 */
  function drawBars() {
    var rel = mode === "rel", B = D.bench[cur][agg], plots = $$(".vd-list > .vd-r > .vd-plot");
    if (!plots.length) return; var w = plots[0].clientWidth; if (!w) return;
    var vals = [];
    G.forEach(function (r) { var v = r[mode][agg]; vals.push(v.dE, (v.dE || 0) + (v.dPE || 0), v.dP); });
    if (!rel) vals.push(B.dP);
    var dom = vdDom(vals), pct = !rel;
    vdAxis($(".vd-ax-t"), dom, pct, w); vdAxis($(".vd-ax-b"), dom, pct, w, rel ? "百分點（0＝大盤）" : "%（對數尺度）");
    plots.forEach(function (pl) { var v = G[+pl.dataset.g][mode][agg]; vdBar(pl, dom, pct, w, v.dE, v.dPE, v.dP, rel ? null : B.dP); });
  }
  function irBlock(s) {
    var v = s.ir; if (!v) return '<div class="vd-ir">法說：本站法說擷取還沒有這檔的資料。</div>';
    var src = (v.src || []).map(function (x) { return x.url ? '<a href="' + vdEsc(x.url) + '" target="_blank" rel="noopener">' + vdEsc(x.src) + "</a>" : vdEsc(x.src); }).join("、");
    var h = '<div class="vd-ir"><b>最近一次法說 ' + vdEsc(v.date) + "</b>（" + src + "）" + (v.in90 ? "" : "・超過 " + D.ir_rule.days + " 天");
    if (!v.q.length) return h + "：沒有提到產能／擴產／資本支出。</div>";
    h += "<ul>" + v.q.map(function (q) { return '<li><span class="vd-q">「' + vdEsc(q.t) + "」</span> <small>— " + vdEsc(q.sec || "") + "・" + vdEsc(q.src) + (q.ts ? " " + vdEsc(q.ts) : "") + "</small></li>"; }).join("") + "</ul>" + (v.more ? "<small>另有 " + v.more + " 句未列出</small>" : "");
    return h + "</div>";
  }
  /* 展開：個股拆解（絕對值；個股 EPS × 本益比 剛好＝股價） */
  function fillMembers(i) {
    var x = $('.vd-exp[data-x="' + i + '"]'), r = G[i]; if (!x || !r) return;
    if (!x.dataset.done) {
      var M = r.codes.map(function (c) { return [c, D.stocks[c]]; }).filter(function (m) { return m[1] && m[1].p[cur]; });
      M.sort(function (a, b) { return (a[1].p[cur].px.dPE || 0) - (b[1].p[cur].px.dPE || 0); });
      var h = '<div class="vd-mh">' + vdEsc(r.g) + " 個股拆解（絕對值，股價收盤至 " + vdMd(D.periods[cur].t1) + "；同一把尺，依本益比貢獻排序）</div>";
      h += '<div class="vd-r vd-hd"><div class="vd-lab">個股</div><div class="vd-ax vd-mx-t"></div></div>';
      M.forEach(function (m) {
        var c = m[0], s = m[1], p = s.p[cur].px;
        h += '<div class="vd-r vd-st"><div class="vd-lab">' + vdTag(p.st) + " <b>" + vdEsc(s.nm) + "</b> <small>" + c + (s.sub ? "・" + vdEsc(s.sub) : "") + "</small></div>" +
          '<div class="vd-plot" data-c="' + c + '"></div>' +
          '<div class="vd-num">股價 <b>' + vdF(p.dP) + "</b>（" + p.p0 + "→" + p.p1 + "）＝EPS " + vdF(p.dE) + "（" + vdN2(p.e0) + "→" + vdN2(p.e1) + "）× 本益比 " + vdF(p.dPE) + "（" + vdN2(p.pe0) + "→" + vdN2(p.pe1) + " 倍）" + (p.b !== D.periods[cur].t0 ? "・起點 " + vdMd(p.b) : "") + "</div>" +
          irBlock(s) + "</div>";
      });
      h += '<div class="vd-r vd-hd"><div class="vd-lab"></div><div class="vd-ax vd-mx-b"></div></div>';
      x.innerHTML = h; x.dataset.done = "1";
    }
    if (x.classList.contains("vd-open")) drawMembers(x);
  }
  function drawMembers(x) {
    var plots = x.querySelectorAll(".vd-plot"); if (!plots.length) return; var w = plots[0].clientWidth; if (!w) return;
    var vals = [];
    plots.forEach(function (pl) { var p = D.stocks[pl.dataset.c].p[cur].px; vals.push(p.dE, p.dE + p.dPE, p.dP); });
    var dom = vdDom(vals);
    vdAxis(x.querySelector(".vd-mx-t"), dom, true, w); vdAxis(x.querySelector(".vd-mx-b"), dom, true, w, "%（對數尺度）");
    plots.forEach(function (pl) { var p = D.stocks[pl.dataset.c].p[cur].px; vdBar(pl, dom, true, w, p.dE, p.dPE, p.dP, null); });
  }
  function draw() { drawMap(); showPick(); drawBars(); $$(".vd-exp.vd-open").forEach(drawMembers); }
  /* 寬度改變就重畫（SVG 用實際像素寬，字不會被拉伸） */
  var lastW = 0, tm = null;
  function onRs() { var w = root.clientWidth; if (w === lastW) return; lastW = w; clearTimeout(tm); tm = setTimeout(draw, 120); }
  if (root._vdRo) root._vdRo.disconnect();
  if (window.ResizeObserver) { root._vdRo = new ResizeObserver(onRs); root._vdRo.observe(root); }
  else window.addEventListener("resize", onRs);
  render(); lastW = root.clientWidth;
};
})();
