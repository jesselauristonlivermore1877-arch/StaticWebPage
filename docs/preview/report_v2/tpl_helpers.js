/* 從 template.html 原樣複製（esc、el、crFactText、crChart、CR_LIB、crScript），只給預覽頁用；套版時不用搬 */
const esc = s => String(s ?? "").replace(/[&<>"]/g, m => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[m]));
const el = (t, c, h, s) => { const e = document.createElement(t); if (c) e.className = c; if (h !== undefined) e.innerHTML = h; if (s) e.style.cssText = s; return e; };
function crFactText(F, id) { const f = F[id]; return f ? f.text : "—"; }
function crMd(t) { return esc(t || "").replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>"); }
function crChart(R, F) {
  const P = (R.chart || {}).rev_eps || [];
  if (P.length < 2) return null;
  const W = 640, H = 220, L = 46, Rr = 46, T = 14, B = 40, n = P.length, bw = (W - L - Rr) / n;
  const rv = P.map(p => (F[p.rev_id] || {}).value), ev = P.map(p => (F[p.eps_id] || {}).value);
  const rmax = Math.max(...rv.filter(v => v != null), 1), emin = Math.min(0, ...ev.filter(v => v != null)), emax = Math.max(...ev.filter(v => v != null), 1);
  const yR = v => T + (H - T - B) * (1 - v / rmax), yE = v => T + (H - T - B) * (1 - (v - emin) / (emax - emin || 1));
  let g = `<svg viewBox="0 0 ${W} ${H}" class="cr-svg" role="img" aria-label="營收與 EPS">`;
  P.forEach((p, i) => { const x = L + i * bw + bw * 0.18, v = rv[i]; if (v != null) g += `<rect x="${x}" y="${yR(v)}" width="${bw * 0.64}" height="${H - B - yR(v)}" class="cr-bar"><title>${esc(p.period)} 營收 ${esc(crFactText(F, p.rev_id))}</title></rect>`;
    g += `<text x="${L + i * bw + bw / 2}" y="${H - B + 16}" class="cr-ax" text-anchor="middle">${esc(p.period)}</text>`; });
  const pts = P.map((p, i) => ev[i] == null ? null : [L + i * bw + bw / 2, yE(ev[i])]).filter(Boolean);
  if (pts.length > 1) g += `<polyline points="${pts.map(q => q.join(",")).join(" ")}" class="cr-line"/>`;
  P.forEach((p, i) => { if (ev[i] != null) g += `<circle cx="${L + i * bw + bw / 2}" cy="${yE(ev[i])}" r="4" class="cr-dot"><title>${esc(p.period)} EPS ${esc(crFactText(F, p.eps_id))}</title></circle>`; });
  ((R.chart || {}).milestones || []).forEach(m => { const i = P.findIndex(p => p.period === m.period); if (i >= 0)
    g += `<text x="${L + i * bw + bw / 2}" y="${H - 6}" class="cr-ms" text-anchor="middle">▲ ${esc(m.text)}</text>`; });
  g += `<text x="4" y="${T + 4}" class="cr-ax">營收（億元）</text><text x="${W - 4}" y="${T + 4}" class="cr-ax" text-anchor="end">EPS（元）</text></svg>`;
  return el("div", "cr-chart", g);
}
const CR_LIB = {h2c: "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js", pdf: "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"};
function crScript(u) { return new Promise((ok, no) => { if (document.querySelector(`script[src="${u}"]`)) return ok(); const t = document.createElement("script"); t.src = u; t.onload = ok; t.onerror = no; document.head.appendChild(t); }); }
