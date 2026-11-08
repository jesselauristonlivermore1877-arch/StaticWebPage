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

## 回報（分支：main，直接推上；commit 58e299e＋本檔）

（實測結果見下方「驗收 run」，跑完後補上）
