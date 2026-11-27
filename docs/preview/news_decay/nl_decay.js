// 提案程式：Evans 點頭後，原樣貼進 template.html 的 nlRankCmp 後面，並把兩處 nlEvents(F).sort(nlRankCmp) 改成 nlEvents(F).sort(nlRankCmpT())
/* 🟢 11-27（Evans：「市場會追的程度」每次點都有舊的跑上來 → 方案 1 加時間衰減）
   有效分數＝rk × NL_DECAY_K ^ (距今小時 ÷ NL_DECAY_H)；預設每 6 小時 ×0.8（約 18.6 小時減半、48 小時剩 17%）。
   距今＝事件代表那則的發布時間（列表上顯示的那個時間）；重磅仍置頂；「最新」排法不動。
   at：取時間的函式（預覽用來比較「事件內最新一則」），正式版不給＝代表那則的 pub。 */
const NL_DECAY_K = 0.8, NL_DECAY_H = 6;
const nlAgeH = (iso, now) => Math.max(0, (now - Date.parse(iso)) / 3600e3) || 0;
const nlDecay = (iso, now) => Math.pow(NL_DECAY_K, nlAgeH(iso, now) / NL_DECAY_H);
function nlRankCmpT(at) {
  const now = Date.now(), get = at || (x => x.pub);
  const C = new WeakMap();          // 每次排序只算一次（排序途中時間不變），結果也寫回 _age／_dk／_eff 給畫面用
  const E = x => { let v = C.get(x); if (v == null) { const t = get(x); x._age = nlAgeH(t, now); x._dk = nlDecay(t, now); x._eff = v = (x.rk || 0) * x._dk; C.set(x, v); } return v; };
  return (a, b) => (nlLevel(b) === 2) - (nlLevel(a) === 2) || E(b) - E(a) || (b.bs || 0) - (a.bs || 0) || String(b.pub).localeCompare(String(a.pub));
}
// 顯示：「市場關注 X 分（時間調整後 Y）」，滑過看分數明細＋衰減係數（取代 nlItem 裡那一段）
const nlRkLab = x => x.rk ? `<span title="${esc((x.rkw || "") + (x._dk != null ? `｜距今 ${x._age.toFixed(1)} 小時 × 衰減係數 ${x._dk.toFixed(2)}（每 ${NL_DECAY_H} 小時 ×${NL_DECAY_K}）` : ""))}">市場關注 ${x.rk} 分` +
  (x._dk != null ? `（時間調整後 ${x._eff.toFixed(1)}）` : "") + `${x._n > 1 ? `・同一事件 ${x._n} 則` : ""}</span>` : "";
const NL_RANK_NOTE = `同一事件合成一則（其他媒體列在「另見」），分數＝跨媒體同報＋主軸詞＋權值股＋價格反應，再依發布時間打折（每 ${NL_DECAY_H} 小時 ×${NL_DECAY_K}，約 19 小時減半）；重磅置頂；滑過「市場關注」看明細`;
