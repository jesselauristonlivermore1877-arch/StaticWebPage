# -*- coding: utf-8 -*-
# ==============================================================================
# GEA 互動機器人 — 主程式 (FastAPI Webhook)
#
# 指令總覽：
#   所有人：
#     @id             → 回覆你的 userId（第一次部署後，你自己傳這個拿管理員ID）
#     @調查 2330       → 即時報價＋法人動向＋新聞（代號或中文名皆可，空格可省略）
#     @籌碼            → 今日三大法人買賣金額
#     其他訊息         → 使用說明
#   管理員限定（userId 在 ADMIN_USER_IDS 內）：
#     @摘錄 <來源名稱>
#     <貼上FB/新聞內文>  → 產出重點摘要「預覽稿」回給你（有 Claude API 金鑰
#                          就自動摘要；沒有就原文加框整理）
#     @發送            → 把預覽稿正式廣播給全部好友
#     @取消            → 丟棄預覽稿
#
# 環境變數：
#   LINE_CHANNEL_TOKEN   (必填) Messaging API 的 Channel Access Token
#   LINE_CHANNEL_SECRET  (必填) Channel Secret（驗證簽章用）
#   ADMIN_USER_IDS       (必填) 管理員 userId，多個用逗號分隔
#   ANTHROPIC_API_KEY    (選填) 填了 @摘錄 就會自動 AI 摘要
#   WEB_KEY              (選填) HTTP 救濟通道金鑰。沒設 = /api/* 後門全部關閉
#                        （fail closed）。設了才能用 ?key=... 走瀏覽器救濟。
# ==============================================================================
import os
import re
import json
import hmac
import base64
import hashlib
import secrets
import threading
import requests as rq
from fastapi import FastAPI, Request, Header, HTTPException

import engines

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
CHANNEL2_SECRET = os.environ.get("LINE2_CHANNEL_SECRET", "")
ADMIN_USER_IDS = set(x.strip() for x in os.environ.get("ADMIN_USER_IDS", "").split(",") if x.strip())
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── 救濟通道金鑰（HTTP 後門專用，與 LINE 憑證無關）─────────────────────────
WEB_KEY = os.environ.get("WEB_KEY", "")

def _check_key(key: str = "", hdr_key: str = ""):
    if not WEB_KEY:
        raise HTTPException(status_code=404, detail="Not Found")
    supplied = (key or hdr_key or "")
    if not secrets.compare_digest(supplied.encode("utf-8"), WEB_KEY.encode("utf-8")):
        raise HTTPException(status_code=404, detail="Not Found")

app = FastAPI()

_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(os.path.join(_static_dir, "bt"), exist_ok=True)
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

pending_drafts = {}   
pending_results = {}

HELP_TEXT = (
    "🤖 GEA 戰情機器人指令\n"
    "━━━━━━━━━━━━\n"
    "💰 @籌碼\n"
    " 法人統計＋外資/投信\n"
    " 買賣超金額 Top30 (各自分列)\n\n"
    "🌏 @外資 上市/上櫃買賣超 Top50\n"
    "📈 @投信 上市/上櫃買賣超 Top50\n"
    "📊 @信用 融資融券增減 Top30\n"
    "🔥 @量榜 成交金額Top50＋體質近況\n"
    "🎯 @期權籌碼 台指期選籌碼五表\n"
    "🏦 @主動ETF 全市場主動式ETF清單\n"
    "  (輸入 @主動ETF 00981A 查明細)\n"
    "📉 @回檔 產業地圖深度回檔追蹤\n"
    "⚡ @轉強 相對強度排行+轉強旗標\n"
    "🧭 @盤勢 台積vs市場體感+廣度名單\n"
    "🏛 @法人結構 法人要角的位階定位\n"
    "🗂 @族群 族群清單｜❓ @名詞 名詞解釋\n"
    "━━━━━━━━━━━━\n"
    "也可以直接用下方選單點選 👇"
)

def verify_signature(body: bytes, signature: str) -> bool:
    if not CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), signature)

def ai_digest(source_name: str, raw_text: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        "你是期貨營業員的資訊助理。請將以下貼文濃縮成 3~5 點重點摘要：\n"
        "1. 保留關鍵數字、公司名、具名消息來源\n"
        "2. 分清楚「作者陳述的事實」與「作者的推論/觀點」，觀點請標註（作者觀點）\n"
        "3. 絕對不要加入任何買賣建議或你自己的判斷\n"
        "4. 繁體中文、適合 LINE 手機閱讀、每點一行、開頭用 ▪ 符號\n"
        f"5. 出處標註為：{source_name}\n\n"
        f"貼文內容：\n{raw_text}"
    )
    try:
        r = rq.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        return text or None
    except Exception:
        return None

def build_digest(source_name: str, raw_text: str) -> str:
    body = ai_digest(source_name, raw_text)
    if body is None:
        body = raw_text.strip()
        if len(body) > 1500:
            body = body[:1500] + "…(節錄)"
    return (
        f"📌 【重點摘錄｜{source_name}】\n"
        "━━━━━━━━━━━━\n"
        f"{body}\n"
        "━━━━━━━━━━━━\n"
        f"出處：{source_name}｜僅供資訊參考，非投資建議"
    )

def _parse_range(rest):
    import datetime as _dt
    if not rest or not rest.strip():
        return None, None, None
    txt = rest.strip()
    dm = re.search(r"(\d{4})\s*[/-]?\s*(\d{1,2})\s*[/-]?\s*(\d{1,2})\s*[-~到至]+\s*"
                   r"(\d{4})\s*[/-]?\s*(\d{1,2})\s*[/-]?\s*(\d{1,2})", txt)
    if not dm:
        if re.search(r"\d{4}\s*[/-]\s*\d{1,2}", txt) or "-" in txt or "~" in txt:
            return None, None, ("⚠️ 區間格式看不懂。正確寫法：\n"
                                "@回測 0.60 0.35 2025/01/01-2026/06/30\n"
                                "（起日-迄日，年/月/日）")
        return None, None, None
    try:
        s = _dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        e = _dt.date(int(dm.group(4)), int(dm.group(5)), int(dm.group(6)))
    except ValueError as ex:
        return None, None, (f"⚠️ 日期不存在：{ex}\n"
                            f"（例如 6/31、2/30 這種日子沒有喔）")
    if s >= e:
        return None, None, "⚠️ 起日必須早於迄日。"
    return s.isoformat(), e.isoformat(), None

def handle_text(user_id: str, text: str, reply_token: str):
    text = text.strip()
    is_admin = user_id in ADMIN_USER_IDS

    def reply(msg):
        ok = engines.line_reply(reply_token, msg)
        if not ok:  
            engines.line_push(user_id, msg)

    def reply_msgs(msgs):
        ok = engines.line_reply_messages(reply_token, msgs)
        if not ok:
            engines.line_push_messages(user_id, msgs)

    if text == "@id":
        reply(f"你的 userId：\n{user_id}\n\n"
              "（要當管理員的話，把這串填進伺服器環境變數 ADMIN_USER_IDS）")
        return

    def reply_blocks(blocks):
        ok, leftover = engines.line_reply_multi(reply_token, blocks)
        if not ok:  
            engines.line_push_messages(user_id, engines.blocks_to_messages(blocks))
        elif leftover:  
            engines.line_push_messages(user_id, leftover)

    if text == "@日選 debug" and is_admin:
        import screener
        reply(screener.vip_debug())
        return

    if text in ("@日選", "@VIP", "@vip", "@多因子", "@選股"):
        import screener
        reply_blocks(screener.build_vip_screen(top_n=20))
        return

    if text in ("@籌碼", "@三大法人"):
        reply_blocks(engines.get_inst_full(top_n=50))
        return

    if text.startswith("@主動ETF") or text.startswith("@主動etf") or text.startswith("@主動式ETF"):
        import active_etf
        arg = (text.replace("@主動式ETF", "").replace("@主動ETF", "")
                   .replace("@主動etf", "").strip())
        if arg.endswith("debug") or arg.startswith("debug"):
            if is_admin:
                code = arg.replace("debug", "").strip() or "00981A"
                reply(active_etf.active_etf_debug(code))
            return
        code = arg.upper() if arg else None
        reply_blocks(active_etf.get_active_etf_blocks(code))
        return

    if text in ("@外資",):
        reply_blocks(engines.get_side_blocks(side="foreign", top_n=50))
        return

    if text in ("@投信",):
        reply_blocks(engines.get_side_blocks(side="trust", top_n=50))
        return

    if text in ("@信用", "@融資", "@信用交易"):
        reply_blocks(engines.get_margin_blocks(top_n=50))
        return

    if text == "@期權籌碼 debug" and is_admin:
        import options
        try:
            reply(options.debug_dump())
        except Exception as e:
            reply(f"⚠️ 診斷失敗：{e}")
        return

    if text.startswith(("@永豐 長測", "@永豐 soak")) and is_admin:
        import re as _re, shioaji_live
        m = _re.search(r"(\d+)", text)
        reply(shioaji_live.start(int(m.group(1)) if m else 60))
        return

    if text in ("@永豐 報告", "@永豐 狀態") and is_admin:
        import shioaji_live
        reply(shioaji_live.status())
        return

    if text in ("@永豐 停止", "@永豐 收工") and is_admin:
        import shioaji_live
        reply(shioaji_live.stop())
        return

    if text in ("@永豐", "@shioaji", "@Shioaji") and is_admin:
        import shioaji_probe
        try:
            sim = "模擬" in text or "sim" in text.lower()
            reply(shioaji_probe.probe(simulation=True if sim else None))
        except Exception as e:
            reply(f"⚠️ 永豐體檢失敗：{type(e).__name__}: {e}")
        return

    if text in ("@報價 debug", "@即時 debug", "@mis") and is_admin:
        import screener
        try:
            reply(screener.mis_debug())
        except Exception as e:
            reply(f"⚠️ 診斷失敗：{e}")
        return

    if text in ("@盤勢 debug", "@選股 debug", "@回檔 debug", "@轉強 debug") and is_admin:
        import screener
        try:
            reply(screener.screener_debug())
        except Exception as e:
            reply(f"⚠️ 診斷失敗：{e}")
        return

    if text in ("@量榜 debug", "@成交金額 debug") and is_admin:
        try:
            reply(engines.amount_debug())
        except Exception as e:
            reply(f"⚠️ 診斷失敗：{e}")
        return

    if text in ("@重暖", "@清快取", "@rewarm") and is_admin:
        import screener
        try:
            n, failed = screener.force_rewarm()
            reply(f"✅ 已清空並重建選股快取：{n} 檔"
                  + (f"（{len(failed)} 檔失敗）" if failed else ""))
        except Exception as e:
            reply(f"⚠️ 重暖失敗：{e}")
        return

    if text in ("@debug", "@診斷") and is_admin:
        reply("🔧 可用診斷指令（管理員）：\n"
              "• @期權籌碼 debug — 期交所各資料集原始標籤＋散戶比中間量\n"
              "• @盤勢 debug — Yahoo 個股延遲 vs 官方最新日（@回檔/@轉強 抓舊價時查）\n"
              "• @量榜 debug — 盤中 MIS 原始欄位（成交金額=0 時查）\n"
              "• @推播額度 — LINE 廣播額度用量（查好友收不到）\n"
              "\n其他指令目前無專屬 debug；如需要再跟開發者說要加哪個。")
        return

    if text in ("@期權籌碼", "@期權"):
        import options
        try:
            reply_blocks(options.get_option_chips())
        except Exception as e:
            reply(f"⚠️ 期權籌碼取得失敗：{e}\n（管理員可用 @期權籌碼 debug 診斷）")
        return

    def screener_reply(builder, *args):
        import screener
        was_ready = screener.cache_ready()
        if not was_ready:
            reply("📡 正在建置今日資料庫（約 60~90 秒）。\n"
                  "建置完成後，再按一次選單（或傳任何訊息）就會立刻收到結果。")
        if not screener._ensure():
            pending_results[user_id] = [{"type": "text", "text": "⚠️ 資料建置失敗，請稍後再試。"}]
            return
        pending_results.pop(user_id, None)   
        blocks = builder(*args)
        if was_ready:
            reply_blocks(blocks)
        else:
            pending_results[user_id] = engines.blocks_to_messages(blocks)

    m = re.match(r"^@回檔\s*(.*)$", text)
    if m:
        import screener
        q = m.group(1).strip()
        if q:
            screener_reply(screener.build_drawdown_sector, q)
        else:
            screener_reply(screener.build_drawdown_overview)
        return

    if text == "@轉強":
        import screener
        screener_reply(screener.build_strength_ranking)
        return

    if text == "@量榜":
        import screener
        screener_reply(screener.build_volume_ranking)
        return

    if text == "@盤勢":
        import screener
        screener_reply(screener.build_market_structure)
        return

    if text == "@族群":
        import screener
        engines.line_reply_multi(reply_token, screener.build_sector_list())
        return

    if text == "@名詞":
        import screener
        engines.line_reply_multi(reply_token, screener.build_legend())
        return

    if text in ("@法人結構", "@籌碼結構"):
        import screener
        screener_reply(screener.build_inst_structure)
        return

    if is_admin:
        m = re.match(r"^@回測\s+([\d.]+)\s+([\d.]+)\s*(.*)$", text)
        if m:
            import bt
            eu, et, rest = float(m.group(1)), float(m.group(2)), m.group(3)
            live = "live" in rest.lower()
            L = {"L1": 120, "L3": 1800, "L6": 2400}
            for kv in re.findall(r"(L[136])\s*=\s*(\d+)", rest):
                L[kv[0]] = int(kv[1])
            start, end, derr = _parse_range(rest)
            if derr:
                reply(derr)
                return
            try:
                msgs = bt.build_backtest(eu, et, L["L1"], L["L3"], L["L6"],
                                         start, end, live=live)
                reply_msgs(msgs)   
            except Exception as e:
                reply(f"⚠️ 回測失敗：{e}")
            return
        if text == "@暖機":
            reply("🔥 暖機啟動：載入回測成品＋建置今日選股資料庫（約60~90秒），完成後通知你。")
            try:
                import bt, screener
                bt.load_product(); bt.load_curves()   
                ok = screener._ensure()
                n = len(screener._cache.get("stats", {}))
                pready = "就緒" if bt.product_ready() else "缺成品(先跑 precompute bt)"
                engines.line_push(user_id, f"✅ 暖機完成：回測成品{pready}｜選股資料 {n} 檔。命中格點秒回。")
            except Exception as e:
                engines.line_push(user_id, f"⚠️ 暖機部分失敗：{e}")
            return

        m = re.match(r"^@驗測\s+(\w+)", text)
        if m:
            import vt
            name = m.group(1)
            live = "live" in text.lower()
            cached = None if live else vt.load_scorecard_cache(name)
            if cached:
                import flex as _flex
                fm = _flex.scorecard_flex(cached["card"])
                note = f"🕐 本結果為預算快取（{cached['ts']}）\n重算請用 @驗測 {name} live"
                if fm:
                    reply_msgs(fm + [{"type": "text", "text": note}])
                else:
                    reply(cached["card"] + "\n\n" + note)
                return
            reply(f"📋 驗測 {name} 現場執行中（TXF+NQ 全格各324＋排列3000，約20~40分鐘），過程分關回報。")
            try:
                card, passed, total = vt.run_scorecard(
                    name, progress=lambda s: engines.line_push(user_id, s))
                vt.save_scorecard_cache(name, card, passed, total)
                import flex as _flex
                fm = _flex.scorecard_flex(card)
                if fm:
                    engines.line_push_messages(user_id, fm)
                else:
                    engines.line_push(user_id, card)
            except Exception as e:
                engines.line_push(user_id, f"⚠️ 驗測失敗：{e}")
            return
        m = re.match(r"^@組合\s*([\d.]+)\s*,\s*([\d.]+)\s*\+\s*([\d.]+)\s*,\s*([\d.]+)(.*)$", text)
        if m:
            import bt
            p1 = (float(m.group(1)), float(m.group(2)))
            p2 = (float(m.group(3)), float(m.group(4)))
            rest = m.group(5) or ""
            live = "live" in rest.lower()
            start, end, derr = _parse_range(rest)
            if derr:
                reply(derr)
                return
            try:
                msgs = bt.build_combo(p1, p2, start=start, end=end, live=live)
                reply_msgs(msgs)   
            except Exception as e:
                reply(f"⚠️ 組合分析失敗：{e}")
            return
        m = re.match(r"^@摘錄\s*(\S*)\s*\n([\s\S]+)$", text)
        if m:
            source_name = m.group(1).strip() or "外部來源"
            raw = m.group(2).strip()
            draft = build_digest(source_name, raw)
            pending_drafts[user_id] = {"text": draft, "imgs": []}
            reply("📝 以下是預覽稿（尚未發送）：\n\n" + draft +
                  "\n\n🖼 現在可直接傳圖片附加到這篇\n"
                  "✅ 確認無誤請回覆 @發送\n❌ 放棄請回覆 @取消")
            return
        if text.startswith("@摘錄"):
            reply("格式：第一行「@摘錄 來源名稱」，\n第二行起貼上整篇內文。\n\n"
                  "範例：\n@摘錄 萬鈞法人視野\n(這裡貼內文...)")
            return
        if text in ("@推播額度", "@發送 debug", "@發送debug"):
            q = engines.get_broadcast_quota()
            if not q:
                reply("⚠️ 查詢額度失敗（TOKEN 無效或 API 異常）。\n"
                      "請確認 LINE_CHANNEL_TOKEN 環境變數正確。")
            else:
                typ, limit, used, remain = q
                if typ == "none":
                    reply(f"✅ 推播額度：無上限（付費方案）\n已用 {used if used is not None else '?'} 則")
                else:
                    reply(f"📊 推播額度診斷\n方案：{typ}（免費層月上限通常 200 則）\n"
                          f"上限：{limit}｜已用：{used}｜剩餘：{remain}\n\n"
                          + ("⚠️ 額度已用罄！這就是好友收不到的原因——"
                             "本月廣播會被 LINE 靜默丟棄。下月 1 日重置，或升級方案。"
                             if (remain is not None and remain <= 0) else
                             "額度尚有剩餘，若仍收不到請用 @發送 看實際回傳碼。"))
            return
        if text == "@發送":
            draft = pending_drafts.pop(user_id, None)
            if draft:
                base_url = os.environ.get("BASE_URL", "").rstrip("/")
                msgs = [{"type": "text", "text": draft["text"]}]
                for fn in draft["imgs"]:
                    u = f"{base_url}/static/digest/{fn}"
                    msgs.append({"type": "image", "originalContentUrl": u, "previewImageUrl": u})
                ok, detail = engines.line_broadcast_messages(msgs)
                n_img = len(draft["imgs"])
                if ok:
                    reply(f"✅ 已廣播成功（文字＋{n_img}張圖，LINE 回 200）。\n"
                          f"（廣播吃額度＝好友數×{1+n_img}則）\n"
                          f"若好友仍說沒收到，多半是好友把官方帳號封鎖，或免費額度用罄——"
                          f"打 @推播額度 查。")
                else:
                    pending_drafts[user_id] = draft
                    reply(f"❌ 廣播失敗！LINE 實際回應：\n{detail}\n\n"
                          f"常見原因：\n"
                          f"• 429/月額度用罄 → 打 @推播額度 確認\n"
                          f"• 401/403 → LINE_CHANNEL_TOKEN 失效\n"
                          f"• 400 → 圖片網址非 https 或無法存取（BASE_URL 設定）\n"
                          f"預覽稿已保留，修正後再 @發送。")
            else:
                reply("目前沒有待發送的預覽稿。先用 @摘錄 建立一份。")
            return
        if text == "@取消":
            if pending_drafts.pop(user_id, None):
                reply("🗑 預覽稿已丟棄。")
            else:
                reply("目前沒有待發送的預覽稿。")
            return

    pend = pending_results.pop(user_id, None)
    if pend:
        reply_msgs(pend)
        return
    reply(HELP_TEXT)

def _save_line_image(message_id):
    import requests as _rq, time as _t
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {"Authorization": f"Bearer {os.environ.get('LINE_CHANNEL_TOKEN','')}"}
    r = _rq.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "digest")
    os.makedirs(d, exist_ok=True)
    fn = f"dg_{int(_t.time()*1000)}.jpg"
    with open(os.path.join(d, fn), "wb") as f:
        f.write(r.content)
    return fn

def process_event(ev: dict):
    try:
        if ev.get("type") != "message":
            return
        msg = ev.get("message", {})
        user_id = ev.get("source", {}).get("userId", "")
        if (msg.get("type") == "image" and user_id in ADMIN_USER_IDS
                and user_id in pending_drafts):
            try:
                fn = _save_line_image(msg.get("id"))
                pending_drafts[user_id]["imgs"].append(fn)
                n = len(pending_drafts[user_id]["imgs"])
                engines.line_reply(ev.get("replyToken", ""),
                                   f"🖼 圖片已附加（目前 {n} 張）。@發送 正式廣播、@取消 放棄。")
            except Exception as e:
                engines.line_push(user_id, f"⚠️ 圖片下載失敗：{e}")
            return
        if msg.get("type") != "text":
            return
        reply_token = ev.get("replyToken", "")
        handle_text(user_id, msg.get("text", ""), reply_token)
    except Exception as e:
        print(f"事件處理錯誤: {e}")

@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    body = await request.body()
    if not verify_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="Bad signature")
    data = json.loads(body)
    for ev in data.get("events", []):
        threading.Thread(target=process_event, args=(ev,), daemon=True).start()
    return "OK"

@app.get("/api/cmd/{cmd_name}")
async def web_command(cmd_name: str, key: str = "", x_api_key: str = Header(None)):
    _check_key(key, x_api_key or "")
    try:
        if cmd_name in ["籌碼", "三大法人"]:
            import engines
            return engines.get_inst_full(top_n=50)
        elif cmd_name == "外資":
            import engines
            return engines.get_side_blocks(side="foreign", top_n=50)
        elif cmd_name == "投信":
            import engines
            return engines.get_side_blocks(side="trust", top_n=50)
        elif cmd_name == "信用":
            import engines
            return engines.get_margin_blocks(top_n=50)
        elif cmd_name == "期權籌碼":
            import options
            return options.get_option_chips()
        elif cmd_name == "盤勢":
            import screener
            screener._ensure()
            return screener.build_market_structure()
        elif cmd_name == "量榜":
            import screener
            screener._ensure()
            return screener.build_volume_ranking()
        elif cmd_name == "轉強":
            import screener
            screener._ensure()
            return screener.build_strength_ranking()
        elif cmd_name == "回檔":
            import screener
            screener._ensure()
            return screener.build_drawdown_overview()
        elif cmd_name == "法人結構":
            import screener
            screener._ensure()
            return screener.build_inst_structure()
        elif cmd_name in ["日選", "VIP"]:
            import screener
            screener._ensure()
            return screener.build_vip_screen(top_n=20)
        else:
            return {"status": "error", "message": f"尚未開放網頁版指令: {cmd_name}"}
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"[web_command] {cmd_name} 失敗：{type(e).__name__}: {e}", flush=True)
        return {"status": "error",
                "message": f"指令執行失敗（{type(e).__name__}），詳情見伺服器 log"}

def _shioaji_call(fn, *a):
    try:
        return {"status": "ok", "message": fn(*a)}
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"[shioaji api] {getattr(fn, '__name__', fn)} 失敗："
              f"{type(e).__name__}: {e}", flush=True)
        return {"status": "error", "message": f"{type(e).__name__}: {e}"}

@app.get("/api/start_test")
async def start_test(minutes: int = 600, key: str = "", x_api_key: str = Header(None)):
    _check_key(key, x_api_key or "")
    minutes = max(1, min(int(minutes), 600))
    import shioaji_live
    return _shioaji_call(shioaji_live.start, minutes)

@app.get("/api/status")
async def get_status(key: str = "", x_api_key: str = Header(None)):
    _check_key(key, x_api_key or "")
    from fastapi.responses import PlainTextResponse
    import shioaji_live
    r = _shioaji_call(shioaji_live.status)
    return PlainTextResponse(str(r["message"]))

@app.get("/api/stop_test")
async def stop_test(key: str = "", x_api_key: str = Header(None)):
    _check_key(key, x_api_key or "")
    import shioaji_live
    return _shioaji_call(shioaji_live.stop)

@app.get("/")
@app.head("/")
async def health():
    return {"status": "GEA bot alive"}

@app.on_event("startup")
async def _auto_warm():
    def _w():
        import time as _t
        _t.sleep(15)               
        while True:                
            try:
                import screener
                screener._ensure()     
            except Exception:
                pass
            try:
                engines.get_inst_full(top_n=30)   
            except Exception:
                pass
            try:
                import options
                options.record_snapshot()  
            except Exception:              
                pass
            _t.sleep(600)          
    threading.Thread(target=_w, daemon=True).start()