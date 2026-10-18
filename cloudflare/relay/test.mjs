// test.mjs ── gea-signal-relay 自動測試（Evans 2026-10-11 15:50 派工第 2 項）
//   1 個發送端＋3 個接收端：正常廣播、接收端斷線後補發、錯誤 token 被拒、停權用戶被拒（含在線被踢）、格式錯誤被拒、
//   重送不重播、接收端不能發、心跳自動回應、/health；印每則延遲（同一台機器量：發送 → 3 個接收端都收到）。
//   用法：BASE=https://… RELAY_PUB_TOKEN=… RELAY_ADMIN_TOKEN=… node test.mjs   （需要 npm 套件 ws）
//   每次用新頻道 t<時間>，測完 /admin/purge 刪掉。任何一項沒過 → exit 1。
import WebSocket from "ws";

const BASE = process.env.BASE.replace(/\/$/, "");
const WSB = BASE.replace(/^http/, "ws");
const PUB = process.env.RELAY_PUB_TOKEN, ADMIN = process.env.RELAY_ADMIN_TOKEN;
const CH = "t" + Date.now();
const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0;
const ok = (cond, what, extra = "") => { console.log((cond ? "  ✓ " : "  ✗ ") + what + (extra ? "｜" + extra : "")); if (!cond) fails++; };

async function admin(path, method = "POST") {
  const r = await fetch(`${BASE}/admin/${path}${path.includes("?") ? "&" : "?"}ch=${CH}`, { method, headers: { Authorization: "Bearer " + ADMIN } });
  return { status: r.status, j: await r.json().catch(() => ({})) };
}

// 開連線；回 {ws, got[], ctl[], closed}；握手失敗回 {err: HTTP 狀態}
function connect(role, id, token) {
  return new Promise(res => {
    const c = { got: [], ctl: [], pong: 0, closed: null, t: [] };
    const ws = new WebSocket(`${WSB}/ws?ch=${CH}&role=${role}&id=${id}`, { headers: { Authorization: "Bearer " + token } });
    c.ws = ws;
    ws.on("unexpected-response", (req, r) => res({ err: r.statusCode }));
    ws.on("error", e => res({ err: String(e.message || e) }));
    ws.on("open", () => res(c));
    ws.on("close", (code, reason) => { c.closed = [code, String(reason)]; });
    ws.on("message", d => {
      const s = String(d);
      if (s === "pong") { c.pong++; return; }
      const m = JSON.parse(s);
      if (m.ctl) c.ctl.push(m); else { c.got.push(m); c.t.push(performance.now()); }
    });
  });
}

const sig = (seq, extra = {}) => JSON.stringify({ Seq: seq, TsMs: Date.now(), Strategy: "TEST", Symbol: "TXF", Month: "", Side: "B",
  Qty: 1, Effect: "O", PriceType: "MKT", Price: 0, Sig: "f".repeat(64), ...extra });
// 被中繼關閉：收到關閉框就算（本機 wrangler dev 會停在 CLOSING、不觸發 close 事件；ws 8 收到關閉框會記 _closeCode）
const kickedCode = c => c.closed ? c.closed[0] : (c.ws._closeFrameReceived ? c.ws._closeCode : null);
const until = async (fn, ms = 5000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(20); } return fn(); };

console.log("頻道", CH, "｜", BASE);
// ── 建用戶
const tok = {};
for (const u of ["u1", "u2", "u3", "u4"]) {
  const r = await admin("user?id=" + u + "&subs=*");                     // 這批用戶訂閱「全部」（舊測試照舊）；訂閱控管在後面另測
  tok[u] = r.j.token;
  ok(r.status === 200 && /^[0-9a-f]{48}$/.test(r.j.token || ""), `新增用戶 ${u}`);
}
ok((await admin("user?id=x")).status === 200, "（多建一個 x 供重發測試）");
ok((await fetch(`${BASE}/admin/users?ch=${CH}`, { headers: { Authorization: "Bearer wrong" } })).status === 401, "管理端點錯 token → 401");

// ── 拒絕
let r = await connect("sub", "u1", "deadbeef");
ok(r.err === 401, "錯誤 token 被拒", "HTTP " + r.err);
r = await connect("pub", "sender", "deadbeef");
ok(r.err === 401, "發送端錯誤 token 被拒", "HTTP " + r.err);
r = await connect("sub", "nobody", tok.u1);
ok(r.err === 401, "不存在的用戶被拒", "HTTP " + r.err);
await admin("disable?id=u4");
r = await connect("sub", "u4", tok.u4);
ok(r.err === 403, "停權用戶被拒", "HTTP " + r.err);

// ── 正常廣播
const subs = {};
for (const u of ["u1", "u2", "u3"]) { subs[u] = await connect("sub", u, tok[u]); ok(!subs[u].err, `接收端 ${u} 連上`); }
const pub = await connect("pub", "sender", PUB);
ok(!pub.err, "發送端連上");
const lat = [];
for (let i = 1; i <= 10; i++) {
  const t0 = performance.now();
  pub.ws.send(sig(i));
  await until(() => ["u1", "u2", "u3"].every(u => subs[u].got.length >= i));
  lat.push(Math.max(...["u1", "u2", "u3"].map(u => subs[u].t[i - 1])) - t0);
  await sleep(100);
}
await until(() => pub.ctl.filter(c => c.ctl === "ack").length >= 10);
for (const u of ["u1", "u2", "u3"]) ok(subs[u].got.map(m => m.Seq).join() === "1,2,3,4,5,6,7,8,9,10", `${u} 收到 1～10 依序`, subs[u].got.map(m => m.Seq).join());
ok(pub.ctl.filter(c => c.ctl === "ack").length === 10 && pub.ctl.every(c => c.subs === 3), "發送端每則收到 ack（subs=3）");
lat.sort((a, b) => a - b);
console.log("  延遲（發送 → 3 個接收端都收到，ms）：最小 %s、中位 %s、最大 %s", lat[0].toFixed(1), lat[5].toFixed(1), lat[9].toFixed(1));

// ── 格式錯誤、重送、接收端發訊號
const nCtl = pub.ctl.length;
pub.ws.send("not json");
pub.ws.send(JSON.stringify({ Seq: "x", TsMs: 1, Sig: "a" }));
pub.ws.send(JSON.stringify({ Seq: 11, TsMs: 1 }));
pub.ws.send(JSON.stringify([1, 2]));
pub.ws.send(sig(5));                                      // 重送
await until(() => pub.ctl.length >= nCtl + 5);
const errs = pub.ctl.slice(nCtl);
ok(errs.slice(0, 4).every(c => c.ctl === "err"), "格式錯誤被拒（4 種）", errs.slice(0, 4).map(c => c.why).join("；"));
ok(errs[4] && errs[4].ctl === "dup", "重送 Seq 5 回 dup、不廣播");
subs.u1.ws.send(sig(99));
await until(() => subs.u1.ctl.length >= 1);
ok(subs.u1.ctl[0] && subs.u1.ctl[0].ctl === "err", "接收端不能發訊號", subs.u1.ctl[0] && subs.u1.ctl[0].why);
await sleep(300);
ok(["u1", "u2", "u3"].every(u => subs[u].got.length === 10), "以上都沒有多廣播任何一則");

// ── 心跳
subs.u2.ws.send("ping"); pub.ws.send("ping");
await until(() => subs.u2.pong >= 1 && pub.pong >= 1);
ok(subs.u2.pong === 1 && pub.pong === 1, "ping → pong 自動回應（兩端）");

// ── 斷線補發
subs.u3.ws.close();
await sleep(300);
for (let i = 11; i <= 15; i++) { pub.ws.send(sig(i)); await sleep(50); }
await until(() => subs.u1.got.length >= 15);
const u3b = await connect("sub", "u3", tok.u3);
u3b.ws.send(JSON.stringify({ since: 10 }));
await until(() => u3b.ctl.some(c => c.ctl === "replayed"));
ok(u3b.got.map(m => m.Seq).join() === "11,12,13,14,15", "u3 斷線期間 11～15，重連 since=10 補發", u3b.got.map(m => m.Seq).join());
const rp = u3b.ctl.find(c => c.ctl === "replayed") || {};
ok(rp.n === 5 && rp.last === 15 && rp.gap === null, "補發結尾 replayed n=5 last=15", JSON.stringify(rp));
const raw = u3b.got[0] && JSON.stringify(u3b.got[0]);
ok(raw && JSON.parse(sig(11)).Sig === u3b.got[0].Sig && u3b.got[0].Strategy === "TEST", "補發內容原文不變");

// ── 在線停權
await admin("disable?id=u2");
await until(() => kickedCode(subs.u2));
ok(kickedCode(subs.u2) === 4003, "在線用戶停權 → 立刻以 4003 關閉", String(kickedCode(subs.u2)));
await admin("enable?id=u2");
r = await connect("sub", "u2", tok.u2);
ok(!r.err, "復權後可再連"); if (!r.err) r.ws.close();

// ── /health
const h = await (await fetch(`${BASE}/health?ch=${CH}`)).json();
ok(h.last_seq === 15 && h.subs_online === 2 && h.signals_1h === 15, "/health", JSON.stringify(h));
const us = await admin("users", "GET");
ok((us.j.users || []).length === 5, "/admin/users 列 5 個用戶", (us.j.users || []).map(u => u.id + (u.enabled ? "" : "(停)")).join(","));

// ── 只留最近 500 則；要補的太舊 → replayed.gap 標出缺段
for (let i = 16; i <= 520; i++) pub.ws.send(sig(i));
await until(() => pub.ctl.filter(c => c.ctl === "ack" && c.seq === 520).length === 1, 20000);
tok.r1 = (await admin("user?id=r1&subs=*")).j.token;               // 另開代號：同代號再連會把 u1 踢掉（4009，同代號只留一條）
const old = await connect("sub", "r1", tok.r1);
old.ws.send(JSON.stringify({ since: 0 }));
await until(() => old.ctl.some(c => c.ctl === "replayed"), 20000);
const rq = old.ctl.find(c => c.ctl === "replayed") || {};
ok(old.got.length === 500 && old.got[0].Seq === 21 && rq.last === 520 && JSON.stringify(rq.gap) === "[1,20]", "只留 500 則（21～520），since=0 回報缺段 1～20", `${old.got.length} 則、${JSON.stringify(rq)}`);
old.ws.close();

// ── 訂閱控管（10-18 20:40 派工第 1 項）：只轉送訂閱且上架的策略；補發照同一規則；到期踢線；模擬端點；管理頁
const post = async (path, body) => { const r = await fetch(`${BASE}/admin/${path}${path.includes("?") ? "&" : "?"}ch=${CH}`, { method: "POST",
  headers: { Authorization: "Bearer " + ADMIN, "content-type": "application/json" }, body: JSON.stringify(body || {}) }); return { status: r.status, j: await r.json().catch(() => ({})) }; };
let st = await admin("state", "GET");
ok((st.j.strategies || []).some(s => s.code === "TEST" && !s.listed), "送過的策略自動登記成下架", JSON.stringify(st.j.strategies));
ok((await post("strategy?code=GEA5", { listed: true })).status === 200 && (await post("strategy?code=GEA6", { listed: false })).status === 200, "登記 GEA5 上架、GEA6 下架");
for (const [id, subs] of [["s1", ["GEA5"]], ["s2", ["GEA5", "GEA6"]], ["s3", ["GEA6"]], ["s0", undefined]]) {
  const rr = await post("user?id=" + id, subs ? { subs } : {}); tok[id] = rr.j.token;
}
st = await admin("state", "GET");
ok((st.j.users || []).find(u => u.id === "s0").subs === "", "新用戶沒指定訂閱 → 什麼都沒訂");
const sc = {};
for (const id of ["s1", "s2", "s3", "s0"]) { sc[id] = await connect("sub", id, tok[id]); ok(!sc[id].err, `訂閱測試接收端 ${id} 連上`); }
const got = id => sc[id].got.map(m => m.Strategy + m.Seq).join(",");
const sigS = (seq, strat) => sig(seq, { Strategy: strat });
let q = 521;
pub.ws.send(sigS(q, "GEA5"));
await until(() => sc.s1.got.length >= 1 && sc.s2.got.length >= 1); await sleep(300);
ok(got("s1") === "GEA5521" && got("s2") === "GEA5521" && got("s3") === "" && got("s0") === "", "GEA5（上架）只送訂 GEA5 的 s1、s2", `s1 ${got("s1")}｜s2 ${got("s2")}｜s3 ${got("s3")}｜s0 ${got("s0")}`);
const ackS = () => pub.ctl.filter(c => c.ctl === "ack").pop();
await until(() => ackS() && ackS().seq === q);
ok(ackS().subs === 2 + 2 && ackS().online >= 6, "ack 的 subs＝實際送出數（s1、s2＋兩個全部訂閱）", JSON.stringify(ackS()));
pub.ws.send(sigS(++q, "GEA6"));
await until(() => subs.u1.got.some(m => m.Seq === q)); await sleep(300);
ok(got("s2") === "GEA5521" && got("s3") === "" && subs.u1.got.some(m => m.Seq === q), "GEA6（下架）一般客戶都收不到；訂「全部」的照收");
await post("strategy?code=GEA6", { listed: true });
pub.ws.send(sigS(++q, "GEA6"));
await until(() => sc.s3.got.length >= 1); await sleep(300);
ok(got("s2") === "GEA5521,GEA6523" && got("s3") === "GEA6523" && got("s1") === "GEA5521", "GEA6 上架後 → 送 s2、s3，s1 照樣收不到", `s1 ${got("s1")}｜s2 ${got("s2")}｜s3 ${got("s3")}`);
pub.ws.send(sigS(++q, "NEWONE"));
await until(() => subs.u1.got.some(m => m.Seq === q)); await sleep(300);
st = await admin("state", "GET");
ok((st.j.strategies || []).some(s => s.code === "NEWONE" && !s.listed) && got("s2") === "GEA5521,GEA6523", "新策略 NEWONE 自動登記下架、一般客戶收不到");
const s1b = await connect("sub", "s1", tok.s1);
s1b.ws.send(JSON.stringify({ since: 520 }));
await until(() => s1b.ctl.some(c => c.ctl === "replayed"));
ok(s1b.got.map(m => m.Seq).join() === "521", "s1 重連 since=520 只補他訂的（521），不補 522～524", s1b.got.map(m => m.Seq).join());
s1b.ws.close();
const rp2 = await admin("replay?id=s3&since=520", "GET");
ok(JSON.stringify(rp2.j.will) === "[522,523]", "/admin/replay：s3 會補 522、523（補發依「現在」的上架與訂閱判斷）", JSON.stringify(rp2.j));
const sim = await post("simulate", { strategy: "GEA5" });
const simOf = id => (sim.j.users || []).find(u => u.id === id) || {};
ok(simOf("s1").receive && !simOf("s3").receive && simOf("s3").why === "沒訂閱" && simOf("u4").why === "停權", "/admin/simulate 原因正確", JSON.stringify(sim.j.users.map(u => u.id + ":" + u.why)));
await post("set?id=s2", { exp: "2020-01-01" });
await until(() => kickedCode(sc.s2));
ok(kickedCode(sc.s2) === 4003, "改成已到期 → 在線立刻 4003 斷線", String(kickedCode(sc.s2)));
r = await connect("sub", "s2", tok.s2);
ok(r.err === 403, "到期用戶再連 → 403", "HTTP " + r.err);
await post("set?id=s1", { subs: [] });
pub.ws.send(sigS(++q, "GEA5"));
await until(() => subs.u1.got.some(m => m.Seq === q)); await sleep(300);
ok(got("s1") === "GEA5521", "s1 取消訂閱後收不到 GEA5（不用重連，下一則就生效）");
ok((await post("testpub", { strategy: "GEA5" })).status === 403, "testpub 只限 test 開頭頻道（正式頻道 403）");
const cons = await fetch(`${BASE}/console`);
ok(cons.status === 200 && (await cons.text()).includes("GEA 下單訊號管理"), "管理頁 /console 開得起來（不含資料）");
for (const id of ["s1", "s3", "s0"]) sc[id].ws.close();

// ── 同代號只留一條（總指揮 2026-10-19 00:50）：同 id 連兩次 → 舊的以 4009 被踢、新的照收、訊號只送一份
const dj = await admin("user?id=d1&subs=*");
const d1a = await connect("sub", "d1", dj.j.token);
const d1b = await connect("sub", "d1", dj.j.token);
await until(() => kickedCode(d1a));
ok(kickedCode(d1a) === 4009, "同代號第二條連上 → 第一條以 4009 被踢", String(kickedCode(d1a)));
ok(!kickedCode(d1b), "新的那條保持連線");
const st9 = await admin("state", "GET");
const d1on = (st9.j.users || []).find(x => x.id === "d1") || {};
ok(d1on.online === 1 && (st9.j.conns || []).filter(c => c.id === "d1").length === 1, "/admin/state：d1 只剩 1 條（conns 有連線明細）", JSON.stringify((st9.j.conns || []).filter(c => c.id === "d1")));
const nA = d1a.got.length;
pub.ws.send(sig(++q, { Strategy: "GEA5" }));
await until(() => d1b.got.some(m => m.Seq === q)); await sleep(300);
ok(d1b.got.filter(m => m.Seq === q).length === 1 && d1a.got.length === nA, "訊號只送新的那條、只一份");
d1b.ws.close();

// ── 收尾
for (const c of [subs.u1, u3b, pub]) c.ws.close();
await sleep(300);
ok((await admin("purge")).status === 200, "測試頻道刪除");
console.log(fails ? `✗✗ ${fails} 項沒過` : "全部通過");
process.exit(fails ? 1 : 0);
