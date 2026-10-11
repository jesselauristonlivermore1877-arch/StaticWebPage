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
const until = async (fn, ms = 5000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(20); } return fn(); };

console.log("頻道", CH, "｜", BASE);
// ── 建用戶
const tok = {};
for (const u of ["u1", "u2", "u3", "u4"]) {
  const r = await admin("user?id=" + u);
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
await until(() => subs.u2.closed);
ok(subs.u2.closed && subs.u2.closed[0] === 4003, "在線用戶停權 → 立刻以 4003 關閉", JSON.stringify(subs.u2.closed));
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
const old = await connect("sub", "u1", tok.u1);
old.ws.send(JSON.stringify({ since: 0 }));
await until(() => old.ctl.some(c => c.ctl === "replayed"), 20000);
const rq = old.ctl.find(c => c.ctl === "replayed") || {};
ok(old.got.length === 500 && old.got[0].Seq === 21 && rq.last === 520 && JSON.stringify(rq.gap) === "[1,20]", "只留 500 則（21～520），since=0 回報缺段 1～20", `${old.got.length} 則、${JSON.stringify(rq)}`);
old.ws.close();

// ── 收尾
for (const c of [subs.u1, u3b, pub]) c.ws.close();
await sleep(300);
ok((await admin("purge")).status === 200, "測試頻道刪除");
console.log(fails ? `✗✗ ${fails} 項沒過` : "全部通過");
process.exit(fails ? 1 : 0);
