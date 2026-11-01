// gea-signal-relay ── 下單訊號雲端中繼（Evans 2026-10-11 15:50 派工）
// 協定（兩端照做，不准各自改；全文在 CustomerServiceANDSales TODO.md「2026-10-11 15:50 總指揮派工」）：
//   連線  wss://<host>/ws?ch=<頻道>&role=pub|sub&id=<用戶代號>[&v=2]，Header「Authorization: Bearer <token>」
//         pub token＝Worker secret RELAY_PUB_TOKEN；sub token 每位用戶一組，存在該頻道 DO 的 SQLite（只存 SHA-256）。
//         v=2＝11-01 新接收端（認得 4012、會送 hello／snap／recon／tg）；沒帶＝舊接收端（照舊 403／4003）。
//   發送  pub 送訊號 JSON（Seq、TsMs、…、Sig；11-01 起另有 Sig2＝ECDSA 公鑰簽章）→ DO 檢查格式、Seq 必須遞增 → 存最近 500 則 → 原文廣播給所有 sub。
//         回 pub：{"ctl":"ack","seq":N}；重送（Seq ≤ 最後一則）回 {"ctl":"dup","seq":N}、不再廣播；格式錯回 {"ctl":"err","why":…}。
//   補發  sub 連上後送 {"since":<最後收到的 Seq>[, "snap":1]} → 有 snap 先送 {"ctl":"snap","items":[每支策略最新一則原文…]}（11-01 部位快照），
//         再依序補發 Seq > since 的原文，最後送 {"ctl":"replayed","n":筆數,"last":最後 Seq}。
//   心跳  兩端送文字 "ping" → 自動回 "pong"（setWebSocketAutoResponse，不喚醒 DO、不計費）；90 秒沒回應就重連（指數退避上限 30 秒，用戶端負責）。
//   同代號只留一條（總指揮 2026-10-19 00:50）：同 role＋同 id 新連線進來 → 舊連線以 4009 replaced 關閉（新的贏）；
//         用戶端收到 4009 不重連、直接結束並通知「同代號在別處登入」。
//   清理  每次有人連上、廣播或查狀態時，把超過 STALE_S（150 秒）沒有任何心跳或訊息的連線以 1001 stale 關掉（殭屍連線）。
//   停權  /admin/disable 之後，該用戶在線連線立刻關閉、之後不再轉送。
//   監看  GET /health?ch=<頻道> → 最後一則發送時間、在線接收端數、最近 1 小時訊號數。
//   管理  Authorization: Bearer RELAY_ADMIN_TOKEN：
//         POST /admin/user?ch=&id=     新增或重發該用戶 token（回 {"token":…}，只回這一次，中繼只存雜湊）
//         POST /admin/disable?ch=&id=  停權；POST /admin/enable?ch=&id= 復權；GET /admin/users?ch=  列用戶
//         POST /admin/reset?ch=        清掉已存訊號（發送端序號重新從 1 開始時用）；POST /admin/purge?ch= 整個頻道刪除（測試用）
//   訂閱控管（Evans 2026-10-18 20:40 派工第 1 項）：傳送端把所有策略都送上來；中繼依「用戶 → 訂閱清單」只轉送他訂的，
//         客戶改本機設定也拿不到沒訂的。規則（routing）：
//           停權 → 不送；不在服務期間（開始前／到期後）→ 不送；連續下單風控暫停的策略 → 不送；訂閱＝"*"（全部，給 Evans 自己的機器）→ 全送（含未上架）；
//           否則策略要「上架」而且在他的訂閱清單裡才送。補發（since）照同一規則過濾（序號會跳號，接收端只記最大序號，不受影響）。
//         新策略第一次送上來自動登記成「下架」，管理頁按上架才會送給一般客戶。舊用戶（升級前就有的）訂閱＝"*"；新用戶預設什麼都沒訂。
//         GET  /admin/state?ch=           用戶（訂閱、服務期間、在線、版本、最後對帳）＋策略（上下架、暫停、最後訊號、保留則數）＋開通碼＋風控參數
//         POST /admin/user?ch=&id=        新增或重發 token；body 可帶 {subs, start, exp, note, tg}
//         POST /admin/set?ch=&id=         改 {subs, start, exp, note, tg}；改成不在服務期間 → 在線連線踢掉
//         POST /admin/strategy?ch=&code=  {listed, name, paused:false＝解除風控暫停}；POST /admin/strategy_delete?ch=&code=
//         POST /admin/simulate?ch=        {strategy} → 每個用戶會不會收到、為什麼（不送任何東西）
//         GET  /admin/replay?ch=&id=&since=  這個用戶重連時會補到哪些序號
//         POST /admin/testpub?ch=test…    只限 test 開頭的測試頻道：送一則假訊號（Sig 不是真的，真接收端會以簽章不符拒單），回實際送給誰
//   11-01（【舊】總指揮第 2 項）：
//     a 服務期間：用戶 start／exp（"YYYY-MM-DD"＝台北那天整天；或 "YYYY-MM-DDTHH:MM" 台北時間）。不在期間或停用 → 不再轉送；
//       v=2 接收端以 4012 關閉（接收端顯示「服務期限已到，請聯絡營業員」＋TG），**不平倉**；到期前 3 天（每天 09:00 排程）TG 給 Evans 和客戶（用戶 tg＝客戶的 Telegram chat id）。
//     b 開通碼：POST /admin/invite?ch=&id=（body 同 /admin/user）產 8 碼（排除 0 O 1 I），一次性、24 小時有效；
//       GET /contracts?ch=&id=  Bearer＝該用戶 token → 本文＝ContractList.csv 原文、X-Gea-Sig＝W 的 ECDSA 簽章、X-Gea-Ver＝產表版本（11-01 補充三 3）
//       POST /redeem?ch=  {code} 不用 token → 回 {id, token, ch}，開通碼當場作廢（換 token 會踢掉舊連線）；錯太多次（每分鐘 20）回 429。
//     c 部位快照：每支策略最新一則「已轉送」的已簽章訊號（latest 表）；sub 帶 snap:1 時先送快照，接收端拿來對帳。
//     d 連續下單風控：同一策略 RISK_WIN 秒內部位變動超過 RISK_MAX 次（預設 60 秒 4 次，POST /admin/risk {max, win} 可調）→ 暫停轉送該策略＋TG Evans；
//       暫停中照樣存（序號連續、標 held），不廣播、不進快照、斷線補發也不補；管理頁按「解除暫停」才恢復：
//       解除時把該策略最新一則（暫停期間最後一則）當目標部位，送 {"ctl":"align","strat":…,"items":[原文]} 給有權收的 v2 接收端對齊（11-01 14:15 裁示：不逐筆補送）。
//     e 客戶端 TG：v=2 接收端送 {"tg":"文字"} → 中繼用 Worker secret TG_BOT_TOKEN 轉發給 Evans（TG_CHAT_ID）；客戶電腦不放 bot token。每人 10 分鐘最多 30 則。
//       接收端另送 {"hello":{"ver":…}}、{"recon":{"ok":true|false,"detail":…}}，管理頁顯示版本與最後對帳結果。
//     f 管理頁 GET /admin 或 /console（手機可看）：貼 RELAY_ADMIN_TOKEN 後操作。
//     免費方案 CPU 10ms：快照、計數都在 Durable Object 的 SQLite（每頻道一個），不掃 D1。
// 簽章金鑰只在兩端：中繼不驗簽、不改內容，只管轉送與補發。
import { DurableObject } from "cloudflare:workers";
import CONSOLE_HTML from "./console.html";
import CONTRACTS from "../contracts.json";
import VERSION from "../version.json";            // 11-01 18:35 第 4 項：下單機最新版號／下載網址／SHA256／更新說明＋W 的 ECDSA 簽章（ordermachine make_dist.py --release 產）        // 11-01 補充三 3：W 用 ordermachine/tools/contracts.py 產表＋簽章；部署時打包

const KEEP = 500;               // 每個頻道保留最近幾則
const MAX_BYTES = 8192;         // 單則訊號上限
const NAME_RE = /^[A-Za-z0-9_-]{1,40}$/;
const WHEN_RE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/;
const INVITE_ABC = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";   // 排除 0、O、1、I
const today = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);   // 台北日期
// 台北時間字串 → UTC 毫秒；日期（沒有時分）：end=true 取那天結束（隔天 00:00），否則那天 00:00
function tpMs(s, end) {
  if (!s) return null;
  const d = s.length === 10 ? s + "T00:00" : s;
  const ms = Date.parse(d + ":00+08:00");
  return Number.isFinite(ms) ? ms + (end && s.length === 10 ? 86400e3 : 0) : null;
}
// 不在服務期間的原因；null＝正常
function offWhy(u, now = Date.now()) {
  if (!u) return "沒有這個用戶";
  if (!u.enabled) return "停用";
  const s = tpMs(u.start, false), e = tpMs(u.exp, true);
  if (s && now < s) return "尚未開始（" + u.start + "）";
  if (e && now >= e) return "已到期（" + u.exp + "）";
  return null;
}
const expired = u => !!(u && tpMs(u.exp, true) && Date.now() >= tpMs(u.exp, true));

const J = (o, status = 200) => new Response(JSON.stringify(o), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

function bearer(req) {
  const h = req.headers.get("authorization") || "";
  return h.startsWith("Bearer ") ? h.slice(7).trim() : "";
}

function same(a, b) {            // 定時比較
  if (!a || !b || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function sha256(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}

function newToken() {
  const b = new Uint8Array(24);
  crypto.getRandomValues(b);
  return [...b].map(x => x.toString(16).padStart(2, "0")).join("");
}

function newInvite() {
  const b = new Uint8Array(8);
  crypto.getRandomValues(b);
  return [...b].map(x => INVITE_ABC[x & 31]).join("");          // 32 個字元 → 取低 5 位元，分布均勻
}

const PAGE_HEADERS = { "content-type": "text/html; charset=utf-8", "cache-control": "no-store",
  "x-robots-tag": "noindex", "x-frame-options": "DENY", "referrer-policy": "no-referrer" };

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    const ch = u.searchParams.get("ch") || "";
    if (u.pathname === "/") return J({ ok: true, name: "gea-signal-relay", paths: ["/ws", "/health", "/redeem", "/contracts", "/tg", "/version", "/admin", "/admin/*", "/console"] });
    if (u.pathname === "/console" || u.pathname === "/admin") return new Response(CONSOLE_HTML, { headers: PAGE_HEADERS });
    if (u.pathname === "/version") return new Response(JSON.stringify(VERSION), { headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });   // 不用 token：內容有簽章，客戶端驗簽才採用
    if (!["/ws", "/health", "/redeem", "/contracts", "/tg"].includes(u.pathname) && !u.pathname.startsWith("/admin/")) return J({ error: "not found" }, 404);
    if (!env.RELAY_PUB_TOKEN || !env.RELAY_ADMIN_TOKEN) return J({ error: "relay secrets not set" }, 503);
    if (!NAME_RE.test(ch)) return J({ error: "bad ch" }, 400);
    if (u.pathname.startsWith("/admin/") && !same(bearer(req), env.RELAY_ADMIN_TOKEN)) return J({ error: "unauthorized" }, 401);
    if (u.pathname === "/redeem" && req.method !== "POST") return J({ error: "POST only" }, 405);
    if (u.pathname === "/contracts" && (!bearer(req) || !NAME_RE.test(u.searchParams.get("id") || ""))) return J({ error: "unauthorized" }, 401);
    // 11-01 21:00 A2：客戶端沒連 WebSocket 的行程（設定精靈、GeaApiCheck）要給 Evans 的 TG → POST /tg?ch=&id=（客戶 token；跟 ws 的 tg 同一套限量）
    if (u.pathname === "/tg" && (req.method !== "POST" || !bearer(req) || !NAME_RE.test(u.searchParams.get("id") || ""))) return J({ error: "unauthorized" }, 401);
    if (u.pathname === "/ws") {
      if ((req.headers.get("upgrade") || "").toLowerCase() !== "websocket") return J({ error: "expected websocket" }, 426);
      const role = u.searchParams.get("role"), id = u.searchParams.get("id") || "";
      if (!["pub", "sub"].includes(role) || !NAME_RE.test(id)) return J({ error: "bad role or id" }, 400);
      if (role === "pub" && !same(bearer(req), env.RELAY_PUB_TOKEN)) return J({ error: "unauthorized" }, 401);
      if (role === "sub" && !bearer(req)) return J({ error: "unauthorized" }, 401);
    }
    const stub = env.RELAY.get(env.RELAY.idFromName(ch));
    return stub.fetch(req);
  },
  // 每小時：踢掉剛到期的在線連線；台北 09:00 那一班另外發到期前 3 天提醒
  async scheduled(ev, env, ctx) {
    for (const ch of String(env.RELAY_CHANNELS || "gea").split(",").map(x => x.trim()).filter(x => NAME_RE.test(x))) {
      const stub = env.RELAY.get(env.RELAY.idFromName(ch));
      ctx.waitUntil(stub.fetch("https://relay.internal/cron?ch=" + ch));
    }
  },
};

const STALE_S = 150;   // 用戶端每 30 秒 ping；150 秒＝連漏 4 次以上才算殭屍（測試可用 var RELAY_STALE_S 縮短）

export class Relay extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.env = env;
    this.sql = ctx.storage.sql;
    this.schema();
    this.dead = new WeakSet();
    this.tgRate = new Map();
    this.staleMs = (Number(env.RELAY_STALE_S) || STALE_S) * 1e3;
    // 心跳：自動回應，不喚醒 DO、不計 duration
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"));
  }

  schema() {
    this.sql.exec(`CREATE TABLE IF NOT EXISTS msgs(seq INTEGER PRIMARY KEY, rts INTEGER NOT NULL, body TEXT NOT NULL);
                   CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, th TEXT NOT NULL, enabled INTEGER NOT NULL, created INTEGER NOT NULL);
                   CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
                   CREATE TABLE IF NOT EXISTS strategies(code TEXT PRIMARY KEY, name TEXT, listed INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
                   CREATE TABLE IF NOT EXISTS latest(strat TEXT PRIMARY KEY, seq INTEGER NOT NULL, rts INTEGER NOT NULL, body TEXT NOT NULL);
                   CREATE TABLE IF NOT EXISTS risk(strat TEXT NOT NULL, ts INTEGER NOT NULL);
                   CREATE INDEX IF NOT EXISTS risk_i ON risk(strat, ts);
                   CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, id TEXT NOT NULL, created INTEGER NOT NULL, exp_ms INTEGER NOT NULL);`);
    // 10-18 20:40 升級：users 加訂閱、到期日、備註、最後連線；msgs 加策略欄（舊用戶訂閱＝"*"，照舊全收）
    // 11-01 升級：users 加開始、客戶 TG、版本、最後對帳、到期提醒；strategies 加風控暫停
    for (const [t, c] of [["users", "subs TEXT NOT NULL DEFAULT '*'"], ["users", "exp TEXT NOT NULL DEFAULT ''"], ["users", "note TEXT NOT NULL DEFAULT ''"],
                          ["users", "last_seen INTEGER"], ["msgs", "strat TEXT"],
                          ["users", "start TEXT NOT NULL DEFAULT ''"], ["users", "tg TEXT NOT NULL DEFAULT ''"], ["users", "ver TEXT"],
                          ["users", "recon TEXT"], ["users", "recon_at INTEGER"], ["users", "warned TEXT NOT NULL DEFAULT ''"],
                          ["strategies", "paused INTEGER NOT NULL DEFAULT 0"], ["strategies", "paused_at INTEGER"], ["strategies", "paused_why TEXT"],
                          ["msgs", "held INTEGER NOT NULL DEFAULT 0"]]) {
      if (!this.sql.exec(`PRAGMA table_info(${t})`).toArray().some(r => r.name === c.split(" ")[0])) this.sql.exec(`ALTER TABLE ${t} ADD COLUMN ${c}`);
    }
  }

  lastSeq() {
    const r = this.sql.exec("SELECT MAX(seq) AS m FROM msgs").one();
    return r.m == null ? Number(this.meta("floor") || 0) : r.m;
  }

  meta(k, v) {
    if (v === undefined) {
      const r = this.sql.exec("SELECT v FROM meta WHERE k=?", k).toArray();
      return r.length ? r[0].v : null;
    }
    this.sql.exec("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, String(v));
  }
  riskMax() { return Number(this.meta("risk_max")) || 4; }
  riskWin() { return Number(this.meta("risk_win")) || 60; }

  async tg(chat, text) {
    const tok = this.env.TG_BOT_TOKEN;
    if (!tok || !chat) return false;
    if (/^t\d+$/.test(this.chName || (this.chName = this.meta("ch") || ""))) { this.meta("tg_test_n", Number(this.meta("tg_test_n") || 0) + 1); return true; }   // 自動測試頻道 t<時間>：不真的發，只計數
    try {
      const r = await fetch(`https://api.telegram.org/bot${tok}/sendMessage`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ chat_id: chat, text: String(text).slice(0, 3500) }) });
      return r.ok;
    } catch (e) { return false; }
  }
  evans(text) { return this.tg(this.env.TG_CHAT_ID, "【下單中繼】" + text); }
  // 客戶端給 Evans 的通知（ws 的 tg 與 POST /tg 共用）：每個代號 10 分鐘最多 30 則
  async relayTg(id, text) {
    const now = Date.now(), L = (this.tgRate.get(id) || []).filter(t => now - t < 600e3);
    if (L.length >= 30) { if (L.length === 30) { L.push(now); this.tgRate.set(id, L); await this.evans(`客戶 ${id} 10 分鐘內通知超過 30 則，之後的先不轉發`); } return false; }
    L.push(now); this.tgRate.set(id, L);
    return await this.evans(`客戶 ${id}：${String(text || "").slice(0, 1500)}`);
  }

  // ── 路由規則：回 null＝會送；否則回不送的原因（keepPaused＝快照用：風控暫停不算，快照本來就只有暫停前的最新狀態）
  users() { return Object.fromEntries(this.sql.exec("SELECT * FROM users").toArray().map(r => [r.id, r])); }
  strats() { return Object.fromEntries(this.sql.exec("SELECT * FROM strategies").toArray().map(r => [r.code, r])); }
  why(user, strat, S, keepPaused) {
    const off = offWhy(user);
    if (off) return off;
    if (!keepPaused && S[strat] && S[strat].paused) return "連續下單風控暫停";
    if (user.subs === "*") return null;
    if (!S[strat] || !S[strat].listed) return "策略未上架";
    if (!user.subs.split(",").includes(strat)) return "沒訂閱";
    return null;
  }
  static stratOf(body) { try { return String(JSON.parse(body).Strategy || ""); } catch (e) { return ""; } }
  parseSubs(v) {
    if (v === "*" || (Array.isArray(v) && v.includes("*"))) return "*";
    if (!Array.isArray(v)) v = String(v || "").split(",");
    return v.map(x => String(x).trim()).filter(x => NAME_RE.test(x)).join(",");
  }
  // 最後活動時間：自動回應 ping 的時間（getWebSocketAutoResponseTimestamp）、最後訊息時間、連上時間取最晚
  lastAct(ws) {
    const a = ws.deserializeAttachment() || {}, t = this.ctx.getWebSocketAutoResponseTimestamp(ws);
    return Math.max(a.at || 0, a.rx || 0, t ? t.getTime() : 0);
  }
  sweep() {
    const now = Date.now(); let n = 0;
    for (const ws of this.ctx.getWebSockets()) if (now - this.lastAct(ws) > this.staleMs) { try { ws.close(1001, "stale"); } catch (e) { } this.dead.add(ws); n++; }
    return n;
  }
  live(tag) { return this.ctx.getWebSockets(tag).filter(ws => !this.dead.has(ws)); }   // 剛踢掉、還在關閉中的不算
  // 把這個用戶的在線連線關掉：新接收端（v=2）4012＝服務期限已到（不重連、不平倉）；舊接收端照舊 4003
  kick(id, why) {
    let n = 0;
    for (const ws of this.live("s:" + id)) {
      const a = ws.deserializeAttachment() || {};
      try { ws.close(a.v2 ? 4012 : 4003, a.v2 ? "service ended: " + why.replace(/[^\x20-\x7e]/g, "").slice(0, 60) : why === "停用" ? "disabled" : "expired"); } catch (e) { }
      this.dead.add(ws); n++;
    }
    return n;
  }
  // 風控解除：最新一則（含暫停期間）寫進快照，送 ctl:align 給有權收的 v2 接收端（舊接收端不認得 → 不送，下次連線的快照對帳會發現差異）
  align(strat) {
    const last = this.sql.exec("SELECT seq, body FROM msgs WHERE strat=? ORDER BY seq DESC LIMIT 1", strat).toArray()[0];
    if (!last) return { to: [], seq: null };
    this.sql.exec("INSERT INTO latest(strat, seq, rts, body) VALUES(?,?,?,?) ON CONFLICT(strat) DO UPDATE SET seq=excluded.seq, rts=excluded.rts, body=excluded.body",
                  strat, last.seq, Date.now(), last.body);
    this.sweep();
    const U = this.users(), S = this.strats(), to = [], msg = '{"ctl":"align","strat":"' + strat + '","items":[' + last.body + "]}";
    for (const s of this.live("sub")) {
      const a = s.deserializeAttachment() || {};
      if (a.v2 && this.why(U[a.id], strat, S) === null) { this.send(s, msg); to.push(a.id); }
    }
    return { to, seq: last.seq };
  }

  broadcast(data, strat) {
    this.sweep();
    const U = this.users(), S = this.strats(), to = [];
    let online = 0;
    for (const s of this.live("sub")) {
      online++;
      const a = s.deserializeAttachment() || {};
      if (this.why(U[a.id], strat, S) === null) { this.send(s, data); to.push(a.id); }
    }
    return { to, online };
  }

  state() {
    const swept = this.sweep(), now = Date.now();
    const conns = this.live().map(ws => { const a = ws.deserializeAttachment() || {};
      return { role: a.role, id: a.id, v2: !!a.v2, colo: a.colo || null, since: new Date(a.at || 0).toISOString(),
        idle_s: Math.round((now - this.lastAct(ws)) / 1000) }; });
    const online = {};
    for (const ws of this.live("sub")) { const a = ws.deserializeAttachment() || {}; online[a.id] = (online[a.id] || 0) + 1; }
    const stat = Object.fromEntries(this.sql.exec("SELECT strat, COUNT(*) AS n, MAX(rts) AS last FROM msgs GROUP BY strat").toArray().map(r => [r.strat, r]));
    const snap = Object.fromEntries(this.sql.exec("SELECT strat, seq, rts FROM latest").toArray().map(r => [r.strat, r]));
    return { today: today(), last_seq: this.lastSeq(), pubs_online: this.ctx.getWebSockets("pub").length,
      swept, conns, risk: { max: this.riskMax(), win: this.riskWin() },
      users: this.sql.exec("SELECT id, enabled, subs, start, exp, note, tg, ver, recon, recon_at, created, last_seen FROM users ORDER BY id").toArray()
        .map(r => ({ ...r, tg: r.tg ? "已設" : "", enabled: !!r.enabled, expired: expired(r), off: offWhy(r), online: online[r.id] || 0 })),
      strategies: this.sql.exec("SELECT * FROM strategies ORDER BY code").toArray()
        .map(r => ({ ...r, listed: !!r.listed, paused: !!r.paused, kept: stat[r.code] ? stat[r.code].n : 0, last: stat[r.code] ? stat[r.code].last : null,
          snap_seq: snap[r.code] ? snap[r.code].seq : null })),
      invites: this.sql.exec("SELECT code, id, exp_ms FROM invites WHERE exp_ms > ? ORDER BY exp_ms", now).toArray(),
      contracts_ver: CONTRACTS.ver, tg_test: Number(this.meta("tg_test_n") || 0) };
  }

  // 新增或改用戶欄位（/admin/user、/admin/set、/admin/invite 共用）；回錯誤字串或 null
  applyUser(id, body, qs) {
    for (const k of ["start", "exp"]) if (k in body && body[k] && !WHEN_RE.test(body[k])) return k + " 格式 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM";
    if ("tg" in body && body.tg && !/^-?\d{1,20}$/.test(String(body.tg))) return "tg 要是 Telegram chat id（數字）";
    if ("subs" in body || qs != null) this.sql.exec("UPDATE users SET subs=? WHERE id=?", "subs" in body ? this.parseSubs(body.subs) : this.parseSubs(qs === "*" ? "*" : qs.split(",")), id);
    if ("start" in body) this.sql.exec("UPDATE users SET start=? WHERE id=?", String(body.start || ""), id);
    if ("exp" in body) this.sql.exec("UPDATE users SET exp=?, warned='' WHERE id=?", String(body.exp || ""), id);
    if ("note" in body) this.sql.exec("UPDATE users SET note=? WHERE id=?", String(body.note).slice(0, 80), id);
    if ("tg" in body) this.sql.exec("UPDATE users SET tg=? WHERE id=?", String(body.tg || ""), id);
    return null;
  }

  async fetch(req) {
    const u = new URL(req.url), p = u.pathname, id = u.searchParams.get("id") || "";
    if (!this.chName && u.searchParams.get("ch")) { this.chName = u.searchParams.get("ch"); if (this.meta("ch") !== this.chName) this.meta("ch", this.chName); }
    if (p === "/ws") return this.accept(req, u.searchParams.get("role"), id, u.searchParams.get("v") === "2");
    if (p === "/cron") return this.cron();
    if (p === "/health") {
      const now = Date.now();
      const n1h = this.sql.exec("SELECT COUNT(*) AS n FROM msgs WHERE rts > ?", now - 3600e3).one().n;
      const last = this.sql.exec("SELECT seq, rts FROM msgs ORDER BY seq DESC LIMIT 1").toArray()[0];
      return J({ ch: u.searchParams.get("ch"), now: new Date(now).toISOString(),
        last_pub: last ? new Date(last.rts).toISOString() : null, last_seq: last ? last.seq : null,
        last_pub_age_s: last ? Math.round((now - last.rts) / 1000) : null,
        subs_online: this.ctx.getWebSockets("sub").length, pubs_online: this.ctx.getWebSockets("pub").length,
        signals_1h: n1h, stored: this.sql.exec("SELECT COUNT(*) AS n FROM msgs").one().n });
    }
    if (p === "/redeem") return this.redeem(req);
    if (p === "/tg") {
      const a = this.sql.exec("SELECT id, th FROM users WHERE id=?", u.searchParams.get("id")).toArray()[0];
      if (!a || !same(await sha256(bearer(req)), a.th)) return J({ error: "unauthorized" }, 401);
      let m; try { m = await req.json(); } catch (e) { return J({ error: "bad json" }, 400); }
      return J({ ok: await this.relayTg(a.id, m && m.tg) });
    }
    if (p === "/contracts") {                                                 // 只要 token 對就給（服務期間外也給：合約表不會下單，只是讓到期客戶續約後馬上能用）
      const r = this.sql.exec("SELECT th FROM users WHERE id=?", u.searchParams.get("id")).toArray()[0];
      if (!r || !same(await sha256(bearer(req)), r.th)) return J({ error: "unauthorized" }, 401);
      return new Response(CONTRACTS.csv, { headers: { "content-type": "text/csv; charset=utf-8", "cache-control": "no-store",
        "x-gea-sig": CONTRACTS.sig, "x-gea-ver": CONTRACTS.ver } });
    }
    // ── 管理端點（Worker 已驗 RELAY_ADMIN_TOKEN）
    if (p === "/admin/users") {
      return J({ users: this.sql.exec("SELECT id, enabled, created FROM users ORDER BY id").toArray()
        .map(r => ({ id: r.id, enabled: !!r.enabled, created: new Date(r.created).toISOString(),
          online: this.ctx.getWebSockets("s:" + r.id).length })) });
    }
    if (p === "/admin/state") return J({ ch: u.searchParams.get("ch"), ...this.state() });
    if (p === "/admin/replay") {
      const user = this.users()[id], S = this.strats(), since = Number(u.searchParams.get("since") || 0);
      const rows = this.sql.exec("SELECT seq, strat, body FROM msgs WHERE seq > ? ORDER BY seq", since).toArray();
      return J({ id, since, will: rows.filter(r => this.why(user, r.strat || Relay.stratOf(r.body), S) === null).map(r => r.seq),
        skipped: rows.filter(r => this.why(user, r.strat || Relay.stratOf(r.body), S) !== null).map(r => [r.seq, r.strat, this.why(user, r.strat || Relay.stratOf(r.body), S)]) });
    }
    if (req.method !== "POST") return J({ error: "POST only" }, 405);
    const body = await req.json().catch(() => ({})) || {};
    if (p === "/admin/strategy" || p === "/admin/strategy_delete") {
      const code = u.searchParams.get("code") || "";
      if (!NAME_RE.test(code)) return J({ error: "bad code" }, 400);
      if (p === "/admin/strategy_delete") return J({ ok: true, deleted: this.sql.exec("DELETE FROM strategies WHERE code=?", code).rowsWritten });
      this.sql.exec("INSERT INTO strategies(code, name, listed, created) VALUES(?,?,0,?) ON CONFLICT(code) DO NOTHING", code, code, Date.now());
      if ("listed" in body) this.sql.exec("UPDATE strategies SET listed=? WHERE code=?", body.listed ? 1 : 0, code);
      if ("name" in body) this.sql.exec("UPDATE strategies SET name=? WHERE code=?", String(body.name).slice(0, 40), code);
      let aligned = null;
      if ("paused" in body && !body.paused) {
        const was = this.sql.exec("SELECT paused FROM strategies WHERE code=?", code).one().paused;
        this.sql.exec("UPDATE strategies SET paused=0, paused_why=NULL WHERE code=?", code); this.sql.exec("DELETE FROM risk WHERE strat=?", code);
        if (was) aligned = this.align(code);
      }
      return J({ ok: true, strategy: this.sql.exec("SELECT * FROM strategies WHERE code=?", code).one(), aligned });
    }
    if (p === "/admin/risk") {
      const mx = Number(body.max), win = Number(body.win);
      if ("max" in body && !(Number.isInteger(mx) && mx >= 1 && mx <= 100)) return J({ error: "max 1～100" }, 400);
      if ("win" in body && !(Number.isInteger(win) && win >= 5 && win <= 3600)) return J({ error: "win 5～3600 秒" }, 400);
      if ("max" in body) this.meta("risk_max", mx);
      if ("win" in body) this.meta("risk_win", win);
      return J({ ok: true, risk: { max: this.riskMax(), win: this.riskWin() } });
    }
    if (p === "/admin/simulate") {
      const strat = String(body.strategy || ""), U = this.users(), S = this.strats();
      const on = {}; for (const ws of this.ctx.getWebSockets("sub")) on[(ws.deserializeAttachment() || {}).id] = true;
      return J({ strategy: strat, listed: !!(S[strat] && S[strat].listed), paused: !!(S[strat] && S[strat].paused),
        users: Object.values(U).map(x => { const w = this.why(x, strat, S); return { id: x.id, receive: w === null, why: w || (on[x.id] ? "在線，立刻收到" : "離線，上線後補發") }; }) });
    }
    if (p === "/admin/testpub") {
      if (!/^test/.test(u.searchParams.get("ch") || "")) return J({ error: "testpub 只限 test 開頭的測試頻道" }, 403);
      const strat = String(body.strategy || "");
      if (!NAME_RE.test(strat)) return J({ error: "bad strategy" }, 400);
      const seq = this.lastSeq() + 1;
      const data = JSON.stringify({ Seq: seq, TsMs: Date.now(), Strategy: strat, Raw: String(body.raw || "TEST"), Sig: "TEST-UNSIGNED" });
      this.store(seq, strat, data);
      return J({ ok: true, seq, ...this.broadcast(data, strat) });
    }
    if (p === "/admin/reset") {
      const n = this.sql.exec("SELECT COUNT(*) AS n FROM msgs").one().n;
      this.sql.exec("DELETE FROM msgs");
      this.meta("floor", 0);
      return J({ ok: true, deleted: n });
    }
    if (p === "/admin/purge") {
      for (const ws of this.ctx.getWebSockets()) ws.close(4010, "channel purged");
      await this.ctx.storage.deleteAll();
      this.schema();                                                          // 同一個實例清空後還會再用（測試頻道）
      return J({ ok: true });
    }
    if (!NAME_RE.test(id)) return J({ error: "bad id" }, 400);
    if (p === "/admin/user" || p === "/admin/invite") {
      const tok = newToken();
      const qs = u.searchParams.get("subs");                                  // 新用戶預設什麼都沒訂；body 或 ?subs= 可直接指定
      const isNew = !this.sql.exec("SELECT id FROM users WHERE id=?", id).toArray().length;
      if (isNew) this.sql.exec("INSERT INTO users(id, th, enabled, created, subs) VALUES(?,?,1,?,'')", id, await sha256(tok), Date.now());
      const bad = this.applyUser(id, body, qs);
      if (bad) { if (isNew) this.sql.exec("DELETE FROM users WHERE id=?", id); return J({ error: bad }, 400); }
      if (p === "/admin/invite") {                                            // 開通碼：token 等客戶用開通碼換（現有 token 不動）
        this.sql.exec("DELETE FROM invites WHERE id=? OR exp_ms < ?", id, Date.now());
        let code;
        do { code = newInvite(); } while (this.sql.exec("SELECT code FROM invites WHERE code=?", code).toArray().length);
        const exp = Date.now() + 24 * 3600e3;
        this.sql.exec("INSERT INTO invites(code, id, created, exp_ms) VALUES(?,?,?,?)", code, id, Date.now(), exp);
        return J({ ok: true, id, code, expires: new Date(exp).toISOString() });
      }
      this.sql.exec("UPDATE users SET th=?, enabled=1 WHERE id=?", await sha256(tok), id);
      for (const ws of this.ctx.getWebSockets("s:" + id)) ws.close(4003, "token reissued");   // 舊 token 的連線踢掉
      return J({ ok: true, id, token: tok });
    }
    if (p === "/admin/set") {
      const x = this.sql.exec("SELECT * FROM users WHERE id=?", id).toArray()[0];
      if (!x) return J({ error: "no such user" }, 404);
      const bad = this.applyUser(id, body, null);
      if (bad) return J({ error: bad }, 400);
      const y = this.sql.exec("SELECT * FROM users WHERE id=?", id).one();
      const off = offWhy(y);
      const kicked = off ? this.kick(id, off) : 0;
      return J({ ok: true, user: { id: y.id, subs: y.subs, start: y.start, exp: y.exp, note: y.note, enabled: !!y.enabled, off }, kicked });
    }
    if (p === "/admin/disable" || p === "/admin/enable") {
      const on = p === "/admin/enable" ? 1 : 0;
      const n = this.sql.exec("UPDATE users SET enabled=? WHERE id=?", on, id).rowsWritten;
      const kicked = on ? 0 : this.kick(id, "停用");
      return n ? J({ ok: true, id, enabled: !!on, kicked }) : J({ error: "no such user" }, 404);
    }
    return J({ error: "not found" }, 404);
  }

  // 開通碼換 token（不用登入）：一次性、24 小時；每分鐘錯 20 次以上先擋（防猜碼）
  async redeem(req) {
    const now = Date.now(), minute = Math.floor(now / 60e3);
    const fail = JSON.parse(this.meta("redeem_fail") || "[0,0]");
    if (fail[0] === minute && fail[1] >= 20) return J({ error: "嘗試太多次，請一分鐘後再試" }, 429);
    const body = await req.json().catch(() => ({})) || {};
    const code = String(body.code || "").toUpperCase().replace(/[^0-9A-Z]/g, "");
    const r = code.length === 8 ? this.sql.exec("SELECT * FROM invites WHERE code=?", code).toArray()[0] : null;
    if (!r || r.exp_ms < now) {
      this.meta("redeem_fail", JSON.stringify([minute, fail[0] === minute ? fail[1] + 1 : 1]));
      if (r) this.sql.exec("DELETE FROM invites WHERE code=?", code);
      return J({ error: r ? "開通碼已過期（24 小時），請營業員重新產生" : "開通碼不對（或已經用過），請核對 8 碼" }, 404);
    }
    this.sql.exec("DELETE FROM invites WHERE code=?", code);                 // 一次性：先作廢再發 token
    const user = this.sql.exec("SELECT * FROM users WHERE id=?", r.id).toArray()[0];
    if (!user) return J({ error: "這個開通碼的用戶已被刪除，請聯絡營業員" }, 404);
    const tok = newToken();
    this.sql.exec("UPDATE users SET th=? WHERE id=?", await sha256(tok), r.id);
    for (const ws of this.ctx.getWebSockets("s:" + r.id)) ws.close(4003, "token reissued");
    await this.evans(`客戶 ${r.id}（${user.note || "沒有備註"}）已用開通碼開通` + (body.ver ? `，接收端版本 ${String(body.ver).slice(0, 20)}` : ""));
    return J({ ok: true, id: r.id, token: tok, ch: new URL(req.url).searchParams.get("ch"), off: offWhy(user) });
  }

  // 每小時：踢掉不在服務期間的在線連線；台北 09 點那班：到期前 3 天（含）內、還沒提醒過這個到期日的 → TG Evans＋客戶
  async cron() {
    const now = Date.now(), hourTp = new Date(now + 8 * 3600e3).getUTCHours();
    let kicked = 0, warned = [];
    for (const x of Object.values(this.users())) {
      const off = offWhy(x, now);
      if (off) {
        const k = this.kick(x.id, off);
        kicked += k;
        if (k) await this.evans(`客戶 ${x.id}（${x.note || "沒有備註"}）${off} → 已停止轉送並關閉他的接收端連線（不平倉）。`);
        continue;
      }
      const e = tpMs(x.exp, true);
      if (hourTp === 9 && e && e - now <= 3 * 86400e3 && x.warned !== x.exp) {
        const days = Math.max(0, Math.ceil((e - now) / 86400e3));
        await this.evans(`客戶 ${x.id}（${x.note || "沒有備註"}）服務將於 ${x.exp} 到期（剩 ${days} 天）。到期後只停止送訊號，不會平倉。`);
        if (x.tg) await this.tg(x.tg, `GEA 跟單服務將於 ${x.exp} 到期（剩 ${days} 天）。到期後不再收到新訊號（不會自動平倉），續約請聯絡營業員。`);
        this.sql.exec("UPDATE users SET warned=? WHERE id=?", x.exp, x.id);
        warned.push(x.id);
      }
    }
    this.sql.exec("DELETE FROM invites WHERE exp_ms < ?", now);
    this.sql.exec("DELETE FROM risk WHERE ts < ?", now - 3600e3);
    return J({ ok: true, kicked, warned });
  }

  async accept(req, role, id, v2) {
    if (role === "sub") {
      const r = this.sql.exec("SELECT * FROM users WHERE id=?", id).toArray()[0];
      const th = await sha256(bearer(req));
      if (!r || !same(th, r.th)) return J({ error: "unauthorized" }, 401);
      const off = offWhy(r);
      if (off && !v2) return J({ error: r.enabled ? "expired" : "disabled" }, 403);   // 舊接收端：照舊 403（連 3 次就停）
      this.sql.exec("UPDATE users SET last_seen=? WHERE id=?", Date.now(), id);
      if (off) {                                                              // 新接收端：先接受再以 4012 關閉，讓它顯示「服務期限已到」而不是 token 錯
        if (this.meta("off_tg:" + id) !== today()) {                          // 每人每天只通知 Evans 一次
          this.meta("off_tg:" + id, today());
          await this.evans(`客戶 ${id}（${r.note || "沒有備註"}）接收端連線被擋：${off}。只停送訊號、不平倉；續約請到管理頁改到期日。`);
        }
        const pair = new WebSocketPair();
        pair[1].accept();
        pair[1].close(4012, "service ended: " + (r.enabled ? (tpMs(r.start, false) > Date.now() ? "not started" : "expired") : "disabled"));
        return new Response(null, { status: 101, webSocket: pair[0] });
      }
    }
    this.sweep();
    const tag = role[0] + ":" + id;
    for (const old of this.live(tag)) { try { old.close(4009, "replaced"); } catch (e) { } this.dead.add(old); }   // 同代號只留一條：新的贏
    const pair = new WebSocketPair();
    this.ctx.acceptWebSocket(pair[1], [role, tag]);
    pair[1].serializeAttachment({ role, id, v2: !!v2, at: Date.now(), colo: (req.cf && req.cf.colo) || null });
    return new Response(null, { status: 101, webSocket: pair[0] });
  }

  send(ws, o) { try { ws.send(typeof o === "string" ? o : JSON.stringify(o)); } catch (e) { /* 已斷線 */ } }

  async webSocketMessage(ws, data) {
    const a = ws.deserializeAttachment() || {};
    if (!a.rx || Date.now() - a.rx > 10e3) { a.rx = Date.now(); ws.serializeAttachment(a); }   // 最後訊息時間（10 秒內不重寫）
    if (typeof data !== "string") return this.send(ws, { ctl: "err", why: "text only" });
    if (data.length > MAX_BYTES) return this.send(ws, { ctl: "err", why: "too large" });
    let m;
    try { m = JSON.parse(data); } catch (e) { return this.send(ws, { ctl: "err", why: "not json" }); }
    if (!m || typeof m !== "object" || Array.isArray(m)) return this.send(ws, { ctl: "err", why: "not object" });

    if (a.role === "sub") return this.subMessage(ws, a, m);

    // ── 發送端：格式檢查（骨架 Signal：Seq 正整數、TsMs 數字、Sig 非空字串）
    const seq = m.Seq;
    if (!Number.isSafeInteger(seq) || seq <= 0) return this.send(ws, { ctl: "err", why: "Seq must be positive integer" });
    if (typeof m.TsMs !== "number" || !Number.isFinite(m.TsMs)) return this.send(ws, { ctl: "err", why: "TsMs must be number" });
    if (typeof m.Sig !== "string" || !m.Sig) return this.send(ws, { ctl: "err", why: "Sig missing" });
    if (seq <= this.lastSeq()) return this.send(ws, { ctl: "dup", seq, last: this.lastSeq() });
    const strat = NAME_RE.test(String(m.Strategy || "")) ? String(m.Strategy) : "";
    this.store(seq, strat, data);
    const paused = strat ? await this.riskCheck(strat) : false;
    if (paused) { this.sql.exec("UPDATE msgs SET held=1 WHERE seq=?", seq); return this.send(ws, { ctl: "ack", seq, subs: 0, online: this.live("sub").length, paused: true }); }
    if (strat) this.sql.exec("INSERT INTO latest(strat, seq, rts, body) VALUES(?,?,?,?) ON CONFLICT(strat) DO UPDATE SET seq=excluded.seq, rts=excluded.rts, body=excluded.body",
                             strat, seq, Date.now(), data);
    const b = this.broadcast(data, strat);
    this.send(ws, { ctl: "ack", seq, subs: b.to.length, online: b.online });
  }

  // 連續下單風控：回 true＝這支策略（已經或剛剛）暫停，這則不轉送
  async riskCheck(strat) {
    const S = this.sql.exec("SELECT paused FROM strategies WHERE code=?", strat).toArray()[0];
    if (S && S.paused) return true;
    const now = Date.now(), win = this.riskWin() * 1e3, mx = this.riskMax();
    this.sql.exec("INSERT INTO risk(strat, ts) VALUES(?,?)", strat, now);
    this.sql.exec("DELETE FROM risk WHERE strat=? AND ts < ?", strat, now - win);
    const n = this.sql.exec("SELECT COUNT(*) AS n FROM risk WHERE strat=?", strat).one().n;
    if (n <= mx) return false;
    const why = `${this.riskWin()} 秒內部位變動 ${n} 次（上限 ${mx}）`;
    this.sql.exec("UPDATE strategies SET paused=1, paused_at=?, paused_why=? WHERE code=?", now, why, strat);
    await this.evans(`⚠ 策略 ${strat} 連續下單風控觸發：${why} → 已暫停轉送給所有客戶。` +
                     `請確認訊號主機（例：同一策略掛在多張 MC 圖表），確認後到管理頁按「解除暫停」。暫停期間的訊號不會補送。`);
    return true;
  }

  async subMessage(ws, a, m) {
    if ("hello" in m) {
      const h = m.hello || {};
      this.sql.exec("UPDATE users SET ver=? WHERE id=?", String(h.ver || "").slice(0, 30), a.id);
      if (!a.v2) { a.v2 = true; ws.serializeAttachment(a); }
      return;
    }
    if ("recon" in m) {
      const r = m.recon || {};
      this.sql.exec("UPDATE users SET recon=?, recon_at=? WHERE id=?", (r.ok ? "✓ " : "✗ ") + String(r.detail || "").slice(0, 300), Date.now(), a.id);
      return;
    }
    if ("tg" in m) {                                                          // 客戶端要給 Evans 的通知：中繼用 Worker secret 轉發
      const ok = await this.relayTg(a.id, m.tg);
      if (m.ack) this.send(ws, { ctl: "tg", ok });
      return;
    }
    if (!("since" in m)) return this.send(ws, { ctl: "err", why: "sub can only send since/hello/recon/tg" });
    const since = Number(m.since);
    if (!Number.isFinite(since) || since < 0) return this.send(ws, { ctl: "err", why: "bad since" });
    const user = this.users()[a.id], S = this.strats();
    if (m.snap) {                                                             // 部位快照：每支策略最新一則已轉送的原文（他有權收的）
      const items = this.sql.exec("SELECT strat, body FROM latest ORDER BY strat").toArray()
        .filter(r => this.why(user, r.strat, S, true) === null).map(r => r.body);
      this.send(ws, '{"ctl":"snap","n":' + items.length + ',"items":[' + items.join(",") + "]}");
    }
    const rows = this.sql.exec("SELECT seq, strat, body FROM msgs WHERE seq > ? AND held=0 ORDER BY seq", since).toArray()
      .filter(r => this.why(user, r.strat || Relay.stratOf(r.body), S) === null);       // 只補他有權收的
    for (const r of rows) this.send(ws, r.body);
    const oldest = this.sql.exec("SELECT MIN(seq) AS m FROM msgs").one().m;
    // gap：要補的比保留的最舊一則還早（超過 500 則）→ 告訴接收端有缺，由接收端 Telegram 回報
    return this.send(ws, { ctl: "replayed", n: rows.length, last: this.lastSeq(),
      gap: oldest != null && since + 1 < oldest && since < this.lastSeq() ? [since + 1, oldest - 1] : null });
  }

  store(seq, strat, data) {
    this.sql.exec("INSERT INTO msgs(seq, rts, body, strat) VALUES(?,?,?,?)", seq, Date.now(), data, strat);
    this.sql.exec(`DELETE FROM msgs WHERE seq < (SELECT MIN(seq) FROM (SELECT seq FROM msgs ORDER BY seq DESC LIMIT ${KEEP}))`);
    this.meta("floor", seq);
    if (strat) this.sql.exec("INSERT INTO strategies(code, name, listed, created) VALUES(?,?,0,?) ON CONFLICT(code) DO NOTHING", strat, strat, Date.now());  // 新策略自動登記成下架
  }

  async webSocketClose(ws, code, reason) {
    try { ws.close(code, reason); } catch (e) { /* 已關 */ }
  }

  async webSocketError(ws) {
    try { ws.close(1011, "error"); } catch (e) { /* 已關 */ }
  }
}
