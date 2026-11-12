// cloudflare/member/test_packages.mjs ── 套餐上下架 B 的本機模擬測試（假 D1，不連正式站；雲端P 11-12）
//   用法：node cloudflare/member/test_packages.mjs
import W from "./src/worker.js";
const conf = {}; let ok = 0, bad = 0;
const t = (n, c, i = "") => { c ? ok++ : bad++; console.log((c ? "✓ " : "✗ ") + n + (i ? "　" + i : "")); };
const now = () => Math.floor(Date.now() / 1000);
const mem = { normal: { id: 2, admin: 0 }, admin: { id: 1, admin: 1 } };
let who = "normal";
const DB = { prepare(sql) { let args = []; const st = {
  bind(...a) { args = a; return st; },
  async first() {
    if (sql.includes("FROM sessions s JOIN members")) return { sid: "x", s_created: now(), s_last: now(), on_: 1, deleted: 0, exp: "2099-12-31", name: "測", ...mem[who] };
    if (sql.includes("FROM conf WHERE name = 'packages'")) return conf.packages ? { value: conf.packages, updated: 1 } : null;
    return null; },
  async run() { if (sql.startsWith("INSERT INTO conf") && sql.includes("'packages'")) conf.packages = args[0]; if (sql.startsWith("DELETE FROM conf")) delete conf.packages; return {}; },
  async all() { return { results: [] }; } }; return st; },
  async batch() { return []; } };
const env = { DB, ADMIN_TOKEN: "tok" };
const ck = { cookie: "gea_s=" + "a".repeat(64) };
const call = (p, o = {}) => W.fetch(new Request("https://m.example" + p, o), env, { waitUntil() {} });
const P = (id, extra) => Object.assign({ id, name: "套餐" + id, desc: "說明", codes: ["GEA5"], year: 1000 }, extra);
let r = await call("/api/admin/packages", { method: "PUT", headers: { authorization: "Bearer tok", "content-type": "application/json" },
  body: JSON.stringify([P("A"), P("B", { on: false, src: "研究組合" }), P("C", { on: true, src: "手動" })]) });
t("管理者存 3 組（A 沒給 on、B 下架、C 上架）", r.status === 200, JSON.stringify(await r.json()));
const st = JSON.parse(conf.packages);
t("存檔保留 on／src", st[0].on === true && !("src" in st[0]) && st[1].on === false && st[1].src === "研究組合" && st[2].src === "手動", conf.packages);
r = await call("/api/admin/packages", { method: "PUT", headers: { authorization: "Bearer tok", "content-type": "application/json" }, body: JSON.stringify([P("A", { on: "否" })]) });
t("on 不是布林被擋", r.status === 400);
r = await call("/api/admin/packages", { method: "PUT", headers: { authorization: "Bearer tok", "content-type": "application/json" }, body: JSON.stringify([P("A", { src: "亂寫" })]) });
t("src 不在清單被擋", r.status === 400);
t("被擋時原資料不動", JSON.parse(conf.packages).length === 3);
who = "normal"; r = await call("/api/packages", { headers: ck }); let j = await r.json();
t("一般會員只看到上架的 A、C", r.status === 200 && j.packages.map(p => p.id).join() === "A,C", JSON.stringify(j.packages.map(p => p.id)));
who = "admin"; r = await call("/api/packages", { headers: ck }); j = await r.json();
t("管理者看到全部 A、B、C", j.packages.map(p => p.id).join() === "A,B,C");
conf.packages = JSON.stringify([{ id: "OLD", name: "舊", desc: "", codes: ["X"], year: 1 }]); who = "normal";
r = await call("/api/packages", { headers: ck }); j = await r.json();
t("舊資料（沒有 on 欄位）照常上架", j.packages.length === 1);
console.log(`通過 ${ok}，失敗 ${bad}`); process.exit(bad ? 1 : 0);
