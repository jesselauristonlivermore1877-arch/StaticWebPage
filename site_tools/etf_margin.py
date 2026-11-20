# -*- coding: utf-8 -*-
"""融資維持率改成「含 ETF」同口徑（雲端新12，2026-11-20；【新】總指揮依 Evans 指定，基準＝財經M平方）

為什麼：tools/mkt_overlay.py 的維持率分子讀 data/bars/margin.npz、margin_otc.npz，這兩個檔只有股票、沒有 ETF；
        分母卻是證交所／櫃買公布的融資金額（含 ETF）→ 分子分母口徑不一致，上市 11/19 少算約 11.5 個百分點。
定義（同財經M平方）：融資維持率 ＝ Σ 各檔融資餘額張數 × 1000 × 收盤（股票＋ETF）÷ 融資金額（官方公布，含 ETF）
     M平方原文：「將上市櫃透過融資買進的股票（包含 ETF）除以上市櫃的融資餘額」
     核對：上市 11/19 147.93 vs M平方 147.9、11/20 140.43 vs 140.4；上櫃 11/19 139.59 vs 139.59、11/20 131.94 vs 131.94

三個模式（都只讀寫 StaticWebPage 自己的檔）：
  land <site>       每天一次：證交所 OpenAPI MI_MARGN（只有最新一天，一個請求）＋櫃買 margin/balance（當天，一個請求）
                    → 只留 ETF（代號 00 開頭）逐檔 → data/margin_etf/twse_YYYY-MM-DD.json、tpex_YYYY-MM-DD.json
  backfill <site> --start YYYY-MM-DD [--end ...] [--sleep 6]
                    歷史慢速回補（GitHub Actions 用；每次請求間隔 ≥ 5 秒；被擋就停，不重打）
  patch <site>      把 ETF 融資市值加進 docs/data/mkt_overlay.json 的上市維持率（與上櫃本站估算）分子，
                    重算 last、pct、wave.maint_low；
                    上市有任何一天缺 ETF 檔就整段不改（網站沿用舊值）；11/19、11/20 跟 M平方差 > 0.2 個百分點也不改。
"""
import json, os, sys, time, urllib.request, urllib.error

UA = {'User-Agent': 'Mozilla/5.0 (StaticWebPage daily build)'}
# 基準（Evans 11-20 提供財經M平方截圖數字，總指揮轉述）：核對用，差 > TOL 就不改
MM_REF = {'twse': {'2026-11-19': 147.9, '2026-11-20': 140.4}, 'otc': {'2026-11-19': 139.59, '2026-11-20': 131.94}}
TOL = 0.2
ETF_RATIO = 0.6   # ETF 融資推估成數（同預覽 build_preview.py RATIO）


def num(s):
    s = str(s).replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def get_json(url, tries=3, wait=6):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                body = r.read().decode('utf-8', 'replace')
            if body.lstrip().startswith('<'):
                raise RuntimeError('回傳 HTML（可能被擋）：' + body[:80].replace('\n', ' '))
            return json.loads(body)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f'  · 第 {i + 1} 次失敗：{e}')
            if 'HTML' in str(e):
                break          # 被擋就不再重打
            time.sleep(wait)
    raise RuntimeError(f'{url} 取不到：{last}')


def etf_dir(site):
    d = os.path.join(site, 'data', 'margin_etf')
    os.makedirs(d, exist_ok=True)
    return d


def write_full(site, mkt, date, src, rows):
    """🟢 11-20 夜（【新】總指揮）：同一個回應裡的全部逐檔（股票＋ETF）另存，給個股／族群融資維持率用（要融資買進、賣出、償還），
    不必再打一輪證交所。欄位同 ETF 檔：買進、賣出、現金償還、前日餘額、今日餘額、融券今日餘額（張）。"""
    d = os.path.join(site, 'data', 'margin_full'); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f'{mkt}_{date}.json')
    json.dump({'date': date, 'src': src, 'fields': ['買進', '賣出', '現金償還', '前日餘額', '今日餘額', '融券今日餘額'],
               'rows': {c: [int(x) for x in r] for c, r in rows.items()}}, open(p, 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f'  ✓ {p}：全部 {len(rows)} 檔')


def write(site, mkt, date, src, rows):
    p = os.path.join(etf_dir(site), f'{mkt}_{date}.json')
    json.dump({'date': date, 'src': src, 'fields': ['買進', '賣出', '現金償還', '前日餘額', '今日餘額', '融券今日餘額'],
               'rows': rows, 'lots': int(sum(r[4] for r in rows.values()))}, open(p, 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f'  ✓ {p}：ETF {len(rows)} 檔、融資 {int(sum(r[4] for r in rows.values())):,} 張')


# ---------------- 上市 ----------------
def twse_rows_rwd(js, etf_only=True):
    rows = {}
    for r in js['tables'][1]['data']:
        c = r[0].strip()
        if c and c != '合計' and (c.startswith('00') or not etf_only):
            rows[c] = [num(r[2]), num(r[3]), num(r[4]), num(r[5]), num(r[6]), num(r[12])]
    return rows


def twse_date_of_openapi(site, js):
    """OpenAPI 沒有日期欄 → 用股票逐檔融資餘額比對 data/bars/margin.npz 最近幾天，全部一致的那天就是資料日"""
    import numpy as np
    z = np.load(os.path.join(site, 'data', 'bars', 'margin.npz'), allow_pickle=True)
    codes = [str(c) for c in z['codes']]
    oa = {x['股票代號']: num(x['融資今日餘額']) for x in js}
    for i in range(len(z['dates']) - 1, max(-1, len(z['dates']) - 6), -1):
        m = z['margin'][i]; ok = bad = 0
        for j, c in enumerate(codes):
            if c in oa and m[j] == m[j]:
                ok += oa[c] == m[j]; bad += oa[c] != m[j]
        if ok > 900 and bad <= 3:
            return str(z['dates'][i])
    return None


def land(site):
    import numpy as np
    zd = str(np.load(os.path.join(site, 'data', 'bars', 'margin.npz'), allow_pickle=True)['dates'][-1])
    if os.path.exists(os.path.join(etf_dir(site), f'twse_{zd}.json')):
        print(f'  · 上市 {zd} 已落地，不再打 OpenAPI')
    else:
        land_twse(site)
    try:
        z = np.load(os.path.join(site, 'data', 'bars', 'margin_otc.npz'), allow_pickle=True)
        d = str(z['dates'][-1])
        if os.path.exists(os.path.join(etf_dir(site), f'tpex_{d}.json')):
            print(f'  · 上櫃 {d} 已落地，不再打櫃買')
        else:
            tpex_land(site, d)
    except Exception as e:  # noqa: BLE001
        print('  ⚠ 上櫃 ETF 融資落地失敗：', e)


def land_twse(site):
    try:
        js = get_json('https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN')
        d = twse_date_of_openapi(site, js)
        if not d:
            print('  ⚠ 上市 OpenAPI 資料日對不上 margin.npz 最近 5 天，不落地')
        else:
            rows = {x['股票代號']: [num(x['融資買進']), num(x['融資賣出']), num(x['融資現金償還']), num(x['融資前日餘額']),
                                    num(x['融資今日餘額']), num(x['融券今日餘額'])] for x in js}
            write(site, 'twse', d, 'openapi.twse.com.tw/v1/exchangeReport/MI_MARGN', {c: v for c, v in rows.items() if c.startswith('00')})
            write_full(site, 'twse', d, 'openapi.twse.com.tw/v1/exchangeReport/MI_MARGN', rows)
    except Exception as e:  # noqa: BLE001
        print('  ⚠ 上市 ETF 融資落地失敗：', e)


def tpex_land(site, d):
    js = get_json(f'https://www.tpex.org.tw/www/zh-tw/margin/balance?date={d.replace("-", "%2F")}&response=json')
    t = js['tables'][0]
    if t.get('date', '').replace('/', '') != f'{int(d[:4]) - 1911}{d[5:7]}{d[8:]}':
        print(f'  ⚠ 櫃買回傳資料日 {t.get("date")} ≠ {d}，不落地'); return
    allr = {r[0].strip(): [num(r[3]), num(r[4]), num(r[5]), num(r[2]), num(r[6]), num(r[14])] for r in t['data'] if r[0].strip()}
    write(site, 'tpex', d, 'www.tpex.org.tw/www/zh-tw/margin/balance', {c: v for c, v in allr.items() if c.startswith('00')})
    write_full(site, 'tpex', d, 'www.tpex.org.tw/www/zh-tw/margin/balance', allr)


def backfill(site, start, end, sleep):
    import numpy as np
    b = np.load(os.path.join(site, 'data', 'bars', 'daily.npz'), allow_pickle=True)
    days = [str(x) for x in b['dates'] if start <= str(x) <= end]
    print(f'回補 {len(days)} 個交易日（{start}～{end}），間隔 {sleep} 秒')
    for d in days:
        for mkt in ('twse', 'tpex'):
            if os.path.exists(os.path.join(etf_dir(site), f'{mkt}_{d}.json')) and os.path.exists(os.path.join(site, 'data', 'margin_full', f'{mkt}_{d}.json')):
                continue
            try:
                if mkt == 'twse':
                    js = get_json(f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d.replace("-", "")}&selectType=ALL&response=json', tries=1)
                    if js.get('stat') != 'OK' or len(js.get('tables', [])) < 2:
                        print(f'  · {d} 上市無資料（{js.get("stat")}）')
                    else:
                        write(site, 'twse', d, 'www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN', twse_rows_rwd(js))
                        write_full(site, 'twse', d, 'www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN', twse_rows_rwd(js, False))
                else:
                    tpex_land(site, d)
            except Exception as e:  # noqa: BLE001
                print(f'  ✗ {d} {mkt}：{e}')
                if 'HTML' in str(e):
                    print('  被擋，停止回補（不重打，下次再補）'); return
            time.sleep(sleep)


# ---------------- 修正 mkt_overlay ----------------
def etf_mv(site, mkt, d, close, bc):
    p = os.path.join(site, 'data', 'margin_etf', f'{mkt}_{d}.json')
    if not os.path.exists(p):
        return None
    rows = json.load(open(p))['rows']; v = 0.0; miss = 0
    for c, r in rows.items():
        x = float(close[bc[c]]) if c in bc else float('nan')
        if x == x:
            v += r[4] * 1000 * x
        elif r[4]:
            miss += 1
    return v / 1e8, miss


def adjust(site, M):
    """把 ETF 融資市值加進 maint（tools/mkt_overlay.maint() 的回傳 dict，記憶體內直接改）；成功回 0，沒改回 1。
    🟢 11-21（雲端新14）：從 patch() 拆出來，讓選股 EDM（tools/pick_edm_ext.py margin_credit，daily 裡比 patch 早跑）用同一段算法。"""
    import numpy as np
    T = M['twse']
    if T.get('etf_in'):
        print('已經是含 ETF 版（etf_in），不重複修正'); return 0
    b = np.load(os.path.join(site, 'data', 'bars', 'daily.npz'), allow_pickle=True)
    BD = [str(x) for x in b['dates']]; bc = {str(c): i for i, c in enumerate(b['codes'])}
    # 上市：每一天都要有 ETF 檔才改
    new, lack = [], []
    for r in T['rows']:
        d, mt, ix, amt = r[0], r[1], r[2], r[3]
        e = etf_mv(site, 'twse', d, b['close'][BD.index(d)], bc) if d in BD else None
        if e is None or not amt:
            lack.append(d); continue
        new.append([d, round(mt + e[0] / amt * 100, 2), ix, amt])
    if lack:
        print(f'⚠ 上市 ETF 融資歷史還缺 {len(lack)} 天（{lack[0]}～{lack[-1]}），整段不改（網站沿用舊值）')
        return 1
    for d, ref in MM_REF['twse'].items():
        x = next((r for r in new if r[0] == d), None)
        if x and abs(x[1] - ref) > TOL:
            print(f'✗ 上市 {d} 本站 {x[1]} vs M平方 {ref} 差 {x[1] - ref:+.2f} > {TOL}，不改'); return 1
        if x:
            print(f'  ✓ 上市 {d} 本站 {x[1]} vs M平方 {ref}（差 {x[1] - ref:+.2f}）')
    # 🟢 11-20 夜（【新】總指揮，Evans 選 A 版：卡上第二行「扣除 ETF」）：ETF 融資金額逐檔推估（同預覽 build_preview.py 算法）
    #   今日金額＝昨日金額×(今日餘額−今日買進)÷昨日餘額＋今日買進張×1000×當日均價×成數；起點＝餘額×收盤×成數
    #   扣除 ETF 維持率＝(含 ETF 融資市值 − ETF 融資市值) ÷ (融資金額 − ETF 融資金額推估)；推估值，頁面註明
    A, ex = {}, {}
    for r in new:
        d = r[0]; i = BD.index(d)
        rows = json.load(open(os.path.join(site, 'data', 'margin_etf', f'twse_{d}.json')))['rows']
        cl, vo, am = b['close'][i], b['vol'][i], b['amt'][i]
        amt_e = mv_e = 0.0
        for c, x in rows.items():
            buy, prev, bal = x[0], x[3], x[4]
            k = bc.get(c)
            px = float(cl[k]) if k is not None and cl[k] == cl[k] else float('nan')
            vw = float(am[k]) / float(vo[k]) if k is not None and vo[k] == vo[k] and vo[k] > 0 and am[k] == am[k] and am[k] > 0 else px
            if px != px:
                px = vw
            if px != px:
                A[c] = A.get(c, 0.0); continue
            if c not in A:
                a = bal * 1000 * px * ETF_RATIO
            else:
                a = (A[c] * max(bal - buy, 0) / prev if prev else 0.0) + buy * 1000 * vw * ETF_RATIO
            A[c] = a; amt_e += a / 1e8; mv_e += bal * 1000 * px / 1e8
        mv_all = r[1] * r[3] / 100
        ex[d] = (round((mv_all - mv_e) / (r[3] - amt_e) * 100, 2), round(r[3] - amt_e, 1), round(amt_e, 1))
    for r in new:
        r.extend(ex[r[0]])
    T['fields'] = ['date', 'est', 'taiex', 'margin_yi', 'est_ex', 'margin_ex_yi', 'etf_amt_yi']
    T['ex_how'] = ('扣除 ETF＝股票（代號 00 開頭以外）融資市值 ÷（上市融資金額 − ETF 融資金額推估）；證交所只公布全市場融資金額、不分股票／ETF，'
                   'ETF 那塊由本站逐檔推估（新買進按當日均價 × %d%%、舊部位依剩餘張數保留，起點 %s），所以扣除 ETF 是大概值' % (round(ETF_RATIO * 100), new[0][0]))
    T['rows'] = new
    vals = [r[1] for r in new]
    T['last'] = new[-1]
    T['pct'] = round(100 * sum(v <= vals[-1] for v in vals) / len(vals))
    T['how'] = 'Σ 各檔融資張數 × 1000 × 收盤（股票＋ETF）÷ 上市融資金額（證交所 MI_MARGN）；定義同財經M平方：融資買進市值（含 ETF）÷ 融資金額；官方未公布上市整體維持率'
    T['etf_in'] = True
    W = M.get('wave')
    if W and W.get('high') and W.get('low'):
        ds = [r[0] for r in new]
        i0 = next((i for i, x in enumerate(ds) if x >= W['high']['date']), None)
        il = next((i for i, x in enumerate(ds) if x >= W['low']['date']), len(ds) - 1)
        if i0 is not None:
            seg = range(i0, min(len(ds), il + 6))
            k = min(seg, key=lambda i: new[i][1]); v = new[k][1]
            j = next((i for i in range(k - 1, -1, -1) if new[i][1] < v), None)
            W['maint_low'] = {'date': ds[k], 'val': v, 'since': ds[j + 1] if j is not None else ds[0], 'taiex': new[k][2],
                              'margin_yi': new[k][3], 'chg_pt': round(v - new[k - 1][1], 2) if k else None}
            W['rule'] = W.get('rule', '').replace('上市融資維持率（本站估算）', '上市融資維持率（本站估算，含 ETF）')
    # 上櫃本站估算（est 欄）：有 ETF 檔的那天才加；沒有就保留原值並註記
    O = M.get('otc')
    if O and O.get('rows'):
        fi = O.get('fields', [])
        ie, im = (fi.index('est'), fi.index('margin_yi')) if 'est' in fi and 'margin_yi' in fi else (2, 4)
        n_ok = 0
        for r in O['rows']:
            if r[ie] is None or not r[im] or r[0] not in BD:
                continue
            e = etf_mv(site, 'tpex', r[0], b['close'][BD.index(r[0])], bc)
            if e:
                r[ie] = round(r[ie] + e[0] / r[im] * 100, 2); n_ok += 1
        for d, ref in MM_REF['otc'].items():
            x = next((r for r in O['rows'] if r[0] == d), None)
            if x and x[ie] is not None:
                print(f'  · 上櫃 {d} 本站估算 {x[ie]} vs M平方 {ref}（差 {x[ie] - ref:+.2f}）')
        O['est_etf_days'] = n_ok
    print(f'✓ 上市 {len(new)} 天改含 ETF，最新 {new[-1][0]} {new[-1][1]}%，第 {T["pct"]} 百分位')
    return 0


def patch(site):
    pj = os.path.join(site, 'docs', 'data', 'mkt_overlay.json')
    J = json.load(open(pj)); T = J['maint']['twse']
    if T.get('etf_in'):
        print('已經是含 ETF 版（etf_in），不重複修正'); return 0
    rc = adjust(site, J['maint'])
    if rc:
        return rc
    tmp = pj + '.tmp'
    json.dump(J, open(tmp, 'w'), ensure_ascii=False)   # 先寫暫存檔，成功才換掉（寫到一半出錯不會留下壞檔）
    json.load(open(tmp)); os.replace(tmp, pj)
    print(f'✓ 已修正 {pj}')
    return 0


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] not in ('land', 'backfill', 'patch'):
        print(__doc__); sys.exit(2)
    site = a[1]
    if a[0] == 'land':
        land(site)
    elif a[0] == 'backfill':
        kw = dict(zip(a[2::2], a[3::2]))
        backfill(site, kw.get('--start', '2025-09-22'), kw.get('--end', '9999-12-31'), max(5.0, float(kw.get('--sleep', 6))))
    else:
        sys.exit(patch(site))
