# -*- coding: utf-8 -*-
"""融資追繳門檻（整戶擔保維持率最低標準）依日期生效 —— 2026-11-23 雲端舊34

出處：證交所 115/11/23 新聞稿（交易部）「自115年11月24日起，信用交易擔保維持率最低標準由130%調降至120%」
  https://www.twse.com.tw/zh/about/news/news/content.html?8a8216d6a19afd9c01a2072d582a0593
  （PDF：/staticFiles/news/news/tsecnews/8a8216d6a19afd9c01a2073bb7af0594.pdf；程式打開核對過原文）
  - 生效：115/11/24；新聞稿沒寫期限 → 恢復或再調時在 MAINT_CALL 加一列（新的在前）
  - 範圍：信用帳戶收盤後計算的「整戶」擔保維持率（上市、上櫃股票同一帳戶一起算）；櫃買中心 11/23 新聞稿清單沒有另發，
    上櫃沿用同一門檻（若之後櫃買另訂，再分市場）
歷史資料照「當日」門檻，不改寫。網站前端同一張表：程式 repo template.html 的 MAINT_CALL；EDM：tools/pick_edm_maint.py 的 MAINT_CALL。
"""

MAINT_CALL = (('2026-11-24', 120.0), ('', 130.0))   # (生效日, 門檻%)，新的在前；'' ＝最早


def maint_call(d, mkt=None):
    """d：資料日（'2026-11-24'／'20261124'／'115/11/24' 以外的西元格式都可）；回傳當日追繳門檻（%）。mkt 保留給上市／上櫃分開時用"""
    k = ''.join(ch for ch in str(d or '') if ch.isdigit())[:8]
    for s, v in MAINT_CALL:
        s8 = s.replace('-', '')
        if not s8 or (len(k) == 8 and k >= s8):
            return v
    return 130.0


def maint_call_note():
    return '11/24 起 120%、之前 130%'


if __name__ == '__main__':
    for d in ('2026-11-20', '2026-11-23', '2026-11-24', '20261201', ''):
        print(repr(d), maint_call(d))
