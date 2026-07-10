"""決策日誌:每天一份 Markdown(給人讀)+ JSONL(給程式讀)。

核心要求:每一個標的、每一天都要有記錄 — 包含「今天決定不動作」及其原因。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

JOURNAL_DIR = Path(__file__).resolve().parent.parent / "journal"

DISCLAIMER = (
    "> ⚠️ **免責聲明**:本系統為個人研究工具,所有「建議」皆由公開資料與規則化訊號計算而成,"
    "僅供參考,不構成投資建議。投資有風險,決策與盈虧請自行負責;重大決定建議諮詢持牌專業人士。"
)


def _fmt_pct(x, digits=1):
    return f"{x * 100:+.{digits}f}%" if x is not None else "—"


def _taipei_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


def build_markdown(run: dict) -> str:
    """run: 完整執行結果(見 run.py 組裝的 data dict)。回傳 Markdown 全文。"""
    d = run["date"]
    lines: list[str] = []
    ap = lines.append

    ap(f"# 投資研究日誌 — {d}")
    ap("")
    ap(f"- 產生時間:{run['generated_at_taipei']}(台北)")
    ap(f"- 資料來源:{run['data_source_summary']}")
    if run.get("demo_mode"):
        ap("- **⚠️ 本篇使用示範資料(僅展示系統功能,非真實行情)**")
    ap("")

    # 摘要表
    ap("## 今日決策一覽")
    ap("")
    ap("| 標的 | 收盤 | 日漲跌 | 評分 | 決策 | 信心 |")
    ap("|---|---|---|---|---|---|")
    for dec in run["decisions"]:
        ind = run["signals"][dec["ticker"]]
        ap(f"| {dec['ticker']} | ${dec['price']:,.2f} | {_fmt_pct(ind.get('change_1d'))} "
           f"| {dec['score']:+d} | **{dec['action_zh']}** | {dec['confidence']} |")
    ap("")

    acted = [x for x in run["decisions"] if x["acted"]]
    ap(f"共 {len(run['decisions'])} 檔:{len(acted)} 檔有動作建議、"
       f"{len(run['decisions']) - len(acted)} 檔決定不動作(理由見下)。")
    ap("")

    # 投資組合
    pf = run["portfolio"]
    ap("## 投資組合狀態")
    ap("")
    if pf.get("total_value"):
        ap(f"- 總價值:**${pf['total_value']:,.2f}**(現金 ${pf['cash']:,.2f},"
           f"佔 {pf['cash_pct']*100:.1f}%)")
        ap(f"- 未實現損益:{_fmt_pct(pf.get('total_pnl_pct'))} "
           f"(${pf.get('total_pnl_usd', 0):+,.2f})")
        if pf.get("is_demo"):
            ap("- ⚠️ 目前為示範持倉 — 請把真實持倉更新到 `config/portfolio.json`")
    else:
        ap("- 尚未設定持倉(config/portfolio.json)")
    for note in run.get("portfolio_notes", []):
        ap(f"- 📌 {note}")
    ap("")

    # 逐檔詳情
    ap("## 逐檔決策紀錄")
    ap("")
    for dec in run["decisions"]:
        t = dec["ticker"]
        ind = run["signals"][t]
        nw = run["news"].get(t, {})
        ap(f"### {t} — {dec['action_zh']}(評分 {dec['score']:+d},信心:{dec['confidence']})")
        ap("")
        ap(f"**結論:{dec['summary']}**")
        ap("")
        if dec.get("position"):
            p = dec["position"]
            ap(f"- 持倉:{p['shares']} 股 @ ${p['avg_cost']:,.2f},市值 ${p['market_value']:,.2f},"
               f"未實現 {_fmt_pct(p.get('pnl_pct'))}(${p['pnl_usd']:+,.2f})")
        if dec.get("suggested_qty"):
            ap(f"- 參考股數:約 {dec['suggested_qty']} 股(依部位上限與現金保留規則計算,僅供參考)")
        for rn in dec.get("risk_notes", []):
            ap(f"- {rn}")
        ap("")
        ap("訊號依據:")
        ap("")
        for r in dec["reasons"]:
            ap(f"- [{r['points']:+d}] **{r['rule']}**:{r['detail']}")
        key_line = (f"RSI {ind.get('rsi'):.0f}" if ind.get("rsi") is not None else "RSI —")
        ap(f"- 關鍵數據:{key_line} | 20日 {_fmt_pct(ind.get('change_20d'))} | "
           f"距 52 週高點 {_fmt_pct(ind.get('dist_high_52w'))} | 資料源 {ind.get('source')}")
        if nw.get("items"):
            ap("")
            ap(f"新聞觀察(情緒:{nw['label']} {nw['agg_sentiment']:+.1f}):")
            ap("")
            for it in nw["items"][:4]:
                mark = {2: "🟢", 1: "🟢", 0: "⚪", -1: "🔴", -2: "🔴"}.get(it["sentiment"], "⚪")
                src = f"({it['source']})" if it.get("source") else ""
                ap(f"- {mark} {it['title']} {src}")
        ap("")

    # 潛力雷達
    disc = run.get("discovery", {})
    ap("## 潛力雷達(候選研究,非買進建議)")
    ap("")
    if disc.get("candidates"):
        ap(f"_{disc.get('note', '')}_")
        ap("")
        ap("| 代號 | 名稱 | 價格 | 漲跌 | 市值 | 備註 |")
        ap("|---|---|---|---|---|---|")
        for cd in disc["candidates"]:
            mcap = f"${cd['market_cap']/1e9:.1f}B" if cd.get("market_cap") else "—"
            ap(f"| {cd['ticker']} | {cd['name']} | ${cd['price']:,.2f} "
               f"| {_fmt_pct(cd['change_pct'])} | {mcap} | {cd.get('note','')} |")
    else:
        ap(f"今日無候選。{disc.get('note', '')}")
    ap("")

    # 每日一課
    lesson = run["lesson"]
    ap(f"## 📚 每日一課:{lesson['title']}")
    ap("")
    ap(lesson["body"])
    ap("")
    ap("## 如何執行建議")
    ap("")
    ap("本系統**不會自動下單**。若你認同某項建議:自行在券商下單後,"
       "把成交結果更新到 `config/portfolio.json`(或告訴 Claude 幫你更新),"
       "系統隔天就會以新持倉計算風控與損益。不認同也沒關係 — 在日誌寫下你的理由,那就是你的投資紀錄。")
    ap("")
    ap(DISCLAIMER)
    ap("")
    return "\n".join(lines)


def write_journal(run: dict) -> tuple[Path, Path]:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    md_path = JOURNAL_DIR / f"{run['date']}.md"
    md_path.write_text(build_markdown(run), encoding="utf-8")

    jsonl_path = JOURNAL_DIR / "journal.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as f:
        for dec in run["decisions"]:
            rec = {
                "date": run["date"], "type": "decision",
                "ticker": dec["ticker"], "action": dec["action"],
                "score": dec["score"], "confidence": dec["confidence"],
                "price": dec["price"], "summary": dec["summary"],
                "reasons": [f"[{r['points']:+d}] {r['rule']}: {r['detail']}" for r in dec["reasons"]],
                "risk_notes": dec["risk_notes"],
                "suggested_qty": dec["suggested_qty"],
                "position": dec["position"],
                "demo": run.get("demo_mode", False),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.write(json.dumps({
            "date": run["date"], "type": "summary",
            "portfolio": run["portfolio"],
            "portfolio_notes": run.get("portfolio_notes", []),
            "lesson_id": run["lesson"]["id"],
            "demo": run.get("demo_mode", False),
        }, ensure_ascii=False) + "\n")
    return md_path, jsonl_path
