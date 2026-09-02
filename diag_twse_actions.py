# -*- coding: utf-8 -*-
"""
diag_twse_actions.py ─ 只從 GitHub Actions 的出口 IP 打一次。

本機那一份已經量完（八個端點兩種模式全綠），這支只補最後一塊：
同樣的網址，從 GitHub 的 IP 打會不會被擋。

所以刻意瘦身：只跑 standalone、每個網址兩次、間隔 0.6 秒，
十六個請求，半分鐘內結束。不 import engines（StaticWebPage 沒有它）。
"""
import os, sys, json, time

import requests
import urllib3
urllib3.disable_warnings()

P = lambda *a: print(*a, flush=True)
TODAY = time.strftime("%Y%m%d")
MON = time.strftime("%Y%m") + "01"

P("=" * 70)
P("環境")
P("=" * 70)
P("  python  : %s" % sys.version.split()[0])
P("  CI      : %s" % os.environ.get("GITHUB_ACTIONS", "(本機)"))
P("  runner  : %s" % os.environ.get("RUNNER_NAME", "-"))
try:
    P("  出口 IP : %s" % requests.get("https://api.ipify.org", timeout=15).text.strip())
except Exception as ex:
    P("  出口 IP : 取不到（%s）" % type(ex).__name__)
P("  台北時間: %s" % time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(time.time() + 8 * 3600)))

S = requests.Session()
S.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9",
})
for warm in ("https://www.twse.com.tw/", "https://www.tpex.org.tw/"):
    try:
        r = S.get(warm, timeout=20)
        P("  暖身 %-26s HTTP %s" % (warm, r.status_code))
    except Exception:
        try:
            r = S.get(warm, timeout=20, verify=False)
            P("  暖身 %-26s HTTP %s (verify=False)" % (warm, r.status_code))
        except Exception as ex:
            P("  暖身 %-26s X %s" % (warm, type(ex).__name__))


def GET(url):
    try:
        return S.get(url, timeout=30)
    except requests.exceptions.SSLError:
        return S.get(url, timeout=30, verify=False)


TARGETS = [
    ("FMTQIK 舊 engines:1336",
     "https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date=" + MON),
    ("FMTQIK 新 screener:1139",
     "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=%s&response=json" % MON),
    ("MI_INDEX 舊 engines:931",
     "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date=%s&type=ALLBUT0999" % TODAY),
    ("MI_5MINS_HIST 舊 engines:1417",
     "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=json&date=" + MON),
    ("權重檔 openapi build_web:775",
     "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
    ("T86 舊 engines:719",
     "https://www.twse.com.tw/fund/T86?response=json&date=" + TODAY),
    ("BFI82U 舊 engines:504",
     "https://www.twse.com.tw/fund/BFI82U?response=json&dayDate=%s&type=day" % TODAY),
    ("TPEx highlight engines:1556",
     "https://www.tpex.org.tw/openapi/v1/tpex_mainborad_highlight"),
]


def describe(txt):
    try:
        j = json.loads(txt)
    except Exception as ex:
        return "不是JSON(%s)" % type(ex).__name__
    if isinstance(j, list):
        return "list %d 列" % len(j)
    if isinstance(j, dict):
        bits = []
        if "stat" in j:
            bits.append("stat=%r" % j["stat"])
        for k in ("data", "aaData", "tables"):
            if isinstance(j.get(k), list):
                bits.append("%s %d 列" % (k, len(j[k])))
        return "dict " + (" ".join(bits) or str(list(j.keys())[:8]))
    return type(j).__name__


P("")
P("=" * 70)
P("逐個端點，各兩次")
P("=" * 70)

for label, base in TARGETS:
    P("\n-- %s" % label)
    for i in range(2):
        sep = "&" if "?" in base else "?"
        url = "%s%s_=%d%d" % (base, sep, int(time.time() * 1000), i)
        try:
            r = GET(url)
        except Exception as ex:
            P("   #%d X 例外 %s: %s" % (i + 1, type(ex).__name__, str(ex)[:120]))
            time.sleep(0.6)
            continue
        hist = ""
        if r.history:
            hist = " <-轉址 %s" % " ".join(str(h.status_code) for h in r.history)
        d = describe(r.text)
        P("   #%d HTTP %s%s | %d bytes | %s" % (i + 1, r.status_code, hist, len(r.text), d))
        if d.startswith("不是JSON") or r.status_code >= 400:
            P("      前 200 字: %r" % r.text[:200])
        time.sleep(0.6)

P("")
P("=" * 70)
P("跑完。整份貼回來。")
P("=" * 70)
