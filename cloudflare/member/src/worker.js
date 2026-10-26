// gea-member ── GEA 會員區 Worker（Evans 2026-10-18 17:05 派工「預覽轉正式」；設計見 CustomerServiceANDSales TODO 同日段）
//   · 會員登入：① GEA 給的專屬登入連結（/login?k=…，打開後按「進入」才建 session，避免 LINE 預覽機器人吃掉名額）
//               ② LINE Login（設了 LINE_CHANNEL_ID／LINE_CHANNEL_SECRET 才開；第一次要先用專屬連結登入、按「綁定 LINE」）
//   · 每個會員最多 3 個裝置同時登入（第 4 個登入時踢掉最舊的）；到期或停用 → 所有頁面與資料都拿不到。
//   · 網頁與資料都在 D1 的 files／file_chunks（文字檔存原文、圖片存 base64，切塊 ≤ 1 MB：D1 一列上限 2 MB；10-18 部署時 API token 沒有 KV 權限，改用 D1），只有有效會員拿得到；index.html 送出前塞入 window.GEA_ME（姓名、到期日、是否管理者）。
//   · 管理 API（Bearer ADMIN_TOKEN 或管理者 session）：會員增刪改、重發連結、踢裝置；檔案上傳／列表／刪除；策略上下架表。
//   · 訂閱（Evans 10-19「留給客戶的當然是照訂閱，沒訂的連訊號圖都不能看」）：members.subs＝訂閱的策略代碼（逗號分隔，"*"＝全部）；
//     data_s_<代碼>.js（該策略的交易與權益）只發給有訂閱的會員或管理者，data_adm_*（原型研究完整版）只發給管理者，其他人一律 403。
//   · 在新裝置登入（10-26 18:15 總指揮本機 3）：管理者按「在新裝置登入」→ 一次性登入連結＋QR 碼（/o?t=…，10 分鐘有效、用一次就失效），
//     手機掃了按「進入」就登入；本機 member_push.py --login-link 也能把連結推到 Evans 自己的 TG。管理者最多 MAX_SESS_ADMIN 台裝置。
//   · 會員自己的版面（10-26 19:15 總指揮本機 2）：prefs 表（會員 × 名稱），看盤區「儲存我的版面」PUT /api/prefs?k=watch；
//     送 index.html 時直接塞進 GEA_ME.prefs，任何裝置登入都載入同一份；沒存過才用預設。
//   · 登入連結與 session 只存 SHA-256 雜湊，資料庫外洩也拿不到可用的連結。
const COOKIE = "gea_s", LCOOKIE = "gea_ls", DAY = 86400, SESS_DAYS = 30, MAX_SESS = 3, MAX_SESS_ADMIN = 6, OTL_SEC = 600;
const enc = new TextEncoder();
const hex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
import qrcode from "./qrcode.js";
const rand = (n = 32) => hex(crypto.getRandomValues(new Uint8Array(n)));
const sha = async s => hex(await crypto.subtle.digest("SHA-256", typeof s === "string" ? enc.encode(s) : s));
const now = () => Math.floor(Date.now() / 1000);
const today = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);          // 台北日期
const SEC = {"x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "x-frame-options": "DENY", "x-robots-tag": "noindex, nofollow"};
const json = (o, st = 200, h = {}) => new Response(JSON.stringify(o), {status: st, headers: {"content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...SEC, ...h}});
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const cookie = (req, n) => { const m = (req.headers.get("cookie") || "").match(new RegExp("(?:^|;\\s*)" + n + "=([^;]+)")); return m ? m[1] : null; };
const setCookie = (n, v, age) => `${n}=${v}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${age}`;
const NAME_RE = /^[A-Za-z0-9_\-][A-Za-z0-9_.\-\/]{0,199}$/;

const SCHEMA = [
  "CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY, name TEXT NOT NULL, contact TEXT, exp TEXT NOT NULL, on_ INTEGER NOT NULL DEFAULT 1, admin INTEGER NOT NULL DEFAULT 0, key_hash TEXT UNIQUE, line_sub TEXT UNIQUE, created INTEGER, last_seen INTEGER)",
  "CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY, member_id TEXT NOT NULL, created INTEGER NOT NULL, last INTEGER NOT NULL, ua TEXT)",
  "CREATE INDEX IF NOT EXISTS sessions_member ON sessions(member_id, created)",
  "CREATE TABLE IF NOT EXISTS conf(name TEXT PRIMARY KEY, value TEXT NOT NULL, updated INTEGER)",
  "CREATE TABLE IF NOT EXISTS files(name TEXT PRIMARY KEY, ct TEXT, sha TEXT, size INTEGER, ts INTEGER, enc TEXT, chunks INTEGER)",
  "CREATE TABLE IF NOT EXISTS file_chunks(name TEXT NOT NULL, i INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(name, i))",
  "CREATE TABLE IF NOT EXISTS live(id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, data TEXT NOT NULL)",
  "CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0, poll INTEGER NOT NULL DEFAULT 0, push INTEGER NOT NULL DEFAULT 0)",   // 每天的請求數（UTC 日，跟 Cloudflare 額度同一天）
  "CREATE TABLE IF NOT EXISTS prefs(member_id TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY(member_id, k))",   // 會員版面（10-26）
  "CREATE TABLE IF NOT EXISTS otl(h TEXT PRIMARY KEY, member_id TEXT NOT NULL, exp INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0)",   // 一次性登入連結（10-26）：只存雜湊
  "CREATE TABLE IF NOT EXISTS livek(k TEXT PRIMARY KEY, ts INTEGER NOT NULL, data TEXT NOT NULL)",   // 訊號區／原型研究盤中即時（10-19 Evans）：s_<代碼>＝那支策略（照訂閱）、adm＝原型研究全部（只給管理者）   // 看盤區盤中即時（10-19 Evans）：本機 tools/live_push.py 每根新K推一次（gzip JSON，base64）
];

// ───────── 檔案（D1）：文字檔存原文（切 300,000 字，中文全形最多 0.9 MB）、其他存 base64（切 900,000 字）─────────
const isText = ct => /^text\/|^application\/(json|javascript)/.test(ct);
function b64(buf) { const u = new Uint8Array(buf); let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); }
function unb64(t) { const s = atob(t), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
async function filePut(env, name, buf, ct) {
  const text = isText(ct), str = text ? new TextDecoder().decode(buf) : b64(buf), step = text ? 300000 : 900000;
  const parts = []; for (let i = 0; i < str.length || i === 0; i += step) parts.push(str.slice(i, i + step));
  const meta = {ct, sha: await sha(buf), size: buf.byteLength, ts: now()};
  await env.DB.batch([
    env.DB.prepare("DELETE FROM file_chunks WHERE name = ?").bind(name),
    ...parts.map((d, i) => env.DB.prepare("INSERT INTO file_chunks(name, i, data) VALUES(?,?,?)").bind(name, i, d)),
    env.DB.prepare("INSERT INTO files(name, ct, sha, size, ts, enc, chunks) VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET ct = excluded.ct, sha = excluded.sha, size = excluded.size, ts = excluded.ts, enc = excluded.enc, chunks = excluded.chunks")
      .bind(name, ct, meta.sha, meta.size, meta.ts, text ? "t" : "b", parts.length),
  ]);
  return meta;
}
async function fileGet(env, name, metaOnly = false) {
  const m = await env.DB.prepare("SELECT * FROM files WHERE name = ?").bind(name).first();
  if (!m || metaOnly) return m ? {meta: m} : null;
  const r = await env.DB.prepare("SELECT data FROM file_chunks WHERE name = ? ORDER BY i").bind(name).all();
  const str = r.results.map(x => x.data).join("");
  return {meta: m, body: m.enc === "t" ? str : unb64(str)};
}
let ready = false;
async function init(env) {
  if (ready) return;
  await env.DB.batch(SCHEMA.map(s => env.DB.prepare(s)));
  const cols = (await env.DB.prepare("PRAGMA table_info(members)").all()).results.map(c => c.name);
  if (!cols.includes("subs")) await env.DB.prepare("ALTER TABLE members ADD COLUMN subs TEXT NOT NULL DEFAULT ''").run();   // 10-19 加：舊會員預設沒訂閱
  ready = true;
}
const PREF_K = /^[a-z0-9_]{1,30}$/;
const LIVE_K = /^(adm|tick|s_[A-Za-z0-9_]{1,40})$/;   // tick＝形成中那根（逐筆跳，10-19；所有會員）
const SUB_RE = /^(\*|[A-Za-z0-9_]{1,40}(,[A-Za-z0-9_]{1,40}){0,49})?$/;
const subsOf = s => s.admin === 1 ? ["*"] : String(s.subs || "").split(",").filter(Boolean);
function canFile(s, name) {                                                       // 依訂閱擋檔：策略資料看訂閱、原型研究完整版只給管理者
  if (s.admin === 1) return true;
  if (name.startsWith("data_adm_")) return false;
  const m = name.match(/^data_s_([A-Za-z0-9_]+)\.js$/);
  if (m) { const a = subsOf(s); return a.includes("*") || a.includes(m[1]); }
  return true;
}

// ───────── 頁面（登入、到期、錯誤）─────────
function page(title, body, st = 200, h = {}) {
  return new Response(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>${esc(title)}</title>
<style>:root{--bg:#07090c;--panel:#121821;--line:#26303d;--tx:#d5dde7;--mut:#8593a3;--acc:#f0b429}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;background:radial-gradient(circle at 30% 20%,#1d2633,var(--bg));color:var(--tx);font:15px/1.6 "Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif}
.box{width:420px;max-width:100%;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:26px}h1{margin:0 0 4px;font-size:22px;color:var(--acc)}.note{font-size:13px;color:var(--mut)}
.btn{display:block;width:100%;padding:12px;border:none;border-radius:8px;font-weight:700;font-size:15px;margin-top:14px;text-align:center;text-decoration:none;cursor:pointer;font-family:inherit}.line{background:#06c755;color:#fff}.go{background:var(--acc);color:#111}.err{color:#ff6b6b}</style></head>
<body><div class="box"><h1>GEA 量化交易 會員區</h1>${body}</div></body></html>`, {status: st, headers: {"content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...SEC, ...h}});
}
function loginPage(env, msg = "", st = 200) {
  const line = env.LINE_CHANNEL_ID && env.LINE_CHANNEL_SECRET;
  return page("GEA 會員登入", `<div class="note">看盤區、訊號區、程式績效只開放給付費會員。</div>
${msg ? `<p class="err">${msg}</p>` : ""}
${line ? `<a class="btn line" href="/auth/line">用 LINE 登入</a><div class="note" style="margin-top:6px">第一次請先用 GEA 給你的專屬登入連結進入，再按右上角「綁定 LINE」，之後就能直接用 LINE 登入。</div>`
       : `<p>請用 GEA 給你的<b>專屬登入連結</b>進入。</p>`}
<div class="note" style="margin-top:16px;border-top:1px solid var(--line);padding-top:10px">連結遺失、換手機或會員到期，請聯絡 GEA。</div>`, st);
}
const expiredPage = m => page("GEA 會員已到期", `<p class="err"><b>${m.on_ ? "會員已到期" : "會員已停用"}</b>${m.on_ ? `（到期日 ${esc(m.exp)}）` : ""}。</p><p class="note">續約後由 GEA 延長到期日，重新整理就能進入。</p><a class="btn go" href="/logout">回登入畫面</a>`, 403);

// ───────── 身分 ─────────
const valid = m => m && m.on_ === 1 && m.exp >= today();
async function session(req, env) {
  const sid = cookie(req, COOKIE); if (!sid || !/^[0-9a-f]{64}$/.test(sid)) return null;
  const r = await env.DB.prepare("SELECT s.sid, s.created AS s_created, s.last AS s_last, m.* FROM sessions s JOIN members m ON m.id = s.member_id WHERE s.sid = ?").bind(await sha(sid)).first();
  if (!r) return null;
  const t = now();
  if (t - r.s_created > SESS_DAYS * DAY) { await env.DB.prepare("DELETE FROM sessions WHERE sid = ?").bind(r.sid).run(); return null; }
  if (t - r.s_last > 600) await env.DB.batch([env.DB.prepare("UPDATE sessions SET last = ? WHERE sid = ?").bind(t, r.sid), env.DB.prepare("UPDATE members SET last_seen = ? WHERE id = ?").bind(t, r.id)]);
  return r;
}
async function newSession(env, req, m, to = "/") {
  const sid = rand(), h = await sha(sid), t = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO sessions(sid, member_id, created, last, ua) VALUES(?,?,?,?,?)").bind(h, m.id, t, t, (req.headers.get("user-agent") || "").slice(0, 160)),
    env.DB.prepare("DELETE FROM sessions WHERE member_id = ? AND sid NOT IN (SELECT sid FROM sessions WHERE member_id = ? ORDER BY created DESC LIMIT ?)").bind(m.id, m.id, m.admin === 1 ? MAX_SESS_ADMIN : MAX_SESS),
    env.DB.prepare("UPDATE members SET last_seen = ? WHERE id = ?").bind(t, m.id),
  ]);
  return new Response(null, {status: 302, headers: {location: to, "set-cookie": setCookie(COOKIE, sid, SESS_DAYS * DAY), "cache-control": "no-store", ...SEC}});
}
function same(a, b) { if (!a || !b || a.length !== b.length) return false; let x = 0; for (let i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i); return x === 0; }
async function isAdmin(req, env, s) {
  const a = req.headers.get("authorization") || "";
  if (a.startsWith("Bearer ") && env.ADMIN_TOKEN && same(a.slice(7), env.ADMIN_TOKEN)) return true;
  if (s === undefined) s = await session(req, env);
  return !!(s && valid(s) && s.admin === 1 && (req.method === "GET" || (req.headers.get("content-type") || "").startsWith("application/json") || req.headers.get("x-gea") === "1"));
}

// ───────── LINE Login（OpenID Connect）─────────
async function lineStart(req, env, url) {
  if (!(env.LINE_CHANNEL_ID && env.LINE_CHANNEL_SECRET)) return loginPage(env, "LINE 登入尚未開通。", 404);
  let mode = "l";
  if (url.searchParams.get("bind") === "1") { const s = await session(req, env); if (!s || !valid(s)) return loginPage(env, "請先登入再綁定 LINE。", 401); mode = "b"; }
  const st = rand(16);
  const q = new URLSearchParams({response_type: "code", client_id: env.LINE_CHANNEL_ID, redirect_uri: url.origin + "/auth/line/cb", state: st, scope: "openid profile"});
  return new Response(null, {status: 302, headers: {location: "https://access.line.me/oauth2/v2.1/authorize?" + q, "set-cookie": setCookie(LCOOKIE, mode + st, 600), "cache-control": "no-store"}});
}
async function lineCallback(req, env, url) {
  if (!(env.LINE_CHANNEL_ID && env.LINE_CHANNEL_SECRET)) return loginPage(env, "LINE 登入尚未開通。", 404);
  const c = cookie(req, LCOOKIE) || "", code = url.searchParams.get("code"), st = url.searchParams.get("state");
  if (!code || !st || !same(c.slice(1), st)) return loginPage(env, "LINE 登入逾時或來源不符，請再試一次。", 400);
  const tok = await fetch("https://api.line.me/oauth2/v2.1/token", {method: "POST", headers: {"content-type": "application/x-www-form-urlencoded"},
    body: new URLSearchParams({grant_type: "authorization_code", code, redirect_uri: url.origin + "/auth/line/cb", client_id: env.LINE_CHANNEL_ID, client_secret: env.LINE_CHANNEL_SECRET})}).then(r => r.json()).catch(() => ({}));
  if (!tok.id_token) return loginPage(env, "LINE 登入失敗（取不到身分），請再試一次。", 502);
  const v = await fetch("https://api.line.me/oauth2/v2.1/verify", {method: "POST", headers: {"content-type": "application/x-www-form-urlencoded"},
    body: new URLSearchParams({id_token: tok.id_token, client_id: env.LINE_CHANNEL_ID})}).then(r => r.json()).catch(() => ({}));
  if (!v.sub) return loginPage(env, "LINE 身分驗證失敗，請再試一次。", 502);
  const clear = setCookie(LCOOKIE, "", 0);
  if (c[0] === "b") {
    const s = await session(req, env); if (!s || !valid(s)) return loginPage(env, "請先登入再綁定 LINE。", 401);
    const other = await env.DB.prepare("SELECT id FROM members WHERE line_sub = ? AND id <> ?").bind(v.sub, s.id).first();
    if (other) return page("綁定失敗", `<p class="err">這個 LINE 帳號已綁定別的會員。</p><a class="btn go" href="/">回會員區</a>`, 409, {"set-cookie": clear});
    await env.DB.prepare("UPDATE members SET line_sub = ? WHERE id = ?").bind(v.sub, s.id).run();
    return new Response(null, {status: 302, headers: {location: "/#bound", "set-cookie": clear}});
  }
  const m = await env.DB.prepare("SELECT * FROM members WHERE line_sub = ?").bind(v.sub).first();
  if (!m) return loginPage(env, "這個 LINE 帳號還沒綁定會員。請先用 GEA 給你的專屬登入連結進入，再按「綁定 LINE」。", 403);
  if (!valid(m)) return expiredPage(m);
  return newSession(env, req, m);
}

// ───────── 請求數（總指揮 2026-10-19 11:15 本機段 4：Workers 免費額度每天 10 萬次，UTC 00:00＝台灣 08:00 歸零）─────────
//   記在記憶體、每 20 次或 30 秒併一次寫進 D1（isolate 被回收時沒寫進去的會少算，管理頁寫「約」）；poll＝/api/live 輪詢、push＝live_push 上傳。
const USE = {d: "", n: 0, poll: 0, push: 0, at: 0};
const flushUse = (env, u) => env.DB.prepare("INSERT INTO usage(day, n, poll, push) VALUES(?, ?, ?, ?) ON CONFLICT(day) DO UPDATE SET n = n + excluded.n, poll = poll + excluded.poll, push = push + excluded.push")
  .bind(u.d, u.n, u.poll, u.push).run().catch(() => {});
function countUse(env, ctx, path) {
  const d = new Date().toISOString().slice(0, 10), now = Date.now(), later = p => ctx && ctx.waitUntil ? ctx.waitUntil(p) : p;
  const take = () => { const u = {...USE}; USE.n = USE.poll = USE.push = 0; USE.at = now; return u; };
  if (USE.d && USE.d !== d && USE.n) later(flushUse(env, take()));
  USE.d = d; USE.n++;
  if (path === "/api/live") USE.poll++; else if (path === "/api/admin/live") USE.push++;
  if (!USE.at) USE.at = now;
  if (USE.n >= 20 || now - USE.at > 30000) later(flushUse(env, take()));
}

// ───────── 管理 API ─────────
function qrSvg(text) {
  const q = qrcode(0, "M"); q.addData(text); q.make();
  return q.createSvgTag({cellSize: 6, margin: 4, scalable: true});
}
async function adminApi(req, env, url, path) {
  const db = env.DB;
  if (path === "/api/admin/otl" && req.method === "POST") {                       // 一次性登入連結＋QR（10 分鐘、用一次就失效）
    const b = await req.json().catch(() => ({}));
    const m = await db.prepare("SELECT * FROM members WHERE id = ?").bind(b.id || "").first(); if (!m) return json({error: "沒有這個會員"}, 404);
    if (!valid(m)) return json({error: "會員已到期或停用"}, 403);
    const t = rand(24), exp = now() + OTL_SEC;
    await db.batch([db.prepare("DELETE FROM otl WHERE exp < ? OR used = 1").bind(now()), db.prepare("INSERT INTO otl(h, member_id, exp) VALUES(?,?,?)").bind(await sha(t), m.id, exp)]);
    const link = url.origin + "/o?t=" + t;
    return json({id: m.id, link, exp, qr: qrSvg(link)});
  }
  if (path === "/api/admin/members") {
    if (req.method === "GET") {
      const r = await db.prepare("SELECT m.id, m.name, m.contact, m.exp, m.on_, m.admin, m.line_sub IS NOT NULL AS line, m.subs, m.created, m.last_seen, (SELECT COUNT(*) FROM sessions s WHERE s.member_id = m.id) AS devices FROM members m ORDER BY m.created").all();
      return json({today: today(), members: r.results});
    }
    const b = await req.json().catch(() => ({}));
    if (req.method === "POST") {
      if (!b.name || !/^\d{4}-\d{2}-\d{2}$/.test(b.exp || "")) return json({error: "姓名、到期日（YYYY-MM-DD）必填"}, 400);
      if (b.subs != null && !SUB_RE.test(String(b.subs))) return json({error: "訂閱格式：策略代碼用逗號分隔，或 *＝全部"}, 400);
      const id = rand(6), key = rand(24);
      await db.prepare("INSERT INTO members(id, name, contact, exp, on_, admin, key_hash, created, subs) VALUES(?,?,?,?,1,?,?,?,?)").bind(id, String(b.name).slice(0, 60), String(b.contact || "").slice(0, 120), b.exp, b.admin ? 1 : 0, await sha(key), now(), String(b.subs || "")).run();
      return json({id, link: url.origin + "/login?k=" + key});
    }
    if (req.method === "PATCH") {
      const m = await db.prepare("SELECT * FROM members WHERE id = ?").bind(b.id || "").first(); if (!m) return json({error: "沒有這個會員"}, 404);
      const st = [], out = {id: m.id};
      if (b.name != null) st.push(db.prepare("UPDATE members SET name = ? WHERE id = ?").bind(String(b.name).slice(0, 60), m.id));
      if (b.contact != null) st.push(db.prepare("UPDATE members SET contact = ? WHERE id = ?").bind(String(b.contact).slice(0, 120), m.id));
      if (b.exp != null) { if (!/^\d{4}-\d{2}-\d{2}$/.test(b.exp)) return json({error: "到期日格式 YYYY-MM-DD"}, 400); st.push(db.prepare("UPDATE members SET exp = ? WHERE id = ?").bind(b.exp, m.id)); }
      if (b.on != null) st.push(db.prepare("UPDATE members SET on_ = ? WHERE id = ?").bind(b.on ? 1 : 0, m.id));
      if (b.admin != null) st.push(db.prepare("UPDATE members SET admin = ? WHERE id = ?").bind(b.admin ? 1 : 0, m.id));
      if (b.subs != null) { if (!SUB_RE.test(String(b.subs))) return json({error: "訂閱格式：策略代碼用逗號分隔，或 *＝全部"}, 400); st.push(db.prepare("UPDATE members SET subs = ? WHERE id = ?").bind(String(b.subs), m.id)); }
      if (b.unbindLine) st.push(db.prepare("UPDATE members SET line_sub = NULL WHERE id = ?").bind(m.id));
      if (b.rotate) { const key = rand(24); st.push(db.prepare("UPDATE members SET key_hash = ? WHERE id = ?").bind(await sha(key), m.id)); out.link = url.origin + "/login?k=" + key; }
      if (b.kick || b.rotate) st.push(db.prepare("DELETE FROM sessions WHERE member_id = ?").bind(m.id));
      if (st.length) await db.batch(st);
      return json(out);
    }
    if (req.method === "DELETE") {
      const id = url.searchParams.get("id") || "";
      await db.batch([db.prepare("DELETE FROM sessions WHERE member_id = ?").bind(id), db.prepare("DELETE FROM prefs WHERE member_id = ?").bind(id), db.prepare("DELETE FROM members WHERE id = ?").bind(id)]);
      return json({deleted: id});
    }
  }
  if (path === "/api/admin/file") {
    const name = url.searchParams.get("name") || "";
    if (!NAME_RE.test(name) || name.includes("..")) return json({error: "檔名不合法"}, 400);
    if (req.method === "PUT") {
      const buf = await req.arrayBuffer();
      if (buf.byteLength > 24 * 1024 * 1024) return json({error: "檔案超過 24 MB"}, 413);
      const meta = await filePut(env, name, buf, req.headers.get("x-ct") || "application/octet-stream");
      return json({name, ...meta});
    }
    if (req.method === "DELETE") { await env.DB.batch([env.DB.prepare("DELETE FROM file_chunks WHERE name = ?").bind(name), env.DB.prepare("DELETE FROM files WHERE name = ?").bind(name)]); return json({deleted: name}); }
  }
  if (path === "/api/admin/live" && req.method === "PUT") {
    const buf = await req.arrayBuffer();
    if (buf.byteLength > 1400 * 1024) return json({error: "即時資料超過 1.4 MB"}, 413);
    const ts = Date.now(), k = url.searchParams.get("k");
    if (k != null) {
      if (!LIVE_K.test(k)) return json({error: "k 只收 s_<代碼>、adm 或 tick"}, 400);
      await env.DB.prepare("INSERT INTO livek(k, ts, data) VALUES(?, ?, ?) ON CONFLICT(k) DO UPDATE SET ts = excluded.ts, data = excluded.data").bind(k, ts, b64(buf)).run();
      return json({k, ts, size: buf.byteLength});
    }
    await env.DB.prepare("INSERT INTO live(id, ts, data) VALUES(1, ?, ?) ON CONFLICT(id) DO UPDATE SET ts = excluded.ts, data = excluded.data").bind(ts, b64(buf)).run();
    return json({ts, size: buf.byteLength});
  }
  if (path === "/api/admin/usage" && req.method === "GET") {                 // 最近 14 天的請求數＋這個 isolate 還沒寫進去的
    const r = await env.DB.prepare("SELECT day, n, poll, push FROM usage ORDER BY day DESC LIMIT 14").all();
    return json({days: r.results, pending: {day: USE.d, n: USE.n}, limit: 100000, tz: "UTC"});
  }
  if (path === "/api/admin/files" && req.method === "GET") {
    const r = await env.DB.prepare("SELECT name, ct, sha, size, ts, chunks FROM files ORDER BY name").all();
    return json({files: r.results});
  }
  if (path === "/api/admin/strategies" && req.method === "PUT") {
    const b = await req.json().catch(() => null);
    if (Array.isArray(b) && b.length === 0) { await env.DB.prepare("DELETE FROM conf WHERE name = 'strategies'").run(); return json({saved: 0, reset: true}); }   // 空陣列＝回到網頁內建預設
    if (!Array.isArray(b) || b.length > 100 || b.some(s => !s || typeof s.id !== "string" || !/^[A-Za-z0-9_]{1,40}$/.test(s.id))) return json({error: "格式：[{id, name, side, solo, combo, on}]"}, 400);
    const clean = b.map(s => ({id: s.id, name: String(s.name || s.id).slice(0, 40), side: String(s.side || "").slice(0, 8), solo: !!s.solo, combo: !!s.combo, on: !!s.on, note: String(s.note || "").slice(0, 120), ...(s.stats && typeof s.stats === "object" ? {stats: Object.fromEntries(["net","mdd","mar","pf","payoff","win","trades","expectancy"].filter(k => Number.isFinite(s.stats[k])).map(k => [k, s.stats[k]]))} : {})}));
    await env.DB.prepare("INSERT INTO conf(name, value, updated) VALUES('strategies', ?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated = excluded.updated").bind(JSON.stringify(clean), now()).run();
    return json({saved: clean.length});
  }
  if (path === "/api/admin/prices" && req.method === "PUT") {   // 客戶選單價格（Evans 10-19：還在定價，要能在管理頁隨時改，不寫死）：{strat:{代碼:年費}, infra:{編號:年費}, pack:{套餐名稱:年費}}
    const b = await req.json().catch(() => null);
    const ok = o => o && typeof o === "object" && !Array.isArray(o) && Object.keys(o).length <= 200 && Object.entries(o).every(([k, v]) => k.length <= 80 && Number.isInteger(v) && v >= 0 && v <= 1e8);
    if (!b || typeof b !== "object" || !["strat", "infra", "pack"].every(k => b[k] == null || ok(b[k]))) return json({error: "格式：{strat:{代碼:年費}, infra:{編號:年費}, pack:{名稱:年費}}，年費是 0 以上的整數"}, 400);
    const clean = {strat: b.strat || {}, infra: b.infra || {}, pack: b.pack || {}};
    const n = Object.keys(clean.strat).length + Object.keys(clean.infra).length + Object.keys(clean.pack).length;
    if (!n) { await env.DB.prepare("DELETE FROM conf WHERE name = 'prices'").run(); return json({saved: 0, reset: true}); }   // 全空＝回到報價單原價
    await env.DB.prepare("INSERT INTO conf(name, value, updated) VALUES('prices', ?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated = excluded.updated").bind(JSON.stringify(clean), now()).run();
    return json({saved: n});
  }
  if (path === "/api/admin/packages" && req.method === "PUT") { // 管理者可調整套餐名稱、內容與年費
    const b = await req.json().catch(() => null);
    if (!Array.isArray(b) || b.length > 30 || b.some(p => !p || !/^[A-Za-z0-9_]{1,40}$/.test(p.id || "") || typeof p.name !== "string" || !p.name.trim() || p.name.length > 60 || typeof p.desc !== "string" || p.desc.length > 400 || !Array.isArray(p.codes) || p.codes.length < 1 || p.codes.length > 40 || p.codes.some(c => typeof c !== "string" || !/^[A-Za-z0-9_]{1,40}$/.test(c)) || new Set(p.codes).size !== p.codes.length || !Number.isInteger(p.year) || p.year < 0 || p.year > 1e8)) return json({error: "套餐格式錯誤：需包含代號、名稱、說明、策略代碼與年費"}, 400);
    if (new Set(b.map(p => p.id)).size !== b.length) return json({error:"套餐代號不可重複"},400);
    if (b.length === 0) { await env.DB.prepare("DELETE FROM conf WHERE name = 'packages'").run(); return json({saved:0,reset:true}); }
    const clean = b.map(p => ({id:p.id, name:p.name.trim(), desc:p.desc.trim(), codes:p.codes, year:p.year}));
    await env.DB.prepare("INSERT INTO conf(name, value, updated) VALUES('packages', ?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated = excluded.updated").bind(JSON.stringify(clean), now()).run();
    return json({saved: clean.length});
  }
  return json({error: "沒有這個管理功能"}, 404);
}

// ───────── 發檔（只給有效會員）─────────
async function serveFile(req, env, s, name) {
  if (!canFile(s, name)) return new Response("沒有訂閱這個策略", {status: 403, headers: {"cache-control": "no-store", ...SEC}});
  const etag0 = req.headers.get("if-none-match");
  const r = await fileGet(env, name, !!etag0 && name !== "index.html");            // 帶 ETag 來的先只查 meta，沒變就 304、不讀內容
  if (r && etag0 && !r.body) { if (etag0 === `"${r.meta.sha}"`) return new Response(null, {status: 304, headers: {etag: etag0, "cache-control": "private, no-cache", ...SEC}}); return serveFile(new Request(req.url, {headers: {cookie: req.headers.get("cookie") || ""}}), env, s, name); }
  if (!r) return name === "index.html" ? page("GEA 會員區", "<p>網站資料準備中，請稍後再來。</p>", 503) : new Response("找不到", {status: 404, headers: SEC});
  const m = r.meta;
  if (name === "index.html") {
    const pr = {}; for (const x of (await env.DB.prepare("SELECT k, v FROM prefs WHERE member_id = ?").bind(s.id).all()).results) { try { pr[x.k] = JSON.parse(x.v); } catch (e) {} }
    const me = JSON.stringify({id: s.id, name: s.name, exp: s.exp, admin: s.admin === 1, subs: subsOf(s), line: !!s.line_sub, lineOn: !!(env.LINE_CHANNEL_ID && env.LINE_CHANNEL_SECRET), prefs: pr}).replace(/</g, "\\u003c");
    return new Response(r.body.replace("<!--GEA_ME-->", `<script>window.GEA_ME=${me};</script>`), {headers: {"content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...SEC}});
  }
  const etag = m.sha ? `"${m.sha}"` : null;
  if (etag && req.headers.get("if-none-match") === etag) return new Response(null, {status: 304, headers: {etag, "cache-control": "private, no-cache", ...SEC}});
  return new Response(r.body, {headers: {"content-type": m.ct || "application/octet-stream", "cache-control": "private, no-cache", ...(etag ? {etag} : {}), ...SEC}});
}

export default {
  async fetch(req, env, ctx) {
    await init(env);
    const url = new URL(req.url), path = url.pathname;
    countUse(env, ctx, path);
    try {
      if (path === "/login") {
        if (req.method === "GET") {                                                   // 只顯示按鈕；按下才建 session（預覽機器人不會按）
          const k = url.searchParams.get("k") || "";
          if (!/^[0-9a-f]{48}$/.test(k)) return loginPage(env, "登入連結不完整，請整段複製 GEA 給你的連結。", 400);
          return page("GEA 會員登入", `<form method="post" action="/login"><input type="hidden" name="k" value="${esc(k)}"><button class="btn go" type="submit">進入會員區</button></form><div class="note" style="margin-top:10px">這是你的專屬連結，請勿轉傳；同一帳號最多 ${MAX_SESS} 台裝置同時登入。</div>`);
        }
        if (req.method === "POST") {
          const k = String((await req.formData().catch(() => null))?.get("k") || "");
          const m = /^[0-9a-f]{48}$/.test(k) ? await env.DB.prepare("SELECT * FROM members WHERE key_hash = ?").bind(await sha(k)).first() : null;
          if (!m) return loginPage(env, "登入連結無效或已更換，請向 GEA 索取新連結。", 403);
          if (!valid(m)) return expiredPage(m);
          return newSession(env, req, m);
        }
      }
      if (path === "/o") {                                                          // 一次性登入：GET 只顯示按鈕（預覽機器人不會按），POST 才用掉
        const t = req.method === "POST" ? String((await req.formData().catch(() => null))?.get("t") || "") : url.searchParams.get("t") || "";
        if (!/^[0-9a-f]{48}$/.test(t)) return loginPage(env, "一次性登入連結不完整。", 400);
        const h = await sha(t), o = await env.DB.prepare("SELECT * FROM otl WHERE h = ?").bind(h).first();
        if (!o || o.used || o.exp < now()) return loginPage(env, "這個一次性登入連結已用過或已過期（10 分鐘），請在已登入的裝置重新產生。", 403);
        if (req.method !== "POST")
          return page("GEA 會員登入", `<form method="post" action="/o"><input type="hidden" name="t" value="${esc(t)}"><button class="btn go" type="submit">在這台裝置進入會員區</button></form><div class="note" style="margin-top:10px">一次性連結：按下後就失效，${Math.max(1, Math.round((o.exp - now()) / 60))} 分鐘內有效。</div>`);
        const u = await env.DB.prepare("UPDATE otl SET used = 1 WHERE h = ? AND used = 0 AND exp >= ?").bind(h, now()).run();
        if (!u.meta || u.meta.changes !== 1) return loginPage(env, "這個一次性登入連結已用過或已過期，請重新產生。", 403);
        const m = await env.DB.prepare("SELECT * FROM members WHERE id = ?").bind(o.member_id).first();
        if (!m) return loginPage(env, "會員不存在。", 403);
        if (!valid(m)) return expiredPage(m);
        return newSession(env, req, m);
      }
      if (path === "/logout") {
        const sid = cookie(req, COOKIE); if (sid && /^[0-9a-f]{64}$/.test(sid)) await env.DB.prepare("DELETE FROM sessions WHERE sid = ?").bind(await sha(sid)).run();
        return new Response(null, {status: 302, headers: {location: "/", "set-cookie": setCookie(COOKIE, "", 0), "cache-control": "no-store"}});
      }
      if (path === "/auth/line") return lineStart(req, env, url);
      if (path === "/auth/line/cb") return lineCallback(req, env, url);
      if (path === "/robots.txt") return new Response("User-agent: *\nDisallow: /\n", {headers: {"content-type": "text/plain"}});
      if (path.startsWith("/api/admin/")) return (await isAdmin(req, env)) ? adminApi(req, env, url, path) : json({error: "需要管理權限"}, 401);

      const s = await session(req, env);
      if (path.startsWith("/api/")) {
        if (!s) return json({error: "請先登入"}, 401);
        if (!valid(s)) return json({error: "會員已到期或停用", exp: s.exp}, 403);
        if (path === "/api/me") return json({name: s.name, exp: s.exp, admin: s.admin === 1, subs: subsOf(s), line: !!s.line_sub});
        if (path === "/api/prefs") {                                                // 會員自己的版面：GET 讀、PUT 存（JSON、≤ 64 KB）、DELETE 刪
          const k = url.searchParams.get("k") || "";
          if (!PREF_K.test(k)) return json({error: "k 不合法"}, 400);
          if (req.method === "GET") { const r = await env.DB.prepare("SELECT v, ts FROM prefs WHERE member_id = ? AND k = ?").bind(s.id, k).first(); return json(r ? {k, v: JSON.parse(r.v), ts: r.ts} : {k, v: null}); }
          if (req.method === "PUT") {
            if (!(req.headers.get("content-type") || "").startsWith("application/json")) return json({error: "要 application/json"}, 415);
            const t = await req.text();
            if (t.length > 65536) return json({error: "版面超過 64 KB"}, 413);
            try { JSON.parse(t); } catch (e) { return json({error: "不是 JSON"}, 400); }
            const ts = now();
            await env.DB.prepare("INSERT INTO prefs(member_id, k, v, ts) VALUES(?,?,?,?) ON CONFLICT(member_id, k) DO UPDATE SET v = excluded.v, ts = excluded.ts").bind(s.id, k, t, ts).run();
            return json({k, ts, size: t.length});
          }
          if (req.method === "DELETE") { await env.DB.prepare("DELETE FROM prefs WHERE member_id = ? AND k = ?").bind(s.id, k).run(); return json({k, deleted: true}); }
          return json({error: "方法不支援"}, 405);
        }
        if (path === "/api/strategies") { const r = await env.DB.prepare("SELECT value FROM conf WHERE name = 'strategies'").first(); return json(r ? JSON.parse(r.value) : null); }
        if (path === "/api/live" && url.searchParams.has("k")) {                       // 策略即時：s_<代碼> 照訂閱、adm 只給管理者
          const k = url.searchParams.get("k"), v = url.searchParams.get("v") || "", sm = k.match(/^s_([A-Za-z0-9_]{1,40})$/);
          if (!LIVE_K.test(k)) return json({error: "沒有這個即時資料"}, 404);
          if (k === "adm" ? s.admin !== 1 : k !== "tick" && !canFile(s, "data_s_" + sm[1] + ".js")) return json({error: "沒有訂閱這支策略"}, 403);
          const m = await env.DB.prepare("SELECT ts FROM livek WHERE k = ?").bind(k).first();
          if (!m) return new Response(null, {status: 204, headers: {"cache-control": "no-store", ...SEC}});
          if (String(m.ts) === v) return new Response(null, {status: 204, headers: {"cache-control": "no-store", "x-live-ts": String(m.ts), ...SEC}});
          const r = await env.DB.prepare("SELECT ts, data FROM livek WHERE k = ?").bind(k).first();
          return new Response(unb64(r.data), {headers: {"content-type": "application/octet-stream", "cache-control": "no-store", "x-live-ts": String(r.ts), ...SEC}});
        }
        if (path === "/api/live") {                                                    // ?v=上次的 ts：沒變回 204（只查 ts，不讀內容）
          const v = url.searchParams.get("v") || "", m = await env.DB.prepare("SELECT ts FROM live WHERE id = 1").first();
          if (!m) return new Response(null, {status: 204, headers: {"cache-control": "no-store", ...SEC}});
          if (String(m.ts) === v) return new Response(null, {status: 204, headers: {"cache-control": "no-store", "x-live-ts": String(m.ts), ...SEC}});
          const r = await env.DB.prepare("SELECT ts, data FROM live WHERE id = 1").first();
          return new Response(unb64(r.data), {headers: {"content-type": "application/octet-stream", "cache-control": "no-store", "x-live-ts": String(r.ts), ...SEC}});
        }
        if (path === "/api/prices") { const r = await env.DB.prepare("SELECT value, updated FROM conf WHERE name = 'prices'").first(); return json(r ? Object.assign(JSON.parse(r.value), {updated: r.updated}) : null); }
        if (path === "/api/packages") { const r = await env.DB.prepare("SELECT value, updated FROM conf WHERE name = 'packages'").first(); return json(r ? {packages: JSON.parse(r.value), updated: r.updated} : null); }
        return json({error: "沒有這個功能"}, 404);
      }
      if (!s) return path === "/" ? loginPage(env) : new Response(null, {status: 302, headers: {location: "/", "cache-control": "no-store"}});
      if (!valid(s)) return expiredPage(s);
      const name = path === "/" ? "index.html" : decodeURIComponent(path.slice(1));
      if (!NAME_RE.test(name) || name.includes("..")) return new Response("找不到", {status: 404, headers: SEC});
      return serveFile(req, env, s, name);
    } catch (e) {
      console.log("錯誤", path, e && e.stack || e);
      return json({error: "伺服器錯誤"}, 500);
    }
  },
};
