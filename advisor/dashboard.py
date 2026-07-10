"""儀表板產生器:把每日執行結果注入單一自足式 HTML(無外部相依、支援深淺色)。

輸出檔可直接開啟、發佈到 GitHub Pages、或存成 Cowork artifact。
資料以 <script type="application/json"> 嵌入;動態文字一律用 textContent 寫入 DOM,
新聞標題等外部字串不會被當成 HTML 解析。
"""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "dashboard_template.html"


def build_dashboard(run: dict, out_path: Path) -> Path:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(run, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = template.replace("__RUN_DATA__", payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
