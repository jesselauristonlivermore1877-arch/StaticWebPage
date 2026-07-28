# -*- coding: utf-8 -*-
import os
import json
import datetime
import gc

import screener
import engines
import options
import active_etf

def build():
    print("啟動網頁靜態烘焙...")
    
    # 確保選股資料庫已就緒
    screener._ensure()
    
    # 建立資料容器
    data = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "asof": screener._data_date(),
        "sections": {}
    }
    
    # 依序呼叫既有模組（與 LINE 端完全相同的函數，確保口徑一致）
    print("  抓取 [盤勢]...")
    data["sections"]["盤勢"] = screener.build_market_structure()
    print("  抓取 [量榜]...")
    data["sections"]["量榜"] = screener.build_volume_ranking()
    print("  抓取 [轉強]...")
    data["sections"]["轉強"] = screener.build_strength_ranking()
    print("  抓取 [回檔]...")
    data["sections"]["回檔"] = screener.build_drawdown_overview()
    print("  抓取 [籌碼]...")
    data["sections"]["籌碼"] = engines.get_inst_full()
    print("  抓取 [期權籌碼]...")
    data["sections"]["期權籌碼"] = options.get_option_chips()
    print("  抓取 [法人結構]...")
    data["sections"]["法人結構"] = screener.build_inst_structure()
    print("  抓取 [外資]...")
    data["sections"]["外資"] = engines.get_side_blocks(side="foreign")
    print("  抓取 [投信]...")
    data["sections"]["投信"] = engines.get_side_blocks(side="trust")
    print("  抓取 [信用]...")
    data["sections"]["信用"] = engines.get_margin_blocks()
    print("  抓取 [主動ETF]...")
    data["sections"]["主動ETF"] = active_etf.get_active_etf_blocks()

    gc.collect()

    # 讀取樣板並替換資料
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 安全地轉為 JSON，並防禦 script 標籤截斷
    json_str = json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>")
    html = html.replace("__DATA__", json_str)

    # 寫出靜態檔至 docs/index.html (供 GitHub Pages 讀取)
    out_dir = os.path.join(os.path.dirname(__file__), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 網頁建置完成: {out_path} (約 {len(html)/1024:.1f} KB)")
    print("   → git commit + push 後，GitHub Pages 點開即 0 秒渲染。")

if __name__ == "__main__":
    build()