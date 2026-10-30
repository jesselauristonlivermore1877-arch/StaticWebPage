// cloudflare/member/test.mjs ── 會員區自動測試（BASE、ADMIN_TOKEN 由環境變數給；本機 wrangler dev 或正式站都能跑）
//   流程：未登入擋資料 → 管理 token 上傳測試檔 → 新增測試會員拿連結 → GET 只顯示按鈕 → POST 登入拿 cookie → 讀檔、/api/me
//         → 第 4 台裝置登入踢掉第 1 台 → 改到期日成昨天被擋 → 重發連結舊的失效 → 防誤刪（自己、Evans、回收桶、救援）→ 刪會員、刪檔 → 錯的管理 token 被擋。
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
// 會員版面（10-26 19:15）：存在帳號、任何裝置一樣
const PJ = {"content-type": "application/json"};
r = await go("/api/prefs?k=watch", {headers: {cookie: s1.cookie}});
t("沒存過的版面＝null", r.status === 200 && (await r.json()).v === null, "HTTP " + r.status);
const lay = {n: 4, lay: "h", charts: [{p: "5", bs: 2.4}], zz: Date.now()};
r = await go("/api/prefs?k=watch", {method: "PUT", headers: {cookie: s1.cookie, ...PJ}, body: JSON.stringify(lay)});
t("存版面", r.status === 200, "HTTP " + r.status);
r = await go("/api/prefs?k=watch", {method: "PUT", headers: {cookie: s1.cookie, "content-type": "text/plain"}, body: JSON.stringify(lay)});
t("不是 JSON 型別的存版面被擋", r.status === 415, "HTTP " + r.status);
r = await go("/api/prefs?k=../x", {headers: {cookie: s1.cookie}});
t("版面名稱不合法被擋", r.status === 400, "HTTP " + r.status);
r = await go("/api/prefs?k=watch", {method: "PUT", headers: PJ, body: "{}"});
t("未登入不能存版面", r.status === 401, "HTTP " + r.status);
// 一次性登入連結（10-26）：GET 只顯示按鈕 → POST 登入 → 同一個連結再用被擋；用完登出，不影響後面的裝置數測試
r = await go("/api/admin/otl", {method: "POST", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id})});
const ot = await r.json();
t("產生一次性登入連結＋QR", r.status === 200 && /\/o\?t=[0-9a-f]{48}$/.test(ot.link || "") && String(ot.qr || "").startsWith("<svg") && ot.exp - Date.now() / 1000 > 500, "HTTP " + r.status);
const otT = new URL(ot.link).searchParams.get("t");
r = await go("/o?t=" + otT);
t("打開一次性連結只顯示按鈕、不建 session", r.status === 200 && (await r.text()).includes("在這台裝置進入") && !r.headers.get("set-cookie"));
const otPost = () => go("/o", {method: "POST", headers: {"content-type": "application/x-www-form-urlencoded"}, body: "t=" + otT});
r = await otPost();
const oc = (r.headers.get("set-cookie") || "").match(/gea_s=([0-9a-f]{64})/);
t("按下進入 → 302＋cookie", r.status === 302 && !!oc, "HTTP " + r.status);
if (oc) { r = await go("/api/prefs?k=watch", {headers: {cookie: "gea_s=" + oc[1]}}); const pv = (await r.json()).v;
  t("另一台裝置讀到同一份版面", pv && pv.zz === lay.zz);
  r = await go("/", {headers: {cookie: "gea_s=" + oc[1]}}); const hh = await r.text();
  t("網頁送出時帶著版面（GEA_ME.prefs）", !hh.includes("<!--GEA_ME-->") ? hh.includes('"zz":' + lay.zz) : true, hh.includes("<!--GEA_ME-->") ? "正式站還沒有網頁，略過" : ""); }
r = await otPost();
t("同一個一次性連結第二次被擋", r.status === 403, "HTTP " + r.status);
if (oc) await go("/logout", {headers: {cookie: "gea_s=" + oc[1]}});
r = await go("/api/admin/otl", {method: "POST", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: "nobody"})});
t("不存在的會員產不了一次性連結", r.status === 404, "HTTP " + r.status);
r = await go("/api/live");
t("未登入拿不到盤中即時", r.status === 401 || r.status === 302, "HTTP " + r.status);
r = await go("/api/live", {headers: {cookie: s1.cookie}});
t("會員拿得到盤中即時（200 有資料／204 還沒推）", r.status === 200 || r.status === 204, "HTTP " + r.status);
if (r.status === 200) { const v = r.headers.get("x-live-ts"); await r.arrayBuffer(); r = await go("/api/live?v=" + v, {headers: {cookie: s1.cookie}}); t("即時資料沒變回 204", r.status === 204, "HTTP " + r.status); }
r = await go("/api/admin/live?k=s_ZZTEST", {method: "PUT", headers: A, body: "zz"});
t("管理 token 推策略即時", r.status === 200, "HTTP " + r.status);
r = await go("/api/live?k=s_ZZTEST", {headers: {cookie: s1.cookie}});
t("沒訂閱的策略即時 → 403", r.status === 403, "HTTP " + r.status);
// 10-31：不再 PUT 正式的 tick／dash（測試寫入 "{}" 會蓋掉 live_push 推的資料，週末不會重推 → 看盤區盤中資金與側欄儀表消失）；只讀
r = await go("/api/live?k=tick", {headers: {cookie: s1.cookie}});
t("會員拿得到形成中K（逐筆跳）", r.status === 200 || r.status === 204, "HTTP " + r.status);
r = await go("/api/live?k=dash", {headers: {cookie: s1.cookie}});
t("會員拿得到盤勢儀表（200 有資料／204 還沒推）", r.status === 200 || r.status === 204, "HTTP " + r.status);
r = await go("/api/live?k=adm", {headers: {cookie: s1.cookie}});
t("一般會員拿不到原型研究即時", r.status === 403, "HTTP " + r.status);
await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, subs: "ZZTEST"})});
r = await go("/api/live?k=s_ZZTEST", {headers: {cookie: s1.cookie}});
t("訂了就拿得到策略即時", r.status === 200 && (await r.text()) === "zz", "HTTP " + r.status);
await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, subs: ""})});
r = await go("/api/admin/usage", {headers: A});
const us = r.status === 200 ? await r.json() : {};
t("管理 token 看得到每天請求數", r.status === 200 && Array.isArray(us.days) && us.limit === 100000, "HTTP " + r.status + "　" + JSON.stringify((us.days || [])[0] || us.pending || {}));
r = await go("/api/admin/usage", {headers: {cookie: s1.cookie}});
t("一般會員看不到請求數", r.status === 401, "HTTP " + r.status);
r = await go("/api/admin/live", {method: "PUT", headers: {cookie: s1.cookie, "x-gea": "1"}, body: "x"});
t("一般會員不能推即時資料", r.status === 401, "HTTP " + r.status);
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

// 客戶選單價格（Evans 10-19）：存、讀、格式錯擋下、還原成測試前
const porig = await (await go("/api/prices", {headers: {cookie: neu.cookie}})).json();
r = await go("/api/admin/prices", {method: "PUT", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({strat: {ZZ_TEST: 12345}})});
t("選單價格可存", r.status === 200, "HTTP " + r.status);
r = await go("/api/prices", {headers: {cookie: neu.cookie}});
const pg = await r.json();
t("會員讀得到價格", r.status === 200 && pg && pg.strat && pg.strat.ZZ_TEST === 12345);
r = await go("/api/admin/prices", {method: "PUT", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({strat: {ZZ_TEST: -1}})});
t("價格格式錯（負數）被擋", r.status === 400, "HTTP " + r.status);
const pback = porig ? {strat: porig.strat, infra: porig.infra, pack: porig.pack} : {};
r = await go("/api/admin/prices", {method: "PUT", headers: {...A, "content-type": "application/json"}, body: JSON.stringify(pback)});
r = await go("/api/prices", {headers: {cookie: neu.cookie}});
const pnow = await r.json();
t("價格還原成測試前", JSON.stringify(pnow ? {strat: pnow.strat, infra: pnow.infra, pack: pnow.pack} : null) === JSON.stringify(porig ? pback : null), porig ? "有自訂價格" : "（原本是報價單原價）");

// 訂閱（Evans 10-19）：沒訂的策略資料 403、訂了才拿得到、"*"＝全部、原型研究完整版只給管理者
for (const [n, b] of [["data_s_ZZA.js", "window.A=1"], ["data_s_ZZB.js", "window.B=1"], ["data_adm_zz.js", "window.X=1"]])
  await go("/api/admin/file?name=" + n, {method: "PUT", headers: {...A, "x-ct": "text/javascript; charset=utf-8"}, body: b});
const st = async n => (await go("/" + n, {headers: {cookie: neu.cookie}})).status;
t("沒訂閱：策略資料 403", (await st("data_s_ZZA.js")) === 403);
r = await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, subs: "ZZA"})});
t("訂 ZZA：拿得到 ZZA、拿不到 ZZB", (await st("data_s_ZZA.js")) === 200 && (await st("data_s_ZZB.js")) === 403);
r = await go("/api/me", {headers: {cookie: neu.cookie}});
t("/api/me 帶訂閱", JSON.stringify((await r.json()).subs) === '["ZZA"]');
r = await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, subs: "*"})});
t("訂 *：兩個都拿得到", (await st("data_s_ZZA.js")) === 200 && (await st("data_s_ZZB.js")) === 200);
t("一般會員拿不到原型研究完整版", (await st("data_adm_zz.js")) === 403);
r = await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, subs: "ZZA;drop"})});
t("訂閱格式錯被擋", r.status === 400, "HTTP " + r.status);
r = await go("/api/admin/members", {headers: A});
t("會員列表帶訂閱欄", ((await r.json()).members.find(m => m.id === mem.id) || {}).subs === "*");
r = await go("/api/admin/members", {method: "PATCH", headers: {...A, "content-type": "application/json"}, body: JSON.stringify({id: mem.id, admin: true})});
t("管理者拿得到原型研究完整版", (await st("data_adm_zz.js")) === 200);
for (const n of ["data_s_ZZA.js", "data_s_ZZB.js", "data_adm_zz.js"]) await go("/api/admin/file?name=" + n, {method: "DELETE", headers: A});

// 防誤刪（10-29 晚【新】總指揮一）：自己、Evans、最後一個管理員擋下；軟刪除＋回收桶＋還原；救援只認 header 的 ADMIN_TOKEN
const EV = "c00f2e16a59e", J = {"content-type": "application/json"};
const patch = (o, h = A) => go("/api/admin/members", {method: "PATCH", headers: {...h, ...J}, body: JSON.stringify(o)});
r = await go("/api/admin/members", {method: "POST", headers: {...A, ...J}, body: JSON.stringify({name: "自動測試管理員", contact: "test", exp: day(1), admin: true})});
const adm = await r.json(), sa = await login(adm.link), SA = {cookie: sa.cookie, "x-gea": "1"};
t("測試管理員登入", sa.st === 302 && !!sa.cookie);
r = await go("/api/admin/members", {headers: SA});
let L = r.status === 200 ? await r.json() : {};
t("名單標出自己與 Evans 受保護", L.me === adm.id && (L.members || []).some(m => m.id === adm.id && m.protect) && (!(L.members || []).some(m => m.id === EV) || L.members.some(m => m.id === EV && m.protect)), "HTTP " + r.status);
for (const [n, o] of [["停用自己", {on: false}], ["取消自己管理員", {admin: false}], ["自己改成已到期", {exp: day(-1)}]]) {
  r = await patch({id: adm.id, ...o}, SA); const j = await r.json(); t(n + " → 擋下＋原因", r.status === 403 && /自己/.test(j.error || ""), "HTTP " + r.status + "　" + (j.error || "")); }
r = await go("/api/admin/members?id=" + adm.id, {method: "DELETE", headers: SA}); let j = await r.json();
t("刪除自己 → 擋下＋原因", r.status === 403 && /自己/.test(j.error || ""), "HTTP " + r.status + "　" + (j.error || ""));
const evOn = (L.members || []).some(m => m.id === EV);
for (const [who, h] of [["管理者", SA], ["ADMIN_TOKEN", A]]) for (const [n, o] of [["停用", {on: false}], ["取消管理員", {admin: false}]]) {
  r = await patch({id: EV, ...o}, h); j = await r.json(); t(`${who}${n} Evans → 擋下`, evOn ? r.status === 403 && /Evans/.test(j.error || "") : r.status === 404, "HTTP " + r.status + "　" + (j.error || "")); }
r = await go("/api/admin/members?id=" + EV, {method: "DELETE", headers: A}); j = await r.json();
t("刪除 Evans → 擋下", evOn ? r.status === 403 && /Evans/.test(j.error || "") : r.status === 404, "HTTP " + r.status + "　" + (j.error || ""));
r = await go("/api/admin/members", {headers: A}); L = await r.json();
const ev = (L.members || []).find(m => m.id === EV);
t("Evans 還是啟用＋管理員", !evOn || (ev && ev.on_ === 1 && ev.admin === 1));
// 最後一個管理員：只有在 D1 裡沒有其他有效管理員時才會觸發（正式站有 Evans → 改測「另一位管理員可以被停用」不被誤擋）
const nAdm = (L.members || []).filter(m => m.admin === 1 && m.on_ === 1 && m.exp >= day(0)).length;
r = await patch({id: mem.id, on: false}, SA);
t("管理者停用別的管理員（還有其他管理員）→ 可以", r.status === 200, "HTTP " + r.status + "　有效管理員 " + nAdm + " 位");
await patch({id: mem.id, on: true});
// 軟刪除＋回收桶＋還原
r = await go("/api/admin/members?id=" + mem.id, {method: "DELETE", headers: SA}); j = await r.json();
t("刪除會員＝進回收桶", r.status === 200 && j.soft === true && j.purge_at - Date.now() / 1000 > 6.9 * 86400, "HTTP " + r.status);
r = await go("/api/me", {headers: {cookie: neu.cookie}});
t("回收桶裡的會員登不進來", r.status === 401 || r.status === 403, "HTTP " + r.status);
r = await go("/api/admin/members", {headers: SA}); L = await r.json();
t("名單沒有他、已刪除清單有他", !L.members.some(m => m.id === mem.id) && L.trash.some(m => m.id === mem.id));
r = await patch({id: mem.id, on: false}, SA);
t("回收桶裡的不能直接改（要先還原）", r.status === 409, "HTTP " + r.status);
r = await patch({id: mem.id, restore: true}, SA);
r = await go("/api/me", {headers: {cookie: neu.cookie}});
t("一鍵還原：原本裝置直接回來", r.status === 200, "HTTP " + r.status);
r = await go("/api/admin/members?id=" + mem.id, {method: "DELETE", headers: A});
r = await go("/api/admin/members?purge=1&id=" + mem.id, {method: "DELETE", headers: A}); j = await r.json();
t("回收桶裡的可立即永久刪除", r.status === 200 && j.purged === true, "HTTP " + r.status);
r = await go("/api/me", {headers: {cookie: neu.cookie}});
t("永久刪除後 session 失效", r.status === 401, "HTTP " + r.status);
// 救援 API：只認 header 的 ADMIN_TOKEN（真的救援會推 TG 給 Evans，自動測試不打；用 workflow mode=rescue 或 W 桌面 bat）
r = await go("/api/admin/rescue", {method: "POST", headers: SA});
t("管理者 session 不能叫救援", r.status === 401, "HTTP " + r.status);
r = await go("/api/admin/rescue?token=" + TOKEN, {method: "POST"});
t("token 放網址不收", r.status === 401, "HTTP " + r.status);
r = await go("/api/admin/rescue", {method: "POST", headers: {authorization: "Bearer x" + TOKEN.slice(1)}});
t("錯的 token 不能救援", r.status === 401, "HTTP " + r.status);
r = await go("/api/admin/rescue", {headers: A});
t("救援只收 POST", r.status === 405, "HTTP " + r.status);
// 收掉測試管理員（用 ADMIN_TOKEN：不是「自己」，Evans 還是管理員 → 不是最後一個）
r = await go("/api/admin/members?id=" + adm.id, {method: "DELETE", headers: A});
t("ADMIN_TOKEN 刪測試管理員（還有 Evans）→ 可以", r.status === 200, "HTTP " + r.status);
await go("/api/admin/members?purge=1&id=" + adm.id, {method: "DELETE", headers: A});
r = await go("/api/admin/file?name=zz_test/hello.txt", {method: "DELETE", headers: A});
t("刪測試檔", r.status === 200);

console.log(`\n結果 ${ok}／${ok + bad}`);
process.exit(bad ? 1 : 0);
