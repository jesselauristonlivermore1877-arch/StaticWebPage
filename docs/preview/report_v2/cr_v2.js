/* AI 研究報告下載版 v2（C4，雲端 10-29 接手 Codex）＋EDM 圖卡（新）
   核准後整段搬進 template.html，取代 crExport／crTwoCol；資料、擷取、核對（company_report.py、company_verify.py）都不動。
   ── 報告版（A4 PDF）──
   舊版：整份排成一張長圖 → 固定 A4 高度硬切 → 表格、圖片、文字被攔腰切斷。
   新版：先排成一頁一頁的 A4（794×1123px），區塊逐一放進頁面、放不下就換頁：
     圖表與小表整塊不拆；長文字在段落／列點之間換頁（小標跟著第一段走，續頁標「（續）」）；
     長表格在列與列之間換頁、續頁重複表頭；太寬的表先縮字、還不夠再整張等比縮小。
     第一頁＝重點摘要 3～5 點（取自已核對的「總結」，不足 3 點補「影響」的小標）＋估值位階區塊（規則不放評等）；
     前言（事件、公司簡介）超過 CR_INTRO_MAX 字 → 第一頁只放開頭幾句，全文收進附錄。
     每頁頁首、頁尾、頁碼；浮水印照舊畫進像素（每頁各畫一次）。
   ── EDM 版（1080×1350 PNG）──
   參考 _inbox/ref_藏鋒 的單頁圖卡架構：大標＋副標、四格關鍵數字、營收與 EPS 圖、重點、後續追蹤、風險一行、總結一行。
   文字全部取自報告已核對的內容，只截短、不改寫；放不下就整張縮字。 */
const CR_INTRO_MAX = 260;
const CR_A4 = {w: 794, h: 1123, pad: 40, head: 34, foot: 30};
function crToday() { return new Date().toISOString().slice(0, 10); }
/* 章節文字 → HTML 區塊陣列（每段、每個列點各一個元素，換頁只能在它們之間） */
function crItems(t) {
  const out = [], ib = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  String(t || "").split(/\n+/).map(s => s.trim()).filter(Boolean).forEach(s => {
    // 「1. … 2. … 3. …」寫在同一行的拆開
    const parts = /^\d+[.、]\s/.test(s) ? s.split(/\s(?=\d+[.、]\s)/) : [s];
    parts.forEach(p => {
      const m = p.match(/^(?:[-•]\s+|(\d+)[.、]\s+)(.*)$/);
      out.push(m ? `<div class="crp-li">${m[1] ? `<i>${m[1]}</i>` : "<i>•</i>"}<span>${ib(m[2])}</span></div>` : `<p>${ib(p)}</p>`);
    });
  });
  return out;
}
/* 前言截短：在句號／分號處截，最多 n 字 */
function crCut(t, n) {
  const s = String(t || "").replace(/\s+/g, " ").trim();
  if (s.length <= n) return [s, false];
  const cut = s.slice(0, n), k = Math.max(cut.lastIndexOf("。"), cut.lastIndexOf("；"));
  return [k > n * 0.4 ? cut.slice(0, k + 1) : cut + "…", true];
}
function crPlain(t) { return String(t || "").replace(/\*\*/g, "").replace(/^\s*(?:[-•]|\d+[.、])\s*/, "").trim(); }
/* 重點摘要 3～5 點：總結的每個環節（→ 分隔）；不足 3 點補「影響」各列點的粗體小標 */
function crKeyPoints(R) {
  const S = R.sections || {};
  const pts = String(S["總結"] || "").split(/→/).map(s => s.trim()).filter(Boolean);
  if (pts.length < 3) (String(S["影響"] || "").match(/\*\*(.+?)\*\*/g) || []).forEach(b => { if (pts.length < 3) pts.push(b.replace(/\*\*|：|:$/g, "")); });
  return pts.slice(0, 5);
}
function crFactsBy(R, sec) { return (R.facts || []).filter(f => f.sec === sec); }
function crFind(R, re) { return (R.facts || []).find(f => re.test(f.label || "")); }
/* 表格（季度表＝列是季度；其他表照原樣）→ {title, head:[], rows:[[...]], note} */
function crTables(R, F) {
  const out = [], Q = (R.tables || {}).quarters;
  if (Q && (Q.cols || []).length) out.push({title: (Q.title || "季度表").replace(/（.*$/, ""), head: ["季度", ...(Q.rows || []).map(r => r.label.replace(/（億元）|（元）/, ""))],
    rows: Q.cols.map((c, j) => [c, ...(Q.rows || []).map(r => { const id = (r.cells || [])[j]; return id ? crFactText(F, id) : "—"; })]).reverse(),
    note: (Q.title || "") + "；金額單位億元、EPS 單位元"});
  Object.entries(R.tables || {}).filter(([k]) => k !== "quarters").forEach(([, T]) => {
    const seen = new Set(), rows = [];
    (T.rows || []).forEach(r => { const v = [r.label, ...(r.cells || []).map(id => id ? crFactText(F, id) : "—")], key = v.join("|");
      if (!seen.has(key)) { seen.add(key); rows.push(v); } });   // 同一列（名稱＋數字都一樣）重複出現只留一列
    out.push({title: T.title || "", head: ["項目", ...(T.cols || [])], rows});
  });
  return out;
}
function crTblHtml(T, rows, cont) {
  return `<div class="crp-cap">${esc(T.title)}${cont ? "（續）" : ""}</div><table><thead><tr>${T.head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr>${r.map((c, i) => `<td${i ? ' class="num"' : ""}>${esc(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
}
/* ── 報告版：排頁 ── */
function crPages(R, mount) {
  const F = {}; (R.facts || []).forEach(f => { F[f.id] = f; });
  const S = R.sections || {}, dd = R.data_date || R.date || "", pages = [];
  const book = el("div", "crp-book"); mount.appendChild(book);   // 先掛上文件，排的時候才量得到高度
  let body = null;
  const newPage = () => {
    const pg = el("div", "crp-page");
    pg.appendChild(el("div", "crp-head", `<span>GEA 戰情・AI 研究報告</span><span>${esc(R.code)} ${esc(R.name || "")}｜資料日 ${esc(dd)}</span>`));
    body = el("div", "crp-body"); pg.appendChild(body);
    pg.appendChild(el("div", "crp-foot", `<span>僅供參考，不構成投資建議｜下載 ${crToday()}</span><span class="crp-pno"></span>`));
    book.appendChild(pg); pages.push(pg);
  };
  const over = () => body.scrollHeight > body.clientHeight + 1;
  // 整塊放（不拆）；目前頁放不下就換頁；整頁都放不下就等比縮小
  const atom = node => {
    body.appendChild(node); if (!over()) return;
    if (body.children.length > 1) { body.removeChild(node); newPage(); body.appendChild(node); }
    if (over()) { const k = body.clientHeight / node.offsetHeight * 0.98; node.style.transform = `scale(${k})`; node.style.transformOrigin = "top left"; node.style.marginBottom = `-${node.offsetHeight * (1 - k)}px`; }
  };
  // 文字章節：段落／列點之間可以換頁；小標不落單
  const text = (title, items, cls) => {
    if (!items.length) return;
    const mk = cont => { const s = el("div", "crp-sec " + (cls || "")); s.appendChild(el("h4", "", esc(title) + (cont ? "（續）" : ""))); body.appendChild(s); return s; };
    let s = mk(false), n = 0;
    items.forEach(h => {
      const it = el("div", "crp-it", h); s.appendChild(it);
      if (!over()) { n++; return; }
      s.removeChild(it);
      if (!n) { body.removeChild(s); newPage(); s = mk(false); }
      else { newPage(); s = mk(true); }
      s.appendChild(it); n = 1;
    });
  };
  // 表格：列與列之間換頁、續頁重複表頭；太寬先縮字、再整張縮小
  const table = T => {
    const fit = w => {
      const tb = w.querySelector("table"); let fs = 11;
      tb.style.fontSize = fs + "px";
      while (tb.scrollWidth > w.clientWidth + 1 && fs > 8.5) { fs -= 0.5; tb.style.fontSize = fs + "px"; }
      if (tb.scrollWidth > w.clientWidth + 1) { const k = w.clientWidth / tb.scrollWidth; tb.style.transform = `scale(${k})`; tb.style.transformOrigin = "top left"; w.style.height = tb.offsetHeight * k + w.querySelector(".crp-cap").offsetHeight + "px"; }
    };
    let start = 0, cont = false;
    while (start < T.rows.length) {
      const w = el("div", "crp-tbl"); body.appendChild(w);
      let n = T.rows.length - start;
      w.innerHTML = crTblHtml(T, T.rows.slice(start, start + n), cont); fit(w);
      while (over() && n > 1) { n--; w.innerHTML = crTblHtml(T, T.rows.slice(start, start + n), cont); fit(w); }
      if (over() || (n < Math.min(3, T.rows.length - start) && body.children.length > 1)) {   // 一列都放不下、或只放得下零星幾列 → 整張移到下一頁
        body.removeChild(w); newPage(); continue;
      }
      start += n; cont = true;
      if (start >= T.rows.length && T.note) w.appendChild(el("div", "crp-tnote", esc(T.note)));
      if (start < T.rows.length) newPage();
    }
  };
  // 第一頁：標題、重點摘要＋估值位階、關鍵數字、總結、圖、前言
  newPage();
  atom(el("div", "crp-hero", `<div class="crp-ind"><span>${esc(R.industry || "")}</span>資料日 ${esc(dd)}${R.made_date ? "｜報告產出日 " + esc(R.made_date) : ""}</div>` +
    `<div class="crp-code"><b>${esc(R.code)}</b> ${esc(R.name || "")}</div><div class="crp-title">${esc(S["標題"] || "")}</div><div class="crp-subt">${esc(S["副標"] || "")}</div>`));
  const kp = crKeyPoints(R), val = crFactsBy(R, "估值").filter(f => /本益比|淨值比|ROE|殖利率/.test(f.label));
  atom(el("div", "crp-top", `<div class="crp-kp"><h4>重點摘要</h4>${kp.map((p, i) => `<div class="crp-li"><i>${i + 1}</i><span>${esc(p)}</span></div>`).join("")}</div>` +
    `<div class="crp-rate"><h4>估值位階</h4>${val.map(f => `<div><span>${esc(f.label.replace(/（.*$/, ""))}</span><b class="num">${esc(f.text)}</b></div>`).join("") || "<div>—</div>"}` +
    `<small>本站依規則不提供評等、目標價與潛在漲幅；位階請看網站「河流圖」。</small></div>`));
  const kpi = crFactsBy(R, "關鍵數據").slice(0, 4);
  if (kpi.length) atom(el("div", "crp-kpi", kpi.map(f => `<div><small>${esc(f.label)}</small><b class="num">${esc(f.text)}</b><small>${esc(f.period || "")}</small></div>`).join("")));
  // 重點摘要就是「總結」各環節；只有補了「影響」小標時（總結不足 3 環節）才另放總結一行
  if (S["總結"] && String(S["總結"]).split("→").length < 3) atom(el("div", "crp-flow", `<span>總結</span> ${esc(S["總結"]).replace(/→/g, "<i>→</i>")}`));
  const ch = crChart(R, F); if (ch) { const c = el("div", "crp-chart"); c.appendChild(el("h4", "", "營收與 EPS")); c.appendChild(ch); atom(c); }
  const appx = [];
  const [ev, evCut] = crCut(S["事件"], CR_INTRO_MAX);
  if (S["事件"]) text("事件", evCut ? [`<p>${esc(ev)}<span class="crp-see">（全文見附錄 A）</span></p>`] : crItems(S["事件"]));
  if (evCut) appx.push(["附錄 A　事件（全文）", S["事件"]]);
  // 內文
  text("影響", crItems(S["影響"]));
  text("預估與估值依據", crItems(S["預估與估值依據"]));
  text("後續追蹤", crItems(S["後續追蹤"]));
  text("風險", crItems(S["風險"]));
  crTables(R, F).forEach(table);
  if (S["公司簡介"]) { const [, c] = crCut(S["公司簡介"], CR_INTRO_MAX);
    if (c) appx.push([`附錄 ${appx.length ? "B" : "A"}　公司簡介`, S["公司簡介"]]); else text("公司簡介", crItems(S["公司簡介"])); }
  appx.forEach(([t, s]) => text(t, crItems(s), "crp-appx"));
  const srcs = [...new Set((R.facts || []).map(f => f.src).filter(u => /^https?:/.test(u || "")))];
  atom(el("div", "crp-note", `數字 ${(R.facts || []).length} 筆全部由程式取自公開資訊觀測站、月營收、法說簡報與站上資料，逐筆核對；文字由 AI 撰寫初稿。` +
    `不含評等、目標價與潛在漲幅；估值只用河流圖位階。官方出處：${srcs.slice(0, 6).map(u => esc(u)).join("　") || "—"}`));
  pages.forEach((p, i) => { p.querySelector(".crp-pno").textContent = `第 ${i + 1}／${pages.length} 頁`; });
  return {book, pages};
}
function crWatermark(cv, R, step) {
  const g = cv.getContext("2d"), wm = `GEA 戰情 ・ ${R.code} ${R.name || ""} ・ ${crToday()}`;
  g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = .13; g.fillStyle = "#7a7468"; g.font = "bold 30px sans-serif"; g.rotate(-Math.PI / 7);
  for (let y = -cv.width; y < cv.height + cv.width; y += step || 210) for (let x = -cv.width; x < cv.width * 2; x += 520) g.fillText(wm, x, y);
  g.restore();
}
function crHost(w) { const h = el("div", "cr-print"); h.style.cssText = `position:fixed;left:-10000px;top:0;width:${w}px;background:#fff`; document.body.appendChild(h); return h; }
/* 產生 PDF（回傳 jsPDF 物件與頁數；網站上直接 save，預覽產生器拿 blob） */
async function crReportPdf(R) {
  await crScript(CR_LIB.h2c); await crScript(CR_LIB.pdf);
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  const host = crHost(CR_A4.w), {pages} = crPages(R, host);
  const doc = new window.jspdf.jsPDF({unit: "mm", format: "a4", compress: true});
  for (let i = 0; i < pages.length; i++) {
    const cv = await window.html2canvas(pages[i], {scale: 2, backgroundColor: "#ffffff", useCORS: true, logging: false});
    crWatermark(cv, R);
    if (i) doc.addPage("a4");
    doc.addImage(cv.toDataURL("image/jpeg", .9), "JPEG", 0, 0, 210, 297);
  }
  host.remove();
  return {doc, pages: pages.length};
}
/* ── EDM 圖卡：1080×1350（IG／LINE 直式分享尺寸） ── */
function crShort(t, n) { const s = crPlain(t).replace(/\s+/g, " "); if (s.length <= n) return s;
  const c = s.slice(0, n), k = Math.max(c.lastIndexOf("，"), c.lastIndexOf("；"), c.lastIndexOf("。"));
  return (k > n * 0.5 ? c.slice(0, k) : c) + "…"; }
function crEdmKpis(R) {
  const pick = [crFind(R, /^\d{4}-\d{2} 月營收$/), crFind(R, /累計營收$/), crFind(R, /累計 EPS$/), crFind(R, /^本益比/)].filter(Boolean);
  const yoy = crFind(R, /累計營收年增$/);
  return pick.map(f => ({lab: f.label.replace(/（.*$/, "").replace(/^\d{4}-(\d{2}) 月營收$/, (a, m) => +m + " 月營收").replace(/^\d{4} 年\s*/, "").replace(/^本益比$/, "本益比（近四季）"),
    num: f.text, sub: /累計營收$/.test(f.label) && yoy ? "年增 " + yoy.text : (f.period || "")}));
}
function crEdm(R, mount) {
  const F = {}; (R.facts || []).forEach(f => { F[f.id] = f; });
  const S = R.sections || {}, dd = R.data_date || R.date || "";
  const all = crKeyPoints(R), kp = all.slice(0, 3), nx = all.slice(3).join("；");   // 重點＝總結前 3 環節；第 4 環節起放最下面「下一步」
  const trk = crItems(S["後續追蹤"]).map(h => h.replace(/<[^>]+>/g, "")).map(t => t.replace(/^\d+/, "").replace(/^[一二三四五六七八九十]+、\s*/, "").trim()).filter(Boolean).slice(0, 3);
  let risk = ((S["風險"] || "").match(/\*\*(.+?)\*\*/g) || []).map(b => b.replace(/\*\*|：|:/g, "").replace(/風險$/, ""));
  if (!risk.length) risk = crItems(S["風險"]).map(h => crPlain(h.replace(/<[^>]+>/g, "").replace(/^[\d•]+/, "")).split(/[，。；：:]/)[0]).filter(t => t && t.length <= 24);
  risk = risk.slice(0, 4);
  const ch = crChart(R, F);
  const c = el("div", "cre-card");
  c.innerHTML = `<div class="cre-top"><div class="cre-tag">企業近況摘要｜${esc(R.industry || "")}</div><div class="cre-brand">GEA 戰情<small>AI 研究報告</small></div>` +
    `<div class="cre-name">${esc(R.name || "")}<span>(${esc(R.code)})</span></div><div class="cre-title">${esc(String(S["標題"] || "").replace(/[。．]$/, ""))}</div><div class="cre-subt">${esc(S["副標"] || "")}</div></div>` +
    `<div class="cre-kpi">${crEdmKpis(R).map(k => { const m = String(k.num).match(/^([+\-−]?[\d.,]+%?)\s*(.*)$/) || [0, k.num, ""];
      return `<div><small>${esc(k.lab)}</small><b>${esc(m[1])}<u>${esc(m[2])}</u></b><em>${esc(k.sub)}</em></div>`; }).join("")}</div>` +
    `<div class="cre-mid"><div class="cre-box cre-chart"><h4>營收與 EPS</h4></div><div class="cre-box"><h4>重點</h4>${kp.map((p, i) => `<div class="cre-li"><i>${i + 1}</i><span>${esc(crShort(p, 46))}</span></div>`).join("")}</div></div>` +
    (trk.length ? `<div class="cre-box cre-trk"><h4>後續追蹤</h4><div>${trk.map((t, i) => `<div class="cre-li"><i>${i + 1}</i><span>${esc(crShort(t, 58))}</span></div>`).join("")}</div></div>` : "") +
    (risk.length ? `<div class="cre-risk"><b>⚠ 風險提醒</b>${esc(risk.join("、"))}</div>` : "") +
    (nx ? `<div class="cre-flow"><b>下一步</b>${esc(crShort(nx, 60))}</div>` : "") +
    `<div class="cre-foot">資料日 ${esc(dd)}｜數字由程式取自公開資訊觀測站、月營收、法說簡報與站上資料，逐筆核對；文字由 AI 撰寫初稿。不含評等、目標價；僅供參考，不構成投資建議。</div>`;
  if (ch) c.querySelector(".cre-chart").appendChild(ch);
  mount.appendChild(c);
  // 放不下就整張縮字（最多縮到 0.8 倍）
  for (let k = 1; c.scrollHeight > 1350 && k > 0.8; k -= 0.02) c.style.setProperty("--k", k.toFixed(2));
  return c;
}
async function crEdmPng(R) {
  await crScript(CR_LIB.h2c);
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  const host = crHost(1080), c = crEdm(R, host);
  const cv = await window.html2canvas(c, {scale: 1, width: 1080, height: 1350, backgroundColor: "#ffffff", useCORS: true, logging: false});
  crWatermark(cv, R, 260);
  host.remove();
  return cv;
}
/* 網站按鈕用（取代 crExport） */
async function crExport2(R, kind, btn) {
  const t0 = btn.textContent; btn.textContent = "產生中…"; btn.disabled = true;
  const fn = `GEA_${R.code}_${R.name || ""}_${R.data_date || R.date || ""}`;
  try {
    if (kind === "pdf") { const {doc} = await crReportPdf(R); doc.save(fn + ".pdf"); }
    else { const cv = await crEdmPng(R), blob = await new Promise(ok => cv.toBlob(ok, "image/png")), a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = fn + "_EDM.png"; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000); }
  } catch (e) { alert("下載失敗：" + (e && e.message || e)); }
  btn.textContent = t0; btn.disabled = false;
}
