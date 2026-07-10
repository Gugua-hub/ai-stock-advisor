#!/usr/bin/env python3
"""主流程:研究 → 建議 → 日誌 → 儀表板。

用法:
  python run.py            # 正常執行(抓真實資料;全部失敗才會報錯)
  python run.py --demo     # 允許在資料源不可用時使用「示範資料」(明確標示)
  python run.py --no-news  # 跳過新聞抓取(較快)
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from advisor import data as data_mod          # noqa: E402
from advisor import indicators, news as news_mod, strategy, discovery as disc_mod  # noqa: E402
from advisor import education, journal as journal_mod  # noqa: E402
from advisor.dashboard import build_dashboard  # noqa: E402

CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="資料源不可用時允許示範資料")
    ap.add_argument("--no-news", action="store_true")
    args = ap.parse_args()

    cfg = load_json(CONFIG_DIR / "settings.json")
    watch = load_json(CONFIG_DIR / "watchlist.json")
    pf_cfg = load_json(CONFIG_DIR / "portfolio.json")

    tickers = [t.upper() for t in watch["tickers"]]
    positions = {p["ticker"].upper(): p for p in pf_cfg.get("positions", [])}
    # 有持倉但不在觀察清單的,也要納入分析(不能漏看自己手上的股票)
    for t in positions:
        if t not in tickers:
            tickers.append(t)

    now_utc = datetime.now(timezone.utc)
    now_tpe = now_utc.astimezone(timezone(timedelta(hours=8)))
    print(f"=== AI 投資研究助理 | {now_utc:%Y-%m-%d %H:%M} UTC ===")

    # 1) 行情 + 指標
    signals: dict[str, dict] = {}
    errors: list[str] = []
    for t in tickers:
        try:
            df = data_mod.fetch_history(t, cfg["indicators"]["history_days"], allow_demo=args.demo)
            signals[t] = indicators.compute_all(df, cfg)
            print(f"  [資料] {t}: {len(df)} 根K線, 來源={signals[t]['source']}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{t}: {e}")
            print(f"  [資料] {t}: 失敗 — {e}")
    if not signals:
        print("所有標的資料抓取失敗。真實環境請檢查網路;展示可加 --demo。")
        return 1

    # 2) 新聞
    news_all: dict[str, dict] = {}
    if not args.no_news and cfg["news"]["enabled"]:
        for t in signals:
            news_all[t] = news_mod.fetch_news(
                t, cfg["news"]["max_headlines_per_ticker"], allow_demo=args.demo
            )
    else:
        news_all = {t: {"items": [], "agg_sentiment": 0.0, "label": "未啟用"} for t in signals}

    # 3) 投資組合現值
    cash = pf_cfg.get("cash") or 0.0
    mv, cost_basis = 0.0, 0.0
    for t, p in positions.items():
        if t in signals:
            mv += p["shares"] * signals[t]["price"]
            cost_basis += p["shares"] * p["avg_cost"]
    total_value = cash + mv
    portfolio_ctx = {
        "cash": cash, "market_value": round(mv, 2),
        "total_value": round(total_value, 2) if total_value else None,
        "cash_pct": (cash / total_value) if total_value else None,
        "total_pnl_usd": round(mv - cost_basis, 2),
        "total_pnl_pct": (mv / cost_basis - 1) if cost_basis else None,
        "is_demo": bool(pf_cfg.get("_示範")),
    }

    # 4) 決策
    decisions = [
        strategy.decide(t, signals[t], news_all.get(t, {}), positions.get(t),
                        portfolio_ctx, cfg)
        for t in signals
    ]
    order = {"SELL": 0, "TRIM": 1, "BUY": 2, "ADD": 3, "HOLD": 4, "WATCH": 5}
    decisions.sort(key=lambda d: (order.get(d["action"], 9), -abs(d["score"])))
    pf_notes = strategy.portfolio_review(decisions, portfolio_ctx, cfg)

    # 5) 潛力雷達
    disc = disc_mod.discover(cfg, tickers, allow_demo=args.demo)

    # 6) 教學
    lesson = education.pick_lesson(decisions, now_utc.date())

    # 資產歷史(由每日快照累積,畫資產走勢用)
    equity_history: list[dict] = []
    hist_dir = OUTPUT_DIR / "history"
    if hist_dir.exists():
        for p in sorted(hist_dir.glob("2*.json")):
            try:
                snap = json.loads(p.read_text(encoding="utf-8"))
                tv = (snap.get("portfolio") or {}).get("total_value")
                if tv:
                    equity_history.append({"date": snap["date"], "total_value": tv})
            except Exception:  # noqa: BLE001
                continue
    today_str = now_utc.strftime("%Y-%m-%d")
    equity_history = [e for e in equity_history if e["date"] != today_str]
    if total_value:
        equity_history.append({"date": today_str, "total_value": round(total_value, 2)})

    sources = {s["source"] for s in signals.values()}
    demo_mode = "demo" in sources
    run = {
        "date": now_utc.strftime("%Y-%m-%d"),
        "generated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_at_taipei": now_tpe.strftime("%Y-%m-%d %H:%M"),
        "demo_mode": demo_mode,
        "data_source_summary": "、".join(sorted(sources)) + ("(示範模式)" if demo_mode else ""),
        "watchlist": tickers,
        "signals": signals,
        "news": news_all,
        "decisions": decisions,
        "portfolio": portfolio_ctx,
        "portfolio_positions": [
            {**p, "ticker": t, "price": signals[t]["price"],
             "market_value": round(p["shares"] * signals[t]["price"], 2),
             "pnl_pct": signals[t]["price"] / p["avg_cost"] - 1 if p.get("avg_cost") else None,
             "pnl_usd": round((signals[t]["price"] - p["avg_cost"]) * p["shares"], 2),
             "weight": (p["shares"] * signals[t]["price"] / total_value) if total_value else None}
            for t, p in positions.items() if t in signals
        ],
        "portfolio_notes": pf_notes,
        "equity_history": equity_history,
        "discovery": disc,
        "lesson": lesson,
        "errors": errors,
    }

    # 7) 日誌
    md_path, _ = journal_mod.write_journal(run)
    print(f"  [日誌] {md_path.relative_to(ROOT)}")

    # 8) 輸出 data.json(+歷史快照)與儀表板
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "history").mkdir(parents=True, exist_ok=True)
    run["journal_markdown"] = journal_mod.build_markdown(run)
    # 近 30 天日誌檔清單(給儀表板日誌頁)
    recent = sorted((ROOT / "journal").glob("2*.md"), reverse=True)[:30]
    run["journal_recent"] = [
        {"date": p.stem, "markdown": p.read_text(encoding="utf-8")} for p in recent[:7]
    ]
    data_json = json.dumps(run, ensure_ascii=False, default=str)
    (OUTPUT_DIR / "data.json").write_text(data_json, encoding="utf-8")
    (OUTPUT_DIR / "history" / f"{run['date']}.json").write_text(data_json, encoding="utf-8")

    dash_path = build_dashboard(run, ROOT / "docs" / "index.html")
    print(f"  [儀表板] {dash_path.relative_to(ROOT)}")

    acted = [d for d in decisions if d["acted"]]
    print(f"=== 完成:{len(decisions)} 檔分析,{len(acted)} 檔動作建議 "
          f"({', '.join(d['ticker'] + '→' + d['action'] for d in acted) or '無'})"
          f"{' | 示範模式' if demo_mode else ''} ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
