# -*- coding: utf-8 -*-
"""
drop_weekend_history.py ─ 刪掉週末重複的歷史快照，並重算 index.json
==========================================================================
放在  C:\\Users\\user\\Documents\\GitHub\\StaticWebPage  底下，
在那個資料夾開 CMD 跑：

    python drop_weekend_history.py

先跑一次看它印什麼（預設是預覽，不會刪）。確認無誤再：

    python drop_weekend_history.py --apply

只有「跟前一交易日逐欄完全相同」的才會被刪。實測 08-08 / 08-09 / 08-15
那三支各有 1~2 個欄位對不上（重抓造成的小數差、或當班多抓到一點東西），
所以預設會保留它們。確定連那三支也要清掉就加 --force：

    python drop_weekend_history.py --apply --force

它做的事：
  ① 逐支檢查候選檔，跟「前一個交易日那支」逐欄比對
     —— 只有在**實質欄位完全相同**（確定是複製品）時才列入刪除
  ② 刪完立刻重算 index.json（不然 index 會指到不存在的檔）
  ③ 印出刪了哪幾支、index 從幾天變成幾天

⚠️ 它不會 git add / commit / push，那三步你自己下。
==========================================================================
"""
import glob
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HDIR = os.path.join(HERE, "data", "history")

# 這四支是實測出來的週末重複點（2026-08-30 量測）
CAND = ["2026-08-08", "2026-08-09", "2026-08-15", "2026-08-30"]

# 這幾個欄位相同就代表是複製品。date / sector_score 不算 ——
# date 本來就不同，sector_score 每班重算會有微幅差異。
KEYS = ["taiex", "otc", "breadth", "margin_balance", "feel",
        "fut_inst", "opt_cp", "retail", "pcr", "inst_date", "etf_holdings"]


def load(p):
    try:
        return json.loads(io.open(p, encoding="utf-8").read())
    except Exception as e:
        print(f"      讀不到 {os.path.basename(p)}：{type(e).__name__}: {e}")
        return None


def stems():
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(HDIR, "*.json"))
                  if os.path.basename(p) != "index.json")


def main():
    apply = "--apply" in sys.argv
    force = "--force" in sys.argv
    print("=" * 70)
    print("drop_weekend_history" + ("　【真的刪除】" if apply else "　（預覽，不會刪）"))
    print("=" * 70)
    if not os.path.isdir(HDIR):
        print(f"✗✗ 找不到 {HDIR}")
        print("   請在 StaticWebPage 資料夾裡跑這支程式。")
        return 1

    all_stems = stems()
    print(f"目前 history 有 {len(all_stems)} 天：{all_stems[0]} → {all_stems[-1]}\n")

    todo = []
    for d in CAND:
        p = os.path.join(HDIR, d + ".json")
        if not os.path.exists(p):
            print(f"  · {d}　不存在，跳過")
            continue
        prev = [s for s in all_stems if s < d]
        if not prev:
            print(f"  ⚠ {d}　前面沒有任何一天可以比對，保留")
            continue
        pv = prev[-1]
        a, b = load(os.path.join(HDIR, pv + ".json")), load(p)
        if not a or not b:
            print(f"  ⚠ {d}　比對失敗，保留")
            continue
        diff = [k for k in KEYS if a.get(k) != b.get(k)]
        if diff and not force:
            print(f"  ⚠ {d}　跟 {pv} 有 {len(diff)} 個欄位不同 {diff[:4]} —— 不是複製品，保留")
            print(f"        （它仍然是週末那天存的。確定要刪就加 --force）")
            continue
        if diff:
            print(f"  ! {d}　跟 {pv} 有 {len(diff)} 個欄位不同 {diff[:4]}，--force 照刪")
            todo.append(p)
            continue
        print(f"  ✓ {d}　與 {pv} 的 {len(KEYS)} 個實質欄位完全相同 → 刪除")
        todo.append(p)

    if not todo:
        print("\n沒有要刪的。")
        return 0

    if not apply:
        print(f"\n預覽模式，沒有動任何檔案。要真的刪，跑：")
        print("    python drop_weekend_history.py --apply")
        return 0

    for p in todo:
        os.remove(p)
    ds = stems()
    io.open(os.path.join(HDIR, "index.json"), "w", encoding="utf-8").write(
        json.dumps({"dates": ds, "count": len(ds),
                    "first": ds[0] if ds else None,
                    "last": ds[-1] if ds else None}, ensure_ascii=False))
    print(f"\n✓ 刪了 {len(todo)} 支，index.json 重算完成："
          f"{len(all_stems)} 天 → {len(ds)} 天（{ds[0]} → {ds[-1]}）")
    print("\n接下來自己下這三行（或用 GitHub Desktop）：")
    print("    git add -A")
    print('    git commit -m "history: drop weekend duplicate snapshots"')
    print("    git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
