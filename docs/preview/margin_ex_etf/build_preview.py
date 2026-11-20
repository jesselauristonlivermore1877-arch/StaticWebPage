# -*- coding: utf-8 -*-
"""上市台股扣除 ETF 資券進出（預覽用，雲端新12，2026-11-20）

用法：python build_preview.py <原始資料夾> <輸出 json>
原始資料夾放證交所每日兩支檔（程式不打網路）：
  mi_YYYYMMDD.json  ＝ MI_MARGN selectType=ALL（逐檔融資／融券張數＋全市場融資金額）
  px_YYYYMMDD.json  ＝ MI_INDEX type=ALLBUT0999（逐檔收盤、成交金額、成交股數）

口徑：
  ETF ＝ 代號 00 開頭（證交所 MI_MARGN selectType=0099P 的 ETF 類別合計與此一致，程式會比對）
  扣除 ETF 融資餘額（張）、融券餘額（張）＝ 逐檔加總，證交所直接公布，不是估算
  扣除 ETF 融資金額（億）＝ 證交所公布全市場融資金額 − ETF 融資金額估算
     證交所只公布全市場融資金額，不分股票／ETF，所以 ETF 那塊必須估：
     逐檔追蹤：今日金額 ＝ 昨日金額 ×（今日餘額 − 今日買進）÷ 昨日餘額 ＋ 今日買進張 × 1000 × 當日均價 × 60%
     （起點那天用 餘額 × 收盤 × 60%；均價 ＝ 成交金額 ÷ 成交股數）
     同一套算法套在「全部證券」上，跟證交所公布的全市場融資金額比，誤差寫在頁面上當驗證。
  扣除 ETF 維持率 ＝ Σ 股票融資張 × 1000 × 收盤 ÷ 扣除 ETF 融資金額（跟本站現有算法同一套，只換範圍）
"""
import json, os, sys

RATIO = 0.6
TW_L2 = {'00631L', '00663L', '00675L', '00685L'}   # 台股正2（台灣50正2、臺灣加權正2、富邦臺灣加權正2、群益臺灣加權正2）


def etf_group(code):
    if code in TW_L2:
        return '台股正2'
    t = code[-1]
    return {'L': '其他槓桿', 'R': '反向', 'A': '主動型', 'B': '債券型'}.get(t, '股票型（市值、高息等）')


def num(s):
    s = str(s).replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


_NPZ = {}


def npz_px(d):
    """本站日K庫 data/bars/daily.npz（含 ETF）當天收盤與均價；沒有那天回傳空"""
    if not _NPZ:
        import numpy as np
        z = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../data/bars/daily.npz'), allow_pickle=True)
        _NPZ.update(codes=[str(c) for c in z['codes']], dates=[str(x).replace('-', '') for x in z['dates']], close=z['close'], vol=z['vol'], amt=z['amt'])
    if d not in _NPZ['dates']:
        return {}, {}
    i = _NPZ['dates'].index(d); cl, vw = {}, {}
    for j, c in enumerate(_NPZ['codes']):
        x = float(_NPZ['close'][i, j]); v = float(_NPZ['vol'][i, j]); a = float(_NPZ['amt'][i, j])
        if x == x and x > 0:
            cl[c] = x
            if v == v and a == a and v > 0 and a > 0:
                vw[c] = a / v
    return cl, vw


def load_day(R, d):
    """融資用 MI_MARGN；價格優先用證交所 MI_INDEX（px_ 檔），沒有就用本站日K庫"""
    mi = json.load(open(os.path.join(R, f'mi_{d}.json')))
    pf = os.path.join(R, f'px_{d}.json')
    px = json.load(open(pf)) if os.path.exists(pf) else {}
    if not px.get('tables'):
        px = {}
    if mi.get('stat') != 'OK' or not mi.get('tables'):
        return None
    tot = mi['tables'][0]['data']
    day = {'amt_all': num(tot[2][5]) * 1000 / 1e8, 'lots_all': num(tot[0][5]), 'short_all': num(tot[1][5]), 'rows': {}}
    close, vwap = {}, {}
    for tb in px.get('tables', []):
        if tb.get('fields') and tb['fields'][0] == '證券代號':
            for r in tb['data']:
                c = r[0].strip(); cl = num(r[8]); sh = num(r[2]); am = num(r[4])
                if cl:
                    close[c] = cl
                if sh and am:
                    vwap[c] = am / sh
    if not close:
        close, vwap = npz_px(d)
        day['px_src'] = 'npz'
    if not close:
        return None
    for r in mi['tables'][1]['data']:
        c = r[0].strip()
        if not c or c == '合計':
            continue
        day['rows'][c] = {'name': r[1].strip(), 'buy': num(r[2]) or 0, 'prev': num(r[5]) or 0, 'bal': num(r[6]) or 0, 'short': num(r[12]) or 0,
                          'close': close.get(c), 'vwap': vwap.get(c) or close.get(c)}
    return day


def main(R, out):
    def ok(f):
        try:
            return bool(json.load(open(os.path.join(R, f))).get('tables'))
        except Exception:
            return False
    days = sorted(f[3:11] for f in os.listdir(R) if f.startswith('mi_') and ok(f))
    A, last_px, res = {}, {}, []
    for d in days:
        day = load_day(R, d)
        if not day:
            print(f'  · {d} 原始檔不完整，跳過'); continue
        g = {k: {'lots': 0, 'short': 0, 'mv': 0.0, 'amt': 0.0, 'nopx': 0} for k in ('stk', 'etf')}
        grp, top = {}, []
        first = not A
        for c, r in day['rows'].items():
            k = 'etf' if c.startswith('00') else 'stk'
            px = r['close'] or last_px.get(c)
            if r['close']:
                last_px[c] = r['close']
            if first or c not in A:
                a = r['bal'] * 1000 * (px or 0) * RATIO
            else:
                keep = max(r['bal'] - r['buy'], 0)
                a = (A[c] * keep / r['prev'] if r['prev'] else 0) + r['buy'] * 1000 * (r['vwap'] or px or 0) * RATIO
            A[c] = a
            x = g[k]; x['lots'] += r['bal']; x['short'] += r['short']; x['amt'] += a / 1e8
            if px:
                x['mv'] += r['bal'] * 1000 * px / 1e8
            if k == 'etf':
                gg = grp.setdefault(etf_group(c), {'lots': 0, 'mv': 0.0, 'amt': 0.0, 'n': 0})
                mvc = r['bal'] * 1000 * (px or 0) / 1e8
                gg['lots'] += r['bal']; gg['mv'] += mvc; gg['amt'] += a / 1e8; gg['n'] += 1 if r['bal'] else 0
                top.append([c, r['name'], int(r['bal']), round(mvc, 2), round(a / 1e8, 2)])
            elif r['bal']:
                x['nopx'] += 1
        model_all = g['stk']['amt'] + g['etf']['amt']
        amt_ex = day['amt_all'] - g['etf']['amt']
        res.append({'date': f'{d[:4]}-{d[4:6]}-{d[6:]}', 'amt_all': round(day['amt_all'], 2), 'model_all': round(model_all, 2),
                    'model_err_pct': round((model_all / day['amt_all'] - 1) * 100, 2),
                    'etf_amt_est': round(g['etf']['amt'], 2), 'amt_ex': round(amt_ex, 2),
                    'mv_ex': round(g['stk']['mv'], 2), 'mv_etf': round(g['etf']['mv'], 2),
                    'maint_ex': round(g['stk']['mv'] / amt_ex * 100, 2),
                    'maint_all': round((g['stk']['mv'] + g['etf']['mv']) / day['amt_all'] * 100, 2),
                    'lots_ex': int(g['stk']['lots']), 'lots_etf': int(g['etf']['lots']),
                    'short_ex': int(g['stk']['short']), 'short_etf': int(g['etf']['short']),
                    'chk_lots': int(g['stk']['lots'] + g['etf']['lots'] - day['lots_all']),
                    'chk_short': int(g['stk']['short'] + g['etf']['short'] - day['short_all']),
                    'nopx': g['stk']['nopx'] + g['etf']['nopx'],
                    'grp': {kk: {'lots': int(v['lots']), 'mv': round(v['mv'], 2), 'amt': round(v['amt'], 2), 'n': v['n']} for kk, v in grp.items()},
                    'top': sorted(top, key=lambda t: -t[3])[:15]})
    for i in range(1, len(res)):
        res[i]['chg_ex'] = round(res[i]['amt_ex'] - res[i - 1]['amt_ex'], 2)
        res[i]['chg_all'] = round(res[i]['amt_all'] - res[i - 1]['amt_all'], 2)
    print('日期        全市場金額 模型全市場 誤差%  ETF估算  扣ETF金額  增減     扣ETF維持率 含ETF維持率 股票融資張  股票融券張 張數核對')
    for x in res[-25:]:
        print(f"{x['date']} {x['amt_all']:9.1f} {x['model_all']:9.1f} {x['model_err_pct']:6.2f} {x['etf_amt_est']:7.1f} {x['amt_ex']:9.1f} "
              f"{x.get('chg_ex', 0):8.2f} {x['maint_ex']:9.2f} {x['maint_all']:9.2f} {x['lots_ex']:10d} {x['short_ex']:9d} {x['chk_lots']},{x['chk_short']}")
    print('\nETF 分組（最後一天）：')
    for kk, v in sorted(res[-1]['grp'].items(), key=lambda t: -t[1]['mv']):
        print(f"  {kk:12s} 張 {v['lots']:>9,d}  市值 {v['mv']:7.1f} 億  估算金額 {v['amt']:6.1f} 億")
    for t in res[-1]['top'][:8]:
        print('  ', t)
    json.dump({'rows': res, 'ratio': RATIO, 'days': len(res)}, open(out, 'w'), ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
