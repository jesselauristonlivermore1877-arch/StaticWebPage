# -*- coding: utf-8 -*-
"""全市場融資金額（上市／上櫃）逐日歷史回補 —— 雲端新19，2026-11-21；【新】總指揮派工（Evans：「融資禮拜五是歷史第一這個 EDM 有做嗎」）

用途：量化 EDM「融資大減」（CustomerServiceANDSales tools/pick_edm_1116.py mf_rank）把歷史排行樣本拉長（原本只從 2025-09-22 起）。
落地 data/margin_total/<twse|otc>.json（data/ 不對外），只存官方彙總列：
  上市：證交所 MI_MARGN（selectType=MS）「融資金額(仟元)」列的前日餘額、今日餘額＋「融資(交易單位)」今日餘額（張）
        https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=YYYYMMDD&selectType=MS&response=json（2001-01-01 起才有）
  上櫃：櫃買 https://www.tpex.org.tw/www/zh-tw/margin/balance?date=YYYY/MM/DD&response=json → tables[0].summary
        「融資金(仟元)」列第 3 欄＝前資餘額、第 7 欄＝資餘額；「合計(張)」列第 7 欄＝融資張數（2007-01 前後起才有；更早 summary 是空的）
檔案格式：{"src": 端點, "days": {日期: [前日餘額億, 今日餘額億, 今日融資張數]}, "empty": [查過但休市／沒資料的日期], "floor": 確認沒有更早資料的日期或 null}

做法（慢速、不繞封鎖）：
  從檔案裡最早的一天往回（沒有檔就從今天往回）逐個「週一～週五」查，每發間隔 ≥ --gap 秒（預設 6）；
  遇到 HTTP 307／403／429、回非 JSON（被轉址擋）→ 立刻停、寫檔、exit 3（workflow 看到 3 就不再接著跑）。
  連續 --stop-empty 個工作日都沒資料（預設 40 ≈ 兩個月）→ 視為已到資料起點，記 floor、exit 0。
  --minutes 到了就寫檔 exit 0（workflow 分段 commit＋push 後再接著跑下一段）。
用法：python site_tools/margin_total_backfill.py --mkt twse|otc [--until 2001-01-01] [--minutes 40] [--gap 6]
"""
import argparse, datetime as dt, json, os, sys, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SRC = {"twse": "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=%s&selectType=MS&response=json",
       "otc": "https://www.tpex.org.tw/www/zh-tw/margin/balance?date=%s&response=json"}
UNTIL = {"twse": "2001-01-01", "otc": "2006-01-01"}


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


class Blocked(Exception):
    pass


def fetch(sess, mkt, d):
    """回傳 [前日餘額億, 今日餘額億, 融資張數] 或 None（休市／沒資料）；被擋 raise Blocked"""
    q = d.strftime("%Y%m%d") if mkt == "twse" else d.strftime("%Y/%m/%d")
    r = sess.get(SRC[mkt] % q, headers=UA, timeout=30, allow_redirects=False)
    if r.status_code in (301, 302, 307, 403, 429) or r.status_code >= 500:
        raise Blocked("HTTP %d" % r.status_code)
    try:
        j = r.json()
    except ValueError:
        raise Blocked("回非 JSON：HTTP %d %s" % (r.status_code, r.text[:200].replace("\n", " ")))
    if mkt == "twse":
        if j.get("stat") != "OK":
            return None
        amt = lots = None
        for t in j.get("tables") or []:
            f = t.get("fields") or []
            ip = next((i for i, x in enumerate(f) if "前日餘額" in str(x)), None)
            it = next((i for i, x in enumerate(f) if "今日餘額" in str(x)), None)
            if ip is None or it is None:
                continue
            for row in t.get("data") or []:
                if "融資金額" in str(row[0]):
                    amt = (num(row[ip]), num(row[it]))
                elif "融資" in str(row[0]) and "交易單位" in str(row[0]):
                    lots = num(row[it])
        if not amt or amt[0] is None or amt[1] is None:
            return None
        return [round(amt[0] / 1e5, 4), round(amt[1] / 1e5, 4), lots]
    t = (j.get("tables") or [{}])[0]
    amt = next((x for x in t.get("summary") or [] if "融資金" in str(x[1])), None)
    lots = next((x for x in t.get("summary") or [] if "合計" in str(x[1])), None)
    if not amt or num(amt[2]) is None or num(amt[6]) is None:
        return None
    return [round(num(amt[2]) / 1e5, 4), round(num(amt[6]) / 1e5, 4), num(lots[6]) if lots else None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mkt", required=True, choices=["twse", "otc"])
    ap.add_argument("--site", default=".")
    ap.add_argument("--until", default=None, help="最早補到哪天（預設上市 2001-01-01、上櫃 2006-01-01）")
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--gap", type=float, default=6)
    ap.add_argument("--stop-empty", type=int, default=40)
    a = ap.parse_args()
    if a.gap < 6:
        raise SystemExit("✗ 間隔至少 6 秒（總指揮規格）")
    p = os.path.join(a.site, "data", "margin_total", a.mkt + ".json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    H = json.load(open(p)) if os.path.exists(p) else {"src": SRC[a.mkt], "days": {}, "empty": [], "floor": None}
    until = dt.date.fromisoformat(a.until or UNTIL[a.mkt])
    known = set(H["days"]) | set(H["empty"])
    # 沒有檔時從 7 天前開始（最近幾天官方可能還沒公布，不要誤記成「沒資料」；近期本來就有 mkt_overlay 那份）
    start = min(known) if known else ((dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)).date() - dt.timedelta(days=7)).isoformat()
    if H.get("floor"):
        print("✓ %s 已到資料起點 %s（%d 天），不再往回補" % (a.mkt, H["floor"], len(H["days"])))
        return 0
    d = dt.date.fromisoformat(start) - (dt.timedelta(days=1) if known else dt.timedelta(0))
    t0, n_req, n_ok, run_empty, code = time.time(), 0, 0, 0, 0
    sess = requests.Session()

    def save():
        H["days"] = dict(sorted(H["days"].items()))
        H["empty"] = sorted(set(H["empty"]))
        open(p + ".tmp", "w").write(json.dumps(H, ensure_ascii=False, separators=(",", ":")))
        os.replace(p + ".tmp", p)

    print("%s 從 %s 往回補到 %s（間隔 %.0f 秒、這段最多 %.0f 分鐘）" % (a.mkt, d, until, a.gap, a.minutes), flush=True)
    while d >= until:
        if time.time() - t0 > a.minutes * 60:
            print("⏸ 這段時間到（%d 發、%d 天有資料），下一段接著補" % (n_req, n_ok)); break
        if d.weekday() >= 5:
            d -= dt.timedelta(days=1); continue
        k = d.isoformat()
        if k in H["days"] or k in H["empty"]:
            d -= dt.timedelta(days=1); continue
        try:
            v = fetch(sess, a.mkt, d)
        except Blocked as e:
            print("✗ %s %s 被擋或異常回應：%s → 停（不繞過），已補的先存" % (a.mkt, k, e)); code = 3; break
        except requests.RequestException as e:
            print("✗ %s %s 連線失敗：%s %s → 停" % (a.mkt, k, type(e).__name__, e)); code = 3; break
        n_req += 1
        if v is None:
            H["empty"].append(k); run_empty += 1
            if run_empty >= a.stop_empty:
                H["floor"] = min(H["days"]) if H["days"] else k
                print("✓ 連續 %d 個工作日沒資料 → 資料起點 %s" % (run_empty, H["floor"])); break
        else:
            H["days"][k] = v; n_ok += 1; run_empty = 0
            if n_ok % 50 == 1:
                print("  %s 前日 %.2f 億 → 今日 %.2f 億（%s 張）" % (k, v[0], v[1], v[2]), flush=True)
        if n_req % 25 == 0:
            save()
        d -= dt.timedelta(days=1)
        time.sleep(a.gap)
    else:
        H["floor"] = H["floor"] or (min(H["days"]) if H["days"] else None)
        print("✓ 已補到 --until %s" % until)
    save()
    ks = sorted(H["days"])
    print("%s 共 %d 天有資料（%s～%s）、休市／無資料 %d 天；這段 %d 發、%.1f 分鐘" % (
        a.mkt, len(ks), ks[0] if ks else "", ks[-1] if ks else "", len(H["empty"]), n_req, (time.time() - t0) / 60))
    return code


if __name__ == "__main__":
    sys.exit(main())
