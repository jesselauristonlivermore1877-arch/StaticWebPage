// 預覽用：正式版 template.html 的信息流排序程式原樣抽出（gen_decay.py 產生，不手改）
/* ↓ 逐字取自 template.html 第 2365～2365 行 */
const esc = s => String(s ?? "").replace(/[&<>"]/g, m => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[m]));
/* ↓ 逐字取自 template.html 第 7234～7276 行 */
const NL_TAIL = /(?:\s*[|｜]\s*[\u4e00-\u9fffA-Za-z0-9 ]{1,8})+\s*$|(?:\s*[-－–—]\s+|\s+[-－–—]\s*)[\u4e00-\u9fff]{1,8}\s*$/;
const nlClean = t => { t = String(t || "").trim(); for (let i = 0; i < 3; i++) { const c = t.replace(NL_TAIL, "").trim(); if (c === t || c.length < 8) break; t = c; } return t; };
function nlDedup(its) {
  const n = its.length, C = its.map(x => nlClean(x.t).toLowerCase().replace(/[\s\p{P}\p{S}_]+/gu, "").slice(0, 60));
  const G = C.map(c => { const g = new Set(); for (let i = 0; i < c.length - 1; i++) g.add(c.slice(i, i + 2)); return g; });
  const T = its.map(x => Date.parse(x.pub)), NUM = its.map(x => (nlClean(x.t).match(/\d+(?:\.\d+)?/g) || []).sort().join(","));
  const par = its.map((_, i) => i), root = i => { while (par[i] !== i) i = par[i] = par[par[i]]; return i; };
  const idx = new Map();
  G.forEach((g, i) => g.forEach(b => { if (!idx.has(b)) idx.set(b, []); idx.get(b).push(i); }));
  for (let i = 0; i < n; i++) {
    const cand = new Set();
    G[i].forEach(b => { const p = idx.get(b); if (p.length <= 300) p.forEach(j => { if (j > i) cand.add(j); }); });
    cand.forEach(j => {
      const a = its[i], b = its[j], m = Math.abs(T[i] - T[j]) / 60e3;
      if (a.src === b.src) { if (C[i] === C[j] && m <= 30) par[root(j)] = root(i); return; }
      if (m > 720 || Math.min(C[i].length, C[j].length) < 10 || NUM[i] !== NUM[j]) return;
      let s = 0; G[i].forEach(x => { if (G[j].has(x)) s++; });
      if (C[i] === C[j] || 2 * s / (G[i].size + G[j].size) >= 0.85) par[root(j)] = root(i);
    });
  }
  const grp = new Map();
  for (let i = 0; i < n; i++) { const r = root(i); if (!grp.has(r)) grp.set(r, []); grp.get(r).push(i); }
  const cu = u => (/news\.google\.com/.test(u || "") ? 1e6 : 0) + String(u || "").length, out = [];
  let gone = 0;
  grp.forEach(g => {
    const rk = x => [x.l2 ? 0 : 1, String(x.seen || "9"), String(x.pub)];
    const r = g.slice().sort((p, q) => { const A = rk(its[p]), B = rk(its[q]); return A[0] - B[0] || A[1].localeCompare(B[1]) || A[2].localeCompare(B[2]); })[0];
    const R = Object.assign({}, its[r], {t: nlClean(its[r].t)}), also = new Map((R.also || []).map(a => [a.src, a.u]));
    g.forEach(i => {
      const x = its[i];
      if (i !== r) { gone++; if (x.big && !R.big) Object.assign(R, {big: x.big, bs: x.bs, bw: x.bw}); if (x.pol) R.pol = 1;
        if ((x.rk || 0) > (R.rk || 0) || (x.rg && !R.rg)) Object.assign(R, {rk: x.rk, rg: x.rg, rkw: x.rkw, rr: x.rr || R.rr}); }   // 11-01：Worker 那則沒有排序分數 → 用 Actions 同一篇的
      if (x.src === R.src) { if (cu(x.u) < cu(R.u)) R.u = x.u; }
      else if (!also.has(x.src) || cu(x.u) < cu(also.get(x.src))) also.set(x.src, x.u);
      (x.also || []).forEach(a => { if (a.src !== R.src && !also.has(a.src)) also.set(a.src, a.u); });
    });
    if (also.size) R.also = [...also].map(([src, u]) => ({src, u}));
    out.push(R);
  });
  out.sort((a, b) => String(b.pub).localeCompare(String(a.pub)));
  window._nlDup = {in: n, out: out.length, gone};      // 驗收用：這次合併掉幾則
  return out;
}
/* ↓ 逐字取自 template.html 第 7300～7300 行 */
const nlTpe = iso => { const d = new Date(iso); return isNaN(d) ? "" : new Date(d.getTime() + 8 * 3600e3).toISOString().slice(5, 16).replace("T", " "); };
/* ↓ 逐字取自 template.html 第 7385～7395 行 */
const NL_GIANT = "輝達|NVIDIA|Nvidia|亞馬遜|Amazon|微軟|Microsoft|蘋果|Apple|Google|谷歌|Alphabet|Meta|OpenAI|特斯拉|Tesla|博通|Broadcom|三星|Samsung|英特爾|Intel|SoftBank|軟銀|Berkshire|波克夏|高通|Qualcomm|超微|AMD";
const NL_HEAVY = new RegExp(`(?:${NL_GIANT})[^。；]{0,16}(?:入主|入股|認購|參與.{0,4}私募|私募|取得.{0,6}股權|公開收購|收購|併購)|(?:入主|認購私募|私募.{0,8}(?:引進|應募)).{0,16}(?:${NL_GIANT})`, "i");
// 對象要是台灣公司（重大訊息／台股代號、台股類別，或標題寫明台灣）—— 10-18 回測：只看動作字眼會把輝達收購美國新創也算進來
const nlTwTarget = x => !!(x.tw_sec || /^\d{4}$/.test(String(x.code || "")) || /台灣|臺灣|台廠|台股|台企|台系/.test((x.t || "") + (x.tz || "")));
const NL_XT = {reg: "主管機關", geo: "政治／選舉／戰爭"};
const nlXt = x => (x.xt || []).map(k => NL_XT[k] ? `<span class="nl-xt ${k}">${NL_XT[k]}</span>` : "").join("");   // 11-05 晚（A7）
function nlLevel(x) {
  if (!x.big || new Date(x.pub).getTime() < Date.now() - 24 * 3600e3) return 0;
  if (x.pol) return 2;    // 🟢 11-01 18:55（【舊】總指揮 2）：金融監理資金面措施（主管機關＋具體措施，news_layers POL_BIG）→ 重磅
  return NL_HEAVY.test((x.t || "") + " " + (x.tz || "")) && nlTwTarget(x) ? 2 : 1;
}
/* ↓ 逐字取自 template.html 第 7429～7444 行 */
function nlEvents(F) {
  const by = new Map(), out = [];
  F.forEach(x => { if (!x.rg) { out.push(x); return; } if (!by.has(x.rg)) by.set(x.rg, []); by.get(x.rg).push(x); });
  by.forEach(g => {
    const r = g.find(x => x.rr) || g[0], R = Object.assign({}, r), also = new Map((r.also || []).map(a => [a.src, a.u]));
    g.forEach(x => { if (x === r) return;
      if (x.src !== R.src && !also.has(x.src)) also.set(x.src, x.u);
      (x.also || []).forEach(a => { if (a.src !== R.src && !also.has(a.src)) also.set(a.src, a.u); });
      if (x.big && !R.big) Object.assign(R, {big: x.big, bs: x.bs, bw: x.bw}); });
    if (also.size) R.also = [...also].map(([src, u]) => ({src, u}));
    R._n = g.length; out.push(R);
  });
  return out;
}
// 「市場會追」：只有「重磅」（前所未聞）置頂，其餘照事件分數 → 重點分數 → 時間（「重點」不再壓過分數更高的事件）
const nlRankCmp = (a, b) => (nlLevel(b) === 2) - (nlLevel(a) === 2) || (b.rk || 0) - (a.rk || 0) || (b.bs || 0) - (a.bs || 0) || String(b.pub).localeCompare(String(a.pub));
