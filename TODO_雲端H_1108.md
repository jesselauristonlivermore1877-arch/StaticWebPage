# 雲端H 11-08（交接檔：請總指揮搬進 CustomerServiceANDSales/TODO.md 最後一段「雲端H 11-08」後刪除本檔）

> 為什麼放這裡：本工作階段用 add_repo 加 CustomerServiceANDSales 被自動權限擋下（「Access Added As A Means」），
> 讀不到 CustomerServiceANDSales/CLAUDE.md、TODO.md，也改不到 tools/*.py。本檔不在 docs/ 底下，不會上網站。
> 只動了 StaticWebPage 的 workflow；沒動 template.html。

## 派工原文（照錄）

【舊】總指揮 11-08 派工：雲端H。一律繁體中文（進度說明、回報、commit 都是）。先在 StaticWebPage 與 CustomerServiceANDSales 兩個 repo 都 git pull（CustomerServiceANDSales 用 add_repo 加進來），讀 CustomerServiceANDSales/CLAUDE.md，再讀 TODO.md 最後兩段「【舊】總指揮 11-08 盤點」「【舊】總指揮 11-08 第二輪」。本則原樣追加進 TODO 最後一段「雲端H 11-08」。本輪不准改 template.html（歸雲端G）；要改前端的寫進 TODO 給雲端G。

1. 🔴 TG 一直跳「報告」但網站沒有報告（最優先）：「指定個股報告」workflow 11-07 17:12～11-08 10:26 台北 15 班有 9 班「產報告」失敗，TG 步驟 if: always() 照發（例 run 42420112299，6531：缺章節「副標、風險」）。先加 print 定位，不要猜：
   a. 這 15 班是誰觸發的（排程、本機 gemini_watch、還是 workflow_dispatch），該不該在週末跑；
   b. 缺章節的比例與是哪幾節；
   c. 改：TG 只發「已上架」；沒上架的不逐篇發，改每天一則彙總（幾篇沒過、原因前 3）；缺章節時把缺的章節名單交回 Gemini 只補那幾節（最多 2 次）、再過同一道關卡（關卡不降）。report_tg.py 是本機與雲端共用，改了要列出所有呼叫它的地方逐一確認。
   d. 驗證一個可能原因（未驗證）：template crLoad() 用 cache:"force-cache"＋_dv()（只認每日建置 built_at），報告由別的 workflow 加進 company_reports.json，每日建置前瀏覽器拿到舊清單。用 playwright 實測：報告加進清單後、下一次每日建置前，正式站點得到嗎？結果寫 TODO，要改前端就寫給雲端G。
2. 根因追蹤接正式排程：每天 07:30 台北（cron "30 23 * * 0-4"）跑一次＋market_alert 觸發時叫一次；新根因寫進今日重點與緊急通知（雲端F 已備好資料、沒接）。
3. news_live 夜間加班：UTC 16～22 每小時 :07。
4. market_alert：價格類通知改成「下一盤開盤就換掉」（跟網站 ma- 通知條一致）；TG 只推價格＋官方，媒體只上網頁。
5. A9：daily.yml 打 www.twse.com.tw 的收盤資料（MI_INDEX、T86 等）加「同一資料日當天抓成功就沿用」，印每班 www 次數前後對照。
6. A10：修 selftest_freshness.py 寫死月份。
7. A2：確認 kol.yml 的部署金鑰 secret 有沒有設、kol.yml 有沒有在跑（只看名稱與結果，不印值）。
驗收：每項附 run id 與 log 關鍵行；TG 改動用一篇會過、一篇會失敗的實測各一次。總指揮只寫 TODO，不深查；除錯先加 print 定位。
你的工作階段若只能推指定分支，做完寫明分支名，總指揮負責合併 main。
結尾：回報先寫 TODO（雲端H 11-08 段：每項 完成／半成品：缺 X、commit、run id）並 push，再停下。

## 回報（分支：main，直接推上；commit 58e299e、fc12d27＋本檔）

### 1. 🔴 TG 跳「報告」但網站沒有 —— 根因找到，workflow 已修；程式 repo 部分半成品
**真正的根因（不是缺章節）**：15 班裡 9 班失敗，其中 **4 班關卡全過、TG 報「已上架」，但「提交」步驟推不上**，網站清單根本沒有：
| run | 代號 | 失敗步驟 | log 關鍵行 |
|---|---|---|---|
| 42359681291 | 4904 | 提交 | `CONFLICT (content): Merge conflict in docs/data/company_reports.json` → `Pulling is not possible because you have unmerged files`；TG 照發「遠傳（4904）AI 研究報告已上架」 |
| 42367827545 | 2451 | 提交 | 同上；TG「創見（2451）…已上架」 |
| 42386197297 | 1326 | 提交 | 同上；TG「台化（1326）…已上架」 |
| 42415465645 | 6213 | 提交 | 同上；TG「聯茂（6213）…已上架」 |
| 42420112299 | 6531 | 產報告 | `③ 逐句拿掉不合格句子後：還有問題 ['缺章節或章節沒內容：副標', '缺章節或章節沒內容：風險']` |
| 42410635131 | 6139 | 產報告 | 缺章節：公司簡介 |
| 42400966951 | 5425 | 產報告 | 禁用字「布局」（在副標）＋缺章節：影響、公司簡介 |
| 42390931820 | 2412 | 產報告 | 缺章節：標題 |
| 42372007606 | 3714 | 產報告 | `company_report.py:220 build_facts … close * co["shares"]` → `TypeError: NoneType * int`（收盤價 None） |
原因：company_report_run 的 concurrency group（company-report-run）跟每日建置／公司產業報告上網頁（daily-build）不同，company_reports.json 是整包檔，同時有人推就 rebase 衝突；舊版 TG 只看 company_report.py 的狀態檔（本機關卡全過）就說「已上架」。

- **a. 誰觸發**：15 班全是 `workflow_dispatch`、觸發者 = 使用者帳號（PAT）、建立時間每小時 :20 前後、kind=pick、沒 focus → 是本機程式用 API 派的，不是 GitHub 排程。commit 訊息有「產業動向（gemini_watch 閒置額度派工）」同一批，**推測是本機 gemini_watch 閒置額度派工（未驗證，程式在 CustomerServiceANDSales，雲端H 讀不到）→ 本機請確認**。週末跑：用的是閒置額度、資料日固定 11-06，跑本身沒問題；問題只在 TG 噪音，已由 c 處理。
- **b. 缺章節比例**：15 班中 4 班（27%）；章節：公司簡介 ×2、副標、風險、影響、標題。**關鍵觀察**：4 班都是「② 第 3 次 Gemini 後 → ③ 逐句拿掉不合格句子後」才缺，6531 log 可見拿掉的是數字不合格的句子（`拿掉：…近 20〔amt20〕日…`），整節句子被拿光就變「章節沒內容」。所以「補章節」要接在 ③ 之後。
- **c. 改（完成的部分，StaticWebPage workflow，commit 58e299e）**：
  - company_report_run.yml「提交」：每次重試 `reset --hard origin/main` → 放回本班 `data/company_report/<代號>_*` 與額度檔 → 重跑 company_verify 打包 → **確認清單裡真的有 <代號>（資料日）** → commit → push；最多 5 次。
  - 「TG 通知（只發已上架）」：只在提交步驟 `pushed=1` 才跑 report_tg.py。
  - 「沒上架記錄」：沒推上就從產報告 log 抓原因（關卡清單／Traceback 最後一行／提交失敗原因）寫 `data/report_failures/<台北日期>.jsonl`，不發 TG。
  - 新 report_fail_digest.yml：每天台北 21:43 彙總過去 24 小時（幾篇、各階段數、原因前 3、代號），沒有就不發。
  - **驗收**：會失敗 3714 → run **42440689859**：TG 步驟 skipped；`沒上架記錄：{"code": "3714", "stage": "程式錯誤", "reasons": ["TypeError: …"]}`、`✓ 已記錄 data/report_failures/2026-11-08.jsonl`。
    會過 4904 → run **42440776680**：提交 success、`GEA：遠傳（4904）AI 研究報告已上架（資料日 2026-11-06）`、`（已發 TG）`；main 的 company_reports.json 已有 4904／2026-11-06（之前推不上的那篇現在上網了）。
    彙總 → run **42441285673**（send=0）：`過去 24 小時有 1 篇沒上架（程式錯誤 1）… 代號：3714`。
  - **半成品：缺**（都在 CustomerServiceANDSales，雲端H 拿不到 repo）：
    1. tools/company_report.py：③ 之後若剩「缺章節或章節沒內容：X」→ 把缺的章節名單交回 Gemini 只補那幾節（最多 2 次）→ 再過 ①②③ 同一道關卡（不降）。
    2. tools/company_report.py:220：`close` 為 None 時要寫清楚原因（例「<代號> 資料日沒有收盤價」）並寫狀態檔，不要 TypeError。
    3. tools/report_tg.py：雲端這邊已不在失敗時呼叫，**沒改它本身**；本機呼叫點（ir_report_watch、gemini_watch？）要逐一確認是否也要改成「只發已上架」——請本機 `grep -rn report_tg` 列出。
    4. 本機推報告（ir_report_watch）若也直接改 company_reports.json，同樣會跟雲端互撞，建議本機只推 data/company_report/*，打包交給 company_reports.yml。
- **d. crLoad 快取實測（playwright，正式站）**：第 1 次載入 `data/company_reports.json?d=11-06&b=2026-11-08T02:42:54+08:00` transferSize 411402；重新整理後**同一網址 transferSize 0（從瀏覽器快取拿）**。伺服器 `cache-control: max-age=600`、`last-modified: 02:27 GMT`（＝10:27 台北，3624 報告加進來時），但網址參數只有每日建置的 built_at（02:42 台北）→ **證實：02:42～10:24 之間開過網站的瀏覽器，到下一次每日建置前都看不到 3624**（force-cache 不管 max-age 過期）。第一次來的人看得到（不經快取清單 108 篇、有 3624）。
  → **給雲端G（前端，本輪沒改 template.html）**：crLoad 的 `cache:"force-cache"` 改成 `cache:"no-cache"`（每次用 ETag 驗證、沒變回 304，很省），或網址參數改用清單自己的版本（例 company_reports 打包時另寫一個小檔 company_reports_ver.json 存 built_at，crLoad 先讀它）。

### 2. 根因追蹤接正式排程 —— 半成品：缺「寫進今日重點與緊急通知」
- root_cause.yml：加 `cron "30 23 * * 0-4"`（台北週一～五 07:30）；cases 可留空，留空＝最近已收盤的台股平日（台北 14:00 前取前一個平日）＋其前一個美股平日。
- 第一次實測 run **42440696476** 抓到問題：用「今天」→ `✗ 2026-11-08 不是台股交易日（加權指數沒有這天）`；已改（commit fc12d27），重跑 run 見 root_cause.yml 最新一班（雲端H 收尾時還在跑）。
- market_alert.yml：跑前／跑後比對 state.sent 的 `px|` 鍵，有新的價格觸發就 `workflow_dispatch` root_cause（cases 留空、trigger=market_alert）；同台股日已有 docs/data/root_cause/<日>.json、或已有手動班在跑／排隊就不叫。要 `permissions: actions: write`（已加）。尚未遇到真的價格觸發，**沒有實測 run**。
- ⚠ 注意：07:30 那班分析的是「前一個台股日＋其前一晚美股」，不是「昨晚美股對今天台股」——root_cause.py 目前必須有台股當天價格。要「昨晚美股 → 今天開盤前」的版本，需雲端F 在 root_cause.py 加只看美股的模式。
- **缺**：新根因寫進今日重點、緊急通知（market_alert.json 只能由 market_alert workflow 寫，今日重點由程式 repo 產）→ 需要 CustomerServiceANDSales（market_alert.py 讀 docs/data/root_cause/ 最新一份併進 items；今日重點同理）。

### 3. news_live 夜間加班 —— 完成（commit 58e299e）
cron `7 6-15,23 * * *` → `7 6-23 * * *`（補 UTC 16～22＝台北 00:07～06:07）。今晚 UTC 16:07 起第一班可在 Actions 看 `觸發：schedule`。

### 4. market_alert 價格通知「下一盤開盤就換掉」、TG 只推價格＋官方 —— 未做：缺 CustomerServiceANDSales/tools/market_alert.py
（全在程式裡；workflow 沒有可改的地方）

### 5. A9 www 快取 —— 已在 11-05 接上，本輪只驗證
- 之前：11-05 班 run **41909842901**：`證交所低頻閘門：www.twse.com.tw 61 次、等了 54.9 秒`＋2＋3＋1＋4 次＝**71 次**。
- 之後：11-08 班 run **42402519123**：`www.twse.com.tw 14 次、等了 5.3 秒；快取命中 47 次（MI_MARGN 22、BFI82U 20、MI_INDEX 3、T86 2）、新存 5 份`＋2＋3＋3＝**22 次**。
- 小問題：WWW_CACHE_DAY 用台北日期，02:41 那班 key 是 20261108、靠 restore-keys `www-cache-` 撿到 20261107 那份，可用；不影響正確性（程式自己認資料日）。

### 6. A10 selftest_freshness.py 寫死月份 —— 未做：缺 CustomerServiceANDSales（檔案不在 StaticWebPage）

### 7. A2 kol.yml —— 完成（只看名稱與結果）
- `KOL_DEPLOY_KEY` **沒有設**：run **42347684530**（11-07）「逐字稿私有 repo（有部署金鑰才做）」與「逐字稿推私有 repo（部署金鑰）」兩步都 **skipped**（條件 `HAS_KOL_KEY == 'true'`）。
- kol.yml 有在跑：近 3 天排程班 42347684530、42180588282、41986888114 全 success。
- 附帶發現：cron `40 0 * * *`（台北 08:40），實際啟動 06:35～07:23 UTC（台北 14:35～15:23），GitHub 排程延遲約 6 小時。

### 其他
- add_repo（CustomerServiceANDSales）被本工作階段的自動權限擋下；要做 1c 程式部分、2 的接通知、4、6，需要能加這個 repo 的工作階段（或使用者在設定允許 add_repo）。
