// test.mjs ── gea-signal-relay 自動測試（Evans 2026-10-11 15:50 派工第 2 項）
//   1 個發送端＋3 個接收端：正常廣播、接收端斷線後補發、錯誤 token 被拒、停權用戶被拒（含在線被踢）、格式錯誤被拒、
//   重送不重播、接收端不能發、心跳自動回應、/health；印每則延遲（同一台機器量：發送 → 3 個接收端都收到）。
//   用法：BASE=https://… RELAY_PUB_TOKEN=… RELAY_ADMIN_TOKEN=… node test.mjs   （需要 npm 套件 ws）
//   每次用新頻道 t<時間>，測完 /admin/purge 刪掉。任何一項沒過 → exit 1。
import WebSocket from "ws";
import { createHash } from "node:crypto";

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
function connect(role, id, token, v2 = false, hdr = {}) {
  return new Promise(res => {
    const c = { got: [], ctl: [], pong: 0, closed: null, t: [] };
    const ws = new WebSocket(`${WSB}/ws?ch=${CH}&role=${role}&id=${id}${v2 ? "&v=2" : ""}`, { headers: { Authorization: "Bearer " + token, ...hdr } });
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
const post = async (path, body) => { const r = await fetch(`${BASE}/admin/${path}${path.includes("?") ? "&" : "?"}ch=${CH}`, { method: "POST",
  headers: { Authorization: "Bearer " + ADMIN, "content-type": "application/json" }, body: JSON.stringify(body || {}) }); return { status: r.status, j: await r.json().catch(() => ({})) }; };
ok((await post("risk", { max: 100, win: 5 })).status === 200, "（舊測試連發很多則：連續下單風控先放寬到 5 秒 100 次；風控在最後另測）");
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
for (let i = 16; i <= 520; i++) pub.ws.send(sig(i, { Strategy: "B" + (i % 10) }));   // 分 10 支策略送，不碰連續下單風控
await until(() => pub.ctl.filter(c => c.ctl === "ack" && c.seq === 520).length === 1, 20000);
tok.r1 = (await admin("user?id=r1&subs=*")).j.token;               // 另開代號：同代號再連會把 u1 踢掉（4009，同代號只留一條）
const old = await connect("sub", "r1", tok.r1);
old.ws.send(JSON.stringify({ since: 0 }));
await until(() => old.ctl.some(c => c.ctl === "replayed"), 20000);
const rq = old.ctl.find(c => c.ctl === "replayed") || {};
ok(old.got.length === 500 && old.got[0].Seq === 21 && rq.last === 520 && JSON.stringify(rq.gap) === "[1,20]", "只留 500 則（21～520），since=0 回報缺段 1～20", `${old.got.length} 則、${JSON.stringify(rq)}`);
old.ws.close();

// ── 訂閱控管（10-18 20:40 派工第 1 項）：只轉送訂閱且上架的策略；補發照同一規則；到期踢線；模擬端點；管理頁
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
ok(simOf("s1").receive && !simOf("s3").receive && simOf("s3").why === "沒訂閱" && /^停/.test(simOf("u4").why), "/admin/simulate 原因正確", JSON.stringify(sim.j.users.map(u => u.id + ":" + u.why)));
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

// ── 11-01 下單機 1.0：開通碼、服務期間（v2 收 4012）、部位快照、hello／recon／tg、連續下單風控、合約表
const rd = async (code, want) => { const r = await fetch(`${BASE}/redeem?ch=${CH}`, { method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ code, ver: "test", ...(want ? { want } : {}) }) }); return { status: r.status, j: await r.json().catch(() => ({})) }; };
const inv = await post("invite?id=n1", { subs: ["GEA5"], exp: "2099-12-31" });
ok(inv.status === 200 && /^[2-9A-HJ-NP-Z]{8}$/.test(inv.j.code || ""), "產開通碼：8 碼、沒有 0／O／1／I", inv.j.code);
ok((await rd("AAAAAAAA")).status === 404, "錯的開通碼 → 404");
const red = await rd(inv.j.code.toLowerCase().slice(0, 4) + "-" + inv.j.code.slice(4));
ok(red.status === 200 && red.j.id === "n1" && /^[0-9a-f]{48}$/.test(red.j.token || "") && red.j.off === null, "開通碼換 token（小寫、連字號都容許）", "HTTP " + red.status);
{ const again = await rd(inv.j.code);
  ok(again.status === 404 && again.j.why === "used" && /已經用過/.test(again.j.error || ""), "開通碼用過就作廢；再填一次回「已經用過」（不是過期）", again.j.error); }
{ const bad = await rd("ZZZZZZZZ");
  ok(bad.status === 404 && bad.j.why === "bad" && /不對/.test(bad.j.error || ""), "沒有這組開通碼 → 回「開通碼不對」", bad.j.error); }
tok.n1 = red.j.token;
const n1 = await connect("sub", "n1", tok.n1, true);
ok(!n1.err, "n1（v2）連上");
n1.ws.send(JSON.stringify({ hello: { ver: "20261101a" } }));
n1.ws.send(JSON.stringify({ since: 1e15, snap: 1 }));
await until(() => n1.ctl.some(c => c.ctl === "replayed"));
const sn = n1.ctl.find(c => c.ctl === "snap") || {};
ok(sn.n === 1 && sn.items[0].Strategy === "GEA5" && sn.items[0].Seq === q && n1.got.length === 0, "部位快照：只給他訂的 GEA5 最新一則、since 很大就不補發", JSON.stringify(sn).slice(0, 160));
ok(Array.isArray(sn.strats) && sn.strats.includes("GEA5") && sn.strats.every(c => c === "GEA5"), "快照附他訂閱且已上架的策略清單（只訂 GEA5 → [GEA5]）", JSON.stringify(sn.strats));
{ const ra = await post("user?id=sall", { subs: "*" }); const sa = await connect("sub", "sall", ra.j.token, true);
  sa.ws.send(JSON.stringify({ since: 1e15, snap: 1 }));
  await until(() => sa.ctl.some(c => c.ctl === "replayed"));
  const ss = (sa.ctl.find(c => c.ctl === "snap") || {}).strats || [], all = ((await admin("state", "GET")).j.strategies || []);
  const want = all.filter(x => x.listed).map(x => x.code).sort();
  ok(want.length >= 2 && JSON.stringify(ss) === JSON.stringify(want) && !ss.some(c => all.find(x => x.code === c && !x.listed)), "訂閱全部 → 快照列出所有已上架策略（不含下架的）", JSON.stringify(ss));
  sa.ws.close();
  // 11-02 13:45 第 1 項：「*」＝只收已上架；「**」＝全部含下架（只能管理頁設，開通碼不給）
  await post("strategy?code=T_OFFX", { listed: false });
  const r2 = await post("user?id=sall2", { subs: "**" });
  const sm = (await post("simulate", { strategy: "T_OFFX" })).j.users || [];
  const s1 = sm.find(x => x.id === "sall") || {}, s2 = sm.find(x => x.id === "sall2") || {};
  ok(s1.receive === false && /未上架/.test(s1.why || "") && s2.receive === true, "下架策略：訂閱「*」收不到、「**」收得到", JSON.stringify([s1, s2]));
  const sb = await connect("sub", "sall2", r2.j.token, true);
  sb.ws.send(JSON.stringify({ since: 1e15, snap: 1 }));
  await until(() => sb.ctl.some(c => c.ctl === "replayed"));
  ok(((sb.ctl.find(c => c.ctl === "snap") || {}).strats || []).includes("T_OFFX"), "「**」的快照策略清單含下架的 T_OFFX");
  sb.ws.close();
  ok((await post("invite?id=sall3", { subs: "**" })).status === 400, "開通碼不能給「**」");
  await post("strategy_delete?code=T_OFFX", {}); }
n1.ws.send(JSON.stringify({ recon: { ok: false, detail: "GEA5 檔案 1、中繼最新 0" } }));
n1.ws.send(JSON.stringify({ tg: "測試：接收端 TG 經中繼" }));
await sleep(500);
st = await admin("state", "GET");
const n1s = (st.j.users || []).find(x => x.id === "n1") || {};
ok(n1s.ver === "20261101a" && /^✗ GEA5/.test(n1s.recon || "") && st.j.tg_test >= 1, "hello／recon 記進管理頁、tg 轉發（測試頻道只計數）", JSON.stringify({ ver: n1s.ver, recon: n1s.recon, tg: st.j.tg_test }));
const cu = `${BASE}/contracts?ch=${CH}&id=n1`;
const ct = await fetch(cu, { headers: { Authorization: "Bearer " + tok.n1 } });
const ctext = await ct.text(), csig = ct.headers.get("x-gea-sig") || "";
ok(ct.status === 200 && ctext.includes("TAIFEX.TMF,") && csig.length === 88 && /^\d{12}$/.test(ct.headers.get("x-gea-ver") || ""), "GET /contracts：合約表＋簽章＋版本", `HTTP ${ct.status}、${ctext.split("\n").length - 1} 列、版本 ${ct.headers.get("x-gea-ver")}`);
ok((await fetch(cu, { headers: { Authorization: "Bearer deadbeef" } })).status === 401 && (await fetch(cu)).status === 401, "GET /contracts 錯 token／沒 token → 401");
{ // 11-01 21:00 A2：沒連 WebSocket 的行程（設定精靈、GeaApiCheck）走 POST /tg
  const tu = `${BASE}/tg?ch=${CH}&id=n1`, before = (await admin("state", "GET")).j.tg_test;
  const tr = await fetch(tu, { method: "POST", headers: { Authorization: "Bearer " + tok.n1, "Content-Type": "application/json" }, body: JSON.stringify({ tg: "測試：POST /tg" }) });
  const tj = await tr.json().catch(() => ({}));
  const after = (await admin("state", "GET")).j.tg_test;
  const bad = await fetch(tu, { method: "POST", headers: { Authorization: "Bearer deadbeef" }, body: "{}" });
  ok(tr.status === 200 && tj.ok !== undefined && after === before + 1 && bad.status === 401, "POST /tg（客戶 token）轉發給 Evans；錯 token → 401", `HTTP ${tr.status}、tg_test ${before}→${after}、錯 token ${bad.status}`);
}
const vr = await fetch(`${BASE}/version`), vj = await vr.json().catch(() => null);
ok(vr.status === 200 && vj && "ver" in vj && "sha256" in vj && "sig" in vj, "GET /version（不用 token）：版號、SHA256、簽章欄位都在", `HTTP ${vr.status}、ver「${vj && vj.ver}」`);
await post("set?id=n1", { exp: "2020-01-01" });
await until(() => kickedCode(n1));
ok(kickedCode(n1) === 4012, "v2 接收端到期 → 4012（顯示「服務期限已到」，不平倉）", String(kickedCode(n1)));
let n1b = await connect("sub", "n1", tok.n1, true);
await until(() => kickedCode(n1b));
ok(!n1b.err && kickedCode(n1b) === 4012, "到期後 v2 再連 → 先接受再 4012", String(n1b.err || kickedCode(n1b)));
r = await connect("sub", "n1", tok.n1);
ok(r.err === 403, "到期後舊接收端再連 → 照舊 403", "HTTP " + r.err);
await post("set?id=n1", { start: "2099-01-01", exp: "2099-12-31" });
n1b = await connect("sub", "n1", tok.n1, true);
await until(() => kickedCode(n1b));
ok(kickedCode(n1b) === 4012 && /not started/.test(n1b.closed ? n1b.closed[1] : n1b.ws._closeMessage || "not started"), "還沒開始 → 4012", String(kickedCode(n1b)));
await post("set?id=n1", { start: "", exp: "2099-12-31" });
n1b = await connect("sub", "n1", tok.n1, true);
await sleep(500);
ok(!n1b.err && !kickedCode(n1b), "改回服務期間內 → 可再連");
// 連續下單風控：60 秒內第 5 次 → 暫停、不轉送；解除後恢復
await post("risk", { max: 4, win: 60 });
await post("strategy?code=RSK", { listed: true });
const n0 = subs.u1.got.length;
for (let i = 0; i < 6; i++) { pub.ws.send(sig(++q, { Strategy: "RSK" })); await sleep(80); }
await until(() => pub.ctl.filter(c => c.ctl === "ack" && c.seq === q).length === 1); await sleep(300);
const rk = subs.u1.got.slice(n0).filter(m => m.Strategy === "RSK").length;
const pz = pub.ctl.filter(c => c.ctl === "ack" && c.paused).length;
st = await admin("state", "GET");
ok(rk === 4 && pz === 2 && (st.j.strategies || []).some(s => s.code === "RSK" && s.paused), "60 秒內第 5 次起暫停轉送（4 則送出、2 則擋下、ack 帶 paused）", `送出 ${rk}、擋下 ${pz}`);
const heldA = q - 1, heldB = q;                                          // 被擋下的兩則
const u1v2 = await connect("sub", "u1", tok.u1, true);
const un = await post("strategy?code=RSK", { paused: false });
await until(() => u1v2.ctl.some(c => c.ctl === "align"));
const al = u1v2.ctl.find(c => c.ctl === "align");
ok(al && al.strat === "RSK" && al.items[0].Seq === heldB && !subs.u1.ctl.some(c => c.ctl === "align"),
   "11-01 14:15：解除 → 暫停期間最後一則當目標部位，送 align 給 v2 接收端（舊接收端不送）", JSON.stringify(un.j.aligned));
u1v2.ws.send(JSON.stringify({ since: heldA - 5 }));
await until(() => u1v2.ctl.some(c => c.ctl === "replayed"));
ok(u1v2.got.length > 0 && !u1v2.got.some(m => m.Seq === heldA || m.Seq === heldB), "斷線補發不補暫停期間的訊號（不逐筆補送）", u1v2.got.map(m => m.Seq).join());
u1v2.ws.close();
subs.u1 = await connect("sub", "u1", tok.u1);                            // 同代號只留一條：剛才 v2 那條把舊的 u1 擠掉了，重連回來
await sleep(300);
pub.ws.send(sig(++q, { Strategy: "RSK" }));
await until(() => subs.u1.got.some(m => m.Seq === q));
ok(subs.u1.got.some(m => m.Seq === q), "管理頁解除暫停 → 下一則照送（暫停期間的不補）");
n1b.ws.close();

// ── 11-01 21:00 B 身分證綁定：idh＝SHA-256("GEA-ID|"+身分證)；換身分證被擋（4013／開通 403）、同身分證兩代號同策略被擋（4014）、管理者多台一台真單其他模擬可過
{
  const idh = x => createHash("sha256").update("GEA-ID|" + x).digest("hex");
  const H = (x, m, mode = "real") => ({ "X-Gea-Idh": idh(x), "X-Gea-Idm": m, "X-Gea-Mode": mode });
  const rdi = async (code, x, m) => { const r = await fetch(`${BASE}/redeem?ch=${CH}`, { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ code, ver: "test", idh: idh(x), idm: m }) }); return { status: r.status, j: await r.json().catch(() => ({})) }; };
  const A = "A123456789", B = "B223456789";
  let iv = await post("invite?id=b1", { subs: ["GEA5"], exp: "2099-12-31" });
  const r1 = await rdi(iv.j.code, A, "A12****789");
  ok(r1.status === 200, "開通時帶身分證雜湊 → 綁上", "HTTP " + r1.status);
  tok.b1 = r1.j.token;
  let st = await admin("state", "GET"), b1s = (st.j.users || []).find(x => x.id === "b1") || {};
  ok((b1s.ids || []).length === 1 && b1s.ids[0].mask === "A12****789" && !JSON.stringify(st.j).includes(A) && !JSON.stringify(st.j).includes(idh(A)),
     "管理頁只看到遮罩（不出現明碼、也不出現客戶端雜湊）", JSON.stringify(b1s.ids));
  iv = await post("invite?id=b1", { subs: ["GEA5"], exp: "2099-12-31" });
  const r2 = await rdi(iv.j.code, B, "B22****789");
  ok(r2.status === 403 && /身分證與開通時不同/.test(r2.j.error || ""), "換身分證再開通 → 403「身分證與開通時不同，請聯絡營業員」", "HTTP " + r2.status);
  st = await admin("state", "GET");
  ok((st.j.invites || []).some(x => x.code === iv.j.code), "被擋時開通碼不作廢（營業員解除綁定後可再用）");
  let b1 = await connect("sub", "b1", tok.b1, true, H(B, "B22****789"));
  await until(() => kickedCode(b1));
  ok(kickedCode(b1) === 4013, "已綁 A、連線帶 B → 4013", String(kickedCode(b1)));
  b1 = await connect("sub", "b1", tok.b1, true);
  await until(() => kickedCode(b1));
  ok(kickedCode(b1) === 4013, "已綁、連線沒帶身分證（舊版）→ 4013", String(kickedCode(b1)));
  b1 = await connect("sub", "b1", tok.b1, true, H(A, "A12****789"));
  await sleep(400);
  ok(!b1.err && !kickedCode(b1), "帶對的身分證 → 連上");
  const b2t = (await admin("user?id=b2&subs=GEA5")).j.token, b3t = (await admin("user?id=b3&subs=OTHER")).j.token;
  let b2 = await connect("sub", "b2", b2t, true, H(A, "A12****789"));
  await until(() => kickedCode(b2));
  ok(kickedCode(b2) === 4014, "同身分證、另一個代號、同策略 GEA5、b1 在線 → 後連上的 b2 被拒 4014", String(kickedCode(b2)));
  const b3 = await connect("sub", "b3", b3t, true, H(A, "A12****789"));
  await sleep(400);
  ok(!b3.err && !kickedCode(b3), "同身分證、沒有重疊的策略 → 可以");
  const sh = (b1s.ids[0] || {}).sh;
  ok((await post("idadmin", { sh })).j.admin === true, "管理頁把身分證標成管理者");
  b2 = await connect("sub", "b2", b2t, true, H(A, "A12****789", "real"));
  await until(() => kickedCode(b2));
  ok(kickedCode(b2) === 4014, "管理者：b1 真單在線、b2 也要真單 → 4014", String(kickedCode(b2)));
  b2 = await connect("sub", "b2", b2t, true, H(A, "A12****789", "sim"));
  await sleep(400);
  ok(!b2.err && !kickedCode(b2), "管理者：b2 用模擬 → 可以（同策略一台真單、其他模擬）");
  st = await admin("state", "GET");
  ok((st.j.conns || []).some(c => c.id === "b2" && c.mode === "sim" && c.idm === "A12****789"), "管理頁連線明細看得到模式與遮罩");
  ok((await post("bind?id=b1", { idh: idh(B), idm: "B22****789" })).j.ids.length === 2, "Evans 手動幫 b1 加第二個身分證");
  const b1b = await connect("sub", "b1", tok.b1, true, H(B, "B22****789"));
  await sleep(400);
  ok(!b1b.err && !kickedCode(b1b), "加了之後 B 也能連 b1");
  ok((await post("unbind?id=b1", { idh: idh(B) })).j.removed === 1, "解除綁定");
  await post("idadmin", { sh, admin: false });
  for (const c of [b1b, b2, b3]) c.ws.close();
}

// ── 11-01 21:00 C：TG 指令（測試頻道走 /admin/tgcmd，回覆直接回傳、不發 TG）、一次性登入連結防呆、webhook 驗 secret
{
  const cmd = async text => (await post("tgcmd", { text })).j.replies || [];
  await post("strategy?code=GEA5", { listed: true });
  let R = await cmd("/開通碼 王小明 GEA5 2099-12-31");
  const m = /開通碼 ([2-9A-HJ-NP-Z]{4})-([2-9A-HJ-NP-Z]{4})/.exec(R[0] || "");
  ok(m && /新客戶 c\d{9}，王小明/.test(R[0]) && R.length === 2 && R[1].includes(m[1] + "-" + m[2]) && /24 小時內有效/.test(R[1]) && /https:\/\//.test(R[1]),
     "/開通碼 姓名 策略 到期日 → 8 碼＋可直接轉給客戶的文字（下載網址、24 小時）", (R[0] || "").slice(0, 80));
  const st = await admin("state", "GET"), cu = (st.j.users || []).find(u => u.note === "王小明") || {};
  ok(cu.subs === "GEA5" && cu.exp === "2099-12-31" && (st.j.invites || []).some(x => x.id === cu.id), "中繼建好客戶（姓名當備註、自動代號、訂閱、到期、開通碼待用）", cu.id);
  R = await cmd("/開通碼 王小明 全部 2099-12-31");
  ok(/既有客戶/.test(R[0] || "") && ((await admin("state", "GET")).j.users || []).find(u => u.id === cu.id).subs === "*", "同一姓名再產 → 沿用同一代號、改訂閱「全部」");
  ok(/沒有上架/.test((await cmd("/開通碼 x1 NOPE 2099-12-31"))[0] || ""), "策略沒上架 → 不產、列出已上架的");
  ok(/YYYY-MM-DD/.test((await cmd("/開通碼 x1 GEA5 明年"))[0] || ""), "到期日格式錯 → 不產");
  ok(/王小明/.test((await cmd("/客戶 王小明"))[0] || "") && /身分證：還沒綁/.test((await cmd("/客戶 " + cu.id))[0] || ""), "/客戶 代號或姓名 → 狀態（身分證只有遮罩）");
  ok(/已停用/.test((await cmd("/停用 " + cu.id))[0] || "") && ((await admin("state", "GET")).j.users || []).find(u => u.id === cu.id).enabled === false, "/停用");
  ok(/已恢復/.test((await cmd("/恢復 王小明"))[0] || "") && ((await admin("state", "GET")).j.users || []).find(u => u.id === cu.id).enabled === true, "/恢復");
  // 11-02 12:15 第 2 項：/策略、/上架、/下架、/訂閱
  await post("strategy?code=GEA_NEWX", { listed: false });
  R = await cmd("/策略");
  ok(/✅ 上架 GEA5/.test(R[0] || "") && /⛔ 下架 GEA_NEWX/.test(R[0] || "") && /最後訊號/.test(R[0] || "") && /訂閱 \d+ 人/.test(R[0] || ""), "/策略 → 代號、上架／下架、最後訊號、訂閱人數", (R[0] || "").slice(0, 120));
  ok(/沒有策略 NOPE/.test((await cmd("/上架 NOPE"))[0] || ""), "/上架 打錯代號 → 不新增、列出現有的");
  ok(/已上架/.test((await cmd("/上架 GEA_NEWX"))[0] || "") && ((await admin("state", "GET")).j.strategies || []).find(s => s.code === "GEA_NEWX").listed === true, "/上架 GEA_NEWX");
  R = await cmd("/訂閱 王小明 GEA5,GEA_NEWX");
  ok(/不用重發開通碼/.test(R[0] || "") && /新增：GEA_NEWX/.test(R[0] || "") && ((await admin("state", "GET")).j.users || []).find(u => u.id === cu.id).subs === "GEA5,GEA_NEWX", "/訂閱 姓名 策略 → 改訂閱、列出新增", (R[0] || "").slice(0, 120));
  R = await cmd("/訂閱 " + cu.id + " GEA5");
  ok(/取消：GEA_NEWX/.test(R[0] || "") && /不自動平倉/.test(R[0] || ""), "/訂閱 少掉策略 → 列出取消、註明不自動平倉");
  ok(/已下架/.test((await cmd("/下架 GEA_NEWX"))[0] || "") && /沒有上架/.test((await cmd("/訂閱 王小明 GEA_NEWX"))[0] || ""), "/下架 → 再訂閱下架的策略會被擋");
  ok(/指令/.test((await cmd("你好"))[0] || ""), "看不懂的 → 回指令說明");
  ok((await post("tgcmd", { text: "x" }).then(() => fetch(`${BASE}/admin/tgcmd?ch=gea`, { method: "POST", headers: { Authorization: "Bearer " + ADMIN }, body: "{}" }))).status === 403, "tgcmd 不能打正式頻道");
  const hk = await fetch(`${BASE}/tg_hook`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: { chat: { id: 1 }, text: "/客戶" } }) });
  ok(hk.status === 401, "TG webhook 沒帶 secret → 401（別人偽造的更新不處理）", "HTTP " + hk.status);
  const lg = await (await fetch(`${BASE}/login?t=${"0".repeat(48)}`)).text();
  const lp = await (await fetch(`${BASE}/login`, { method: "POST", body: new URLSearchParams({ t: "0".repeat(48) }), redirect: "manual" }));
  ok(/已用過、已過期/.test(lg) && lp.status === 200 && /已用過或已過期/.test(await lp.text()) && !lp.headers.get("set-cookie"), "假的一次性登入連結：GET 不給按鈕、POST 不發 cookie");
  const ck = await fetch(`${BASE}/admin/state?ch=${CH}`, { headers: { cookie: "gea_radm=" + "a".repeat(96) } });
  ok(ck.status === 401, "假的登入 cookie → 401", "HTTP " + ck.status);
}

// ── 11-01 23:40：傳送端開通碼（pub）——一般開通碼拿不到傳送端、管理者開通碼才拿得到；兩種 token 不能互換角色；同一台兩角色互不干擾
{
  const cmd = async text => (await post("tgcmd", { text })).j.replies || [];
  const sv = await post("invite?id=r1", { subs: ["GEA5"], exp: "2099-12-31" });
  const ws1 = await rd(sv.j.code, "pub");
  ok(ws1.status === 400 && /不是管理者開通碼/.test(ws1.j.error || ""), "客戶開通碼填到「管理者開通碼」→ 400、拿不到傳送端", "HTTP " + ws1.status);
  const rs = await rd(sv.j.code);
  ok(rs.status === 200, "（同一個客戶開通碼沒被作廢，第 3 步照樣能用）", "HTTP " + rs.status);
  ok(rs.status === 200 && rs.j.role === "sub", "一般開通碼兌換 → role=sub（精靈只顯示接收端）", rs.j.role);
  const xs = await connect("pub", "r1", rs.j.token);
  ok(xs.err === 401, "客戶 token 不能當傳送端連（401）", String(xs.err));
  const R = await cmd("/開通碼 傳送端 sh2 測試訊號主機");
  const m = /傳送端）([2-9A-HJ-NP-Z]{4})-([2-9A-HJ-NP-Z]{4})/.exec(R[0] || "");
  ok(!!m && /不要轉給客戶/.test(R[0]), "TG「/開通碼 傳送端 代號 備註」→ 管理者開通碼", (R[0] || "").slice(0, 60));
  ok(/格式/.test((await cmd("/開通碼 傳送端"))[0] || ""), "/開通碼 傳送端 沒給代號 → 回格式");
  let st = await admin("state", "GET");
  ok((st.j.invites || []).some(x => x.id === "sh2" && x.kind === "pub") && !(st.j.users || []).some(u => u.id === "sh2"), "管理者開通碼不建客戶（不在客戶列表、不收訊號）");
  const wp = await rd(m ? m[1] + m[2] : "x");
  ok(wp.status === 400 && /管理者開通碼/.test(wp.j.error || ""), "管理者開通碼填到客戶的第 3 步（舊版沒帶 want）→ 400、不作廢", "HTTP " + wp.status);
  const rp = await rd(m ? m[1] + m[2] : "x", "pub");
  ok(rp.status === 200 && rp.j.role === "pub" && rp.j.id === "sh2" && /^[0-9a-f]{48}$/.test(rp.j.token || ""), "管理者開通碼兌換 → role=pub＋傳送端 token", "HTTP " + rp.status);
  ok((await rd(m ? m[1] + m[2] : "x", "pub")).status === 404, "管理者開通碼用過就作廢");
  const xp = await connect("sub", "sh2", rp.j.token, true);
  ok(xp.err === 401, "傳送端 token 不能當接收端連（401）", String(xp.err));
  const p2 = await connect("pub", "sh2", rp.j.token);
  ok(!p2.err, "傳送端 token 以 role=pub 連上", String(p2.err || ""));
  // 同一台兩角色：傳送端 sh2＋接收端 r1（同時在線）；sh2 送的訊號 r1 照訂閱收到、各自的連線不互踢
  const r1 = await connect("sub", "r1", rs.j.token, true);
  await sleep(300);
  r1.ws.send(JSON.stringify({ since: q }));
  await post("strategy?code=GEA5", { listed: true });
  p2.ws.send(sigS(++q, "GEA5"));
  await until(() => p2.ctl.some(c => c.ctl === "ack" && c.seq === q) && r1.got.some(x => x.Seq === q));
  ok(p2.ctl.some(c => c.ctl === "ack" && c.seq === q) && r1.got.some(x => x.Seq === q) && !p2.closed && !r1.closed, "同一台：傳送端送、接收端收，兩條連線都還在");
  const n0 = (await admin("state", "GET")).j.tg_test;
  p2.ws.send(JSON.stringify({ tg: "傳送端測試通知" }));
  await until(() => p2.ctl.some(c => c.ctl === "tg"));
  ok(p2.ctl.some(c => c.ctl === "tg" && c.ok) && (await admin("state", "GET")).j.tg_test > n0, "傳送端沒有 bot token → {tg} 經中繼轉給 Evans");
  st = await admin("state", "GET");
  ok(((st.j.pubs || []).find(x => x.id === "sh2") || {}).online === 1, "管理頁傳送端列表：sh2 在線");
  await post("pub_disable?id=sh2", {});
  await until(() => p2.closed);
  ok(p2.closed && p2.closed[0] === 4003, "停用傳送端 → 在線的以 4003 關閉", JSON.stringify(p2.closed));
  ok((await connect("pub", "sh2", rp.j.token)).err === 401, "停用後不能再連");
  ok(!pub.closed, "現行訊號主機（RELAY_PUB_TOKEN）不受影響");
  r1.ws.close();
}

// ── 收尾
for (const c of [subs.u1, u3b, pub]) c.ws.close();
await sleep(300);
ok((await admin("purge")).status === 200, "測試頻道刪除");
console.log(fails ? `✗✗ ${fails} 項沒過` : "全部通過");
process.exit(fails ? 1 : 0);
