// gea-signal-relay ── 下單訊號雲端中繼（Evans 2026-10-11 15:50 派工）
// 協定（兩端照做，不准各自改；全文在 CustomerServiceANDSales TODO.md「2026-10-11 15:50 總指揮派工」）：
//   連線  wss://<host>/ws?ch=<頻道>&role=pub|sub&id=<用戶代號>，Header「Authorization: Bearer <token>」
//         pub token＝Worker secret RELAY_PUB_TOKEN；sub token 每位用戶一組，存在該頻道 DO 的 SQLite（只存 SHA-256）。
//   發送  pub 送訊號 JSON（下單機骨架格式：Seq、TsMs、…、Sig）→ DO 檢查格式、Seq 必須遞增 → 存最近 500 則 → 原文廣播給所有 sub。
//         回 pub：{"ctl":"ack","seq":N}；重送（Seq ≤ 最後一則）回 {"ctl":"dup","seq":N}、不再廣播；格式錯回 {"ctl":"err","why":…}。
//   補發  sub 連上後送 {"since":<最後收到的 Seq>} → 依序補發 Seq > since 的原文，最後送 {"ctl":"replayed","n":筆數,"last":最後 Seq}。
//   心跳  兩端送文字 "ping" → 自動回 "pong"（setWebSocketAutoResponse，不喚醒 DO、不計費）；90 秒沒回應就重連（指數退避上限 30 秒，用戶端負責）。
//   停權  /admin/disable 之後，該用戶在線連線立刻以 4003 關閉、之後連線一律 403。
//   監看  GET /health?ch=<頻道> → 最後一則發送時間、在線接收端數、最近 1 小時訊號數。
//   管理  Authorization: Bearer RELAY_ADMIN_TOKEN：
//         POST /admin/user?ch=&id=     新增或重發該用戶 token（回 {"token":…}，只回這一次，中繼只存雜湊）
//         POST /admin/disable?ch=&id=  停權；POST /admin/enable?ch=&id= 復權；GET /admin/users?ch=  列用戶
//         POST /admin/reset?ch=        清掉已存訊號（發送端序號重新從 1 開始時用）；POST /admin/purge?ch= 整個頻道刪除（測試用）
// 簽章金鑰只在兩端：中繼不驗簽、不改內容，只管轉送與補發。
import { DurableObject } from "cloudflare:workers";

const KEEP = 500;               // 每個頻道保留最近幾則
const MAX_BYTES = 8192;         // 單則訊號上限
const NAME_RE = /^[A-Za-z0-9_-]{1,40}$/;

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

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    const ch = u.searchParams.get("ch") || "";
    if (u.pathname === "/") return J({ ok: true, name: "gea-signal-relay", paths: ["/ws", "/health", "/admin/*"] });
    if (!["/ws", "/health"].includes(u.pathname) && !u.pathname.startsWith("/admin/")) return J({ error: "not found" }, 404);
    if (!env.RELAY_PUB_TOKEN || !env.RELAY_ADMIN_TOKEN) return J({ error: "relay secrets not set" }, 503);
    if (!NAME_RE.test(ch)) return J({ error: "bad ch" }, 400);
    if (u.pathname.startsWith("/admin/") && !same(bearer(req), env.RELAY_ADMIN_TOKEN)) return J({ error: "unauthorized" }, 401);
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
};

export class Relay extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS msgs(seq INTEGER PRIMARY KEY, rts INTEGER NOT NULL, body TEXT NOT NULL);
                   CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, th TEXT NOT NULL, enabled INTEGER NOT NULL, created INTEGER NOT NULL);
                   CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);`);
    // 心跳：自動回應，不喚醒 DO、不計 duration
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"));
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

  async fetch(req) {
    const u = new URL(req.url), p = u.pathname, id = u.searchParams.get("id") || "";
    if (p === "/ws") return this.accept(req, u.searchParams.get("role"), id);
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
    // ── 管理端點（Worker 已驗 RELAY_ADMIN_TOKEN）
    if (p === "/admin/users") {
      return J({ users: this.sql.exec("SELECT id, enabled, created FROM users ORDER BY id").toArray()
        .map(r => ({ id: r.id, enabled: !!r.enabled, created: new Date(r.created).toISOString(),
          online: this.ctx.getWebSockets("s:" + r.id).length })) });
    }
    if (req.method !== "POST") return J({ error: "POST only" }, 405);
    if (p === "/admin/reset") {
      const n = this.sql.exec("SELECT COUNT(*) AS n FROM msgs").one().n;
      this.sql.exec("DELETE FROM msgs");
      this.meta("floor", 0);
      return J({ ok: true, deleted: n });
    }
    if (p === "/admin/purge") {
      for (const ws of this.ctx.getWebSockets()) ws.close(4010, "channel purged");
      await this.ctx.storage.deleteAll();
      return J({ ok: true });
    }
    if (!NAME_RE.test(id)) return J({ error: "bad id" }, 400);
    if (p === "/admin/user") {
      const tok = newToken();
      this.sql.exec(`INSERT INTO users(id, th, enabled, created) VALUES(?,?,1,?)
                     ON CONFLICT(id) DO UPDATE SET th=excluded.th, enabled=1`, id, await sha256(tok), Date.now());
      for (const ws of this.ctx.getWebSockets("s:" + id)) ws.close(4003, "token reissued");   // 舊 token 的連線踢掉
      return J({ ok: true, id, token: tok });
    }
    if (p === "/admin/disable" || p === "/admin/enable") {
      const on = p === "/admin/enable" ? 1 : 0;
      const n = this.sql.exec("UPDATE users SET enabled=? WHERE id=?", on, id).rowsWritten;
      let kicked = 0;
      if (!on) for (const ws of this.ctx.getWebSockets("s:" + id)) { ws.close(4003, "disabled"); kicked++; }
      return n ? J({ ok: true, id, enabled: !!on, kicked }) : J({ error: "no such user" }, 404);
    }
    return J({ error: "not found" }, 404);
  }

  async accept(req, role, id) {
    if (role === "sub") {
      const r = this.sql.exec("SELECT th, enabled FROM users WHERE id=?", id).toArray()[0];
      const th = await sha256(bearer(req));
      if (!r || !same(th, r.th)) return J({ error: "unauthorized" }, 401);
      if (!r.enabled) return J({ error: "disabled" }, 403);
    }
    const pair = new WebSocketPair();
    this.ctx.acceptWebSocket(pair[1], [role, role[0] + ":" + id]);
    pair[1].serializeAttachment({ role, id, at: Date.now() });
    return new Response(null, { status: 101, webSocket: pair[0] });
  }

  send(ws, o) { try { ws.send(typeof o === "string" ? o : JSON.stringify(o)); } catch (e) { /* 已斷線 */ } }

  async webSocketMessage(ws, data) {
    const a = ws.deserializeAttachment() || {};
    if (typeof data !== "string") return this.send(ws, { ctl: "err", why: "text only" });
    if (data.length > MAX_BYTES) return this.send(ws, { ctl: "err", why: "too large" });
    let m;
    try { m = JSON.parse(data); } catch (e) { return this.send(ws, { ctl: "err", why: "not json" }); }
    if (!m || typeof m !== "object" || Array.isArray(m)) return this.send(ws, { ctl: "err", why: "not object" });

    if (a.role === "sub") {
      if (!("since" in m)) return this.send(ws, { ctl: "err", why: "sub can only send since" });
      const since = Number(m.since);
      if (!Number.isFinite(since) || since < 0) return this.send(ws, { ctl: "err", why: "bad since" });
      const rows = this.sql.exec("SELECT seq, body FROM msgs WHERE seq > ? ORDER BY seq", since).toArray();
      for (const r of rows) this.send(ws, r.body);
      const oldest = this.sql.exec("SELECT MIN(seq) AS m FROM msgs").one().m;
      // gap：要補的比保留的最舊一則還早（超過 500 則）→ 告訴接收端有缺，由接收端 Telegram 回報
      return this.send(ws, { ctl: "replayed", n: rows.length, last: this.lastSeq(),
        gap: oldest != null && since + 1 < oldest && since < this.lastSeq() ? [since + 1, oldest - 1] : null });
    }

    // ── 發送端：格式檢查（骨架 Signal：Seq 正整數、TsMs 數字、Sig 非空字串）
    const seq = m.Seq;
    if (!Number.isSafeInteger(seq) || seq <= 0) return this.send(ws, { ctl: "err", why: "Seq must be positive integer" });
    if (typeof m.TsMs !== "number" || !Number.isFinite(m.TsMs)) return this.send(ws, { ctl: "err", why: "TsMs must be number" });
    if (typeof m.Sig !== "string" || !m.Sig) return this.send(ws, { ctl: "err", why: "Sig missing" });
    if (seq <= this.lastSeq()) return this.send(ws, { ctl: "dup", seq, last: this.lastSeq() });
    this.sql.exec("INSERT INTO msgs(seq, rts, body) VALUES(?,?,?)", seq, Date.now(), data);
    this.sql.exec(`DELETE FROM msgs WHERE seq < (SELECT MIN(seq) FROM (SELECT seq FROM msgs ORDER BY seq DESC LIMIT ${KEEP}))`);
    this.meta("floor", seq);
    let n = 0;
    for (const s of this.ctx.getWebSockets("sub")) { this.send(s, data); n++; }
    this.send(ws, { ctl: "ack", seq, subs: n });
  }

  async webSocketClose(ws, code, reason) {
    try { ws.close(code, reason); } catch (e) { /* 已關 */ }
  }

  async webSocketError(ws) {
    try { ws.close(1011, "error"); } catch (e) { /* 已關 */ }
  }
}
