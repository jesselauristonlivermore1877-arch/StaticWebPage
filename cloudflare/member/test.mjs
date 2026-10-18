// cloudflare/member/test.mjs ── 會員區自動測試（BASE、ADMIN_TOKEN 由環境變數給；本機 wrangler dev 或正式站都能跑）
//   流程：未登入擋資料 → 管理 token 上傳測試檔 → 新增測試會員拿連結 → GET 只顯示按鈕 → POST 登入拿 cookie → 讀檔、/api/me
//         → 第 4 台裝置登入踢掉第 1 台 → 改到期日成昨天被擋 → 重發連結舊的失效 → 刪會員、刪檔 → 錯的管理 token 被擋。
const BASE = process.env.BASE, TOKEN = process.env.ADMIN_TOKEN;
if (!BASE || !TOKEN) { console.log("缺 BASE／ADMIN_TOKEN"); process.exit(2); }
let ok = 0, bad = 0;
const t = (name, cond, info = "") => { cond ? ok++ : bad++; console.log((cond ? "✓ " : "✗ ") + name + (info ? "　" + info : "")); };
const A = {authorization: "Bearer " + TOKEN};
const go = (p, o = {}) => fetch(BASE + p, {redirect: "manual", ...o});
const day = d => new Date(Date.now() + 8 * 3600e3 + d * 86400e3).toISOString().slice(0, 10);
async function login(link) {
  const k = new URL(link).searchParams.get("k");
  const r = await go("/login", {method: "POST", headers: {"content-type": "application/x-www-form-urlencoded"}, body: "k=" + k});
  const c = (r.headers.get("set-cookie") || "").match(/gea_s=([0-9a-f]{64})/);
  return {st: r.status, cookie: c ? "gea_s=" + c[1] : null};
}

let r = await go("/");
t("未登入首頁＝登入頁", r.status === 200 && (await r.text()).includes("會員登入"), "HTTP " + r.status);
r = await go("/zz_test/hello.txt");
t("未登入拿資料被導回首頁", r.status === 302, "HTTP " + r.status);
r = await go("/api/admin/files", {headers: {authorization: "Bearer x" + TOKEN.slice(1)}});
t("錯的管理 token 被擋", r.status === 401, "HTTP " + r.status);

const body = "GEA 測試檔 " + Date.now();
r = await go("/api/admin/file?name=zz_test/hello.txt", {method: "PUT", headers: {...A, "x-ct": "text/plain; charset=utf-8"}, body});
t("上傳測試檔", r.status === 200, JSON.stringify(await r.json()));
r = await go("/api/admin/files", {headers: A});
const files = (await r.json()).files || [];
t("檔案列表看得到", files.some(f => f.name === "zz_test/hello.txt"), files.length + " 個檔");

r = await go("/api/admin/members", {method: "POST", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({name: "自動測試", contact: "test", exp: day(1)})});
const mem = await r.json();
t("新增測試會員拿到連結", !!mem.link && /\/login\?k=[0-9a-f]{48}$/.test(mem.link), "id " + mem.id);
r = await go(new URL(mem.link).pathname + new URL(mem.link).search);
const html = await r.text();
t("打開連結只顯示按鈕、不建 session", r.status === 200 && html.includes("進入會員區") && !r.headers.get("set-cookie"));
const s1 = await login(mem.link);
t("按下進入 → 302＋cookie", s1.st === 302 && !!s1.cookie);
r = await go("/zz_test/hello.txt", {headers: {cookie: s1.cookie}});
const got = await r.text();
t("登入後讀到測試檔", r.status === 200 && got === body, "HTTP " + r.status);
const etag = r.headers.get("etag");
r = await go("/zz_test/hello.txt", {headers: {cookie: s1.cookie, "if-none-match": etag}});
t("ETag 沒變回 304", r.status === 304, "HTTP " + r.status);
const big = ("GEA 大檔測試，中文全形" + "abcdefghij".repeat(5) + "\n").repeat(60000);           // 約 4.6 MB：切塊存、讀回要一模一樣
r = await go("/api/admin/file?name=zz_test/big.js", {method: "PUT", headers: {...A, "x-ct": "text/javascript; charset=utf-8"}, body: big});
const bm = await r.json();
r = await go("/zz_test/big.js", {headers: {cookie: s1.cookie}});
t("大文字檔切塊存取一致", r.status === 200 && (await r.text()) === big, `${(bm.size / 1e6).toFixed(1)} MB`);
const bin = new Uint8Array(1500000).map((_, i) => (i * 7919) % 256);
r = await go("/api/admin/file?name=zz_test/bin.webp", {method: "PUT", headers: {...A, "x-ct": "image/webp"}, body: bin});
r = await go("/zz_test/bin.webp", {headers: {cookie: s1.cookie}});
const bb = new Uint8Array(await r.arrayBuffer());
t("二進位檔（base64 切塊）存取一致", r.status === 200 && bb.length === bin.length && bb.every((v, i) => v === bin[i]), r.headers.get("content-type"));
await go("/api/admin/file?name=zz_test/big.js", {method: "DELETE", headers: A}); await go("/api/admin/file?name=zz_test/bin.webp", {method: "DELETE", headers: A});
r = await go("/api/me", {headers: {cookie: s1.cookie}});
const me = await r.json();
t("/api/me 是測試會員", me.name === "自動測試" && me.admin === false);
r = await go("/api/admin/members", {headers: {cookie: s1.cookie}});
t("一般會員不能用管理 API", r.status === 401, "HTTP " + r.status);

const s2 = await login(mem.link), s3 = await login(mem.link), s4 = await login(mem.link);
r = await go("/api/me", {headers: {cookie: s1.cookie}});
const r4 = await go("/api/me", {headers: {cookie: s4.cookie}});
t("第 4 台登入踢掉第 1 台（最多 3 台）", r.status === 401 && r4.status === 200, `第1台 ${r.status}、第4台 ${r4.status}`);

r = await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, exp: day(-1)})});
r = await go("/zz_test/hello.txt", {headers: {cookie: s4.cookie}});
t("到期日改成昨天 → 被擋", r.status === 403, "HTTP " + r.status);
r = await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, exp: day(30), rotate: true})});
const rot = await r.json();
const old = await login(mem.link), neu = await login(rot.link);
t("重發連結：舊連結失效、新連結可用", old.st === 403 && neu.st === 302, `舊 ${old.st}、新 ${neu.st}`);
r = await go("/api/me", {headers: {cookie: s2.cookie}});
t("重發連結同時登出所有舊裝置", r.status === 401, "HTTP " + r.status);

const orig = await (await go("/api/strategies", {headers: {cookie: neu.cookie}})).json();        // 正式站的上下架表：測完原樣還原
const reg = [{id: "ZZ_TEST", name: "測試", side: "只多", solo: true, combo: true, on: false}];
r = await go("/api/admin/strategies", {method: "PUT", headers: {...A, "content-type": "application/json"}, body: JSON.stringify(reg)});
t("策略上下架表可存", r.status === 200, "HTTP " + r.status);
r = await go("/api/strategies", {headers: {cookie: neu.cookie}});
const got2 = await r.json();
t("會員讀得到策略表", r.status === 200 && Array.isArray(got2) && got2[0].id === "ZZ_TEST");
r = await go("/api/admin/strategies", {method: "PUT", headers: {...A, "content-type": "application/json"}, body: JSON.stringify(orig || [])});
r = await go("/api/strategies", {headers: {cookie: neu.cookie}});
t("上下架表還原成測試前", JSON.stringify(await r.json()) === JSON.stringify(orig), orig ? orig.length + " 列" : "（原本是預設）");

r = await go("/api/admin/members?id=" + mem.id, {method: "DELETE", headers: A});
r = await go("/api/me", {headers: {cookie: neu.cookie}});
t("刪除會員後 session 失效", r.status === 401, "HTTP " + r.status);
r = await go("/api/admin/file?name=zz_test/hello.txt", {method: "DELETE", headers: A});
t("刪測試檔", r.status === 200);

console.log(`\n結果 ${ok}／${ok + bad}`);
process.exit(bad ? 1 : 0);
