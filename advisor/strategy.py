"""建議引擎:把技術訊號 + 新聞情緒 + 持倉風控,轉成可讀的買賣建議。

設計原則:
1. 每一分都有出處 — reasons 列出每條規則的加減分與白話解釋(這也是教學素材)。
2. 風控優先 — 停損/停利檢查凌駕於分數之上。
3. 純建議制 — 系統絕不下單;所有建議需由使用者確認後自行執行。
分數區間 -100 ~ +100。門檻在 config/settings.json 可調。
"""
from __future__ import annotations

ACTION_ZH = {
    "BUY": "建議買進", "ADD": "建議加碼", "HOLD": "續抱觀察",
    "TRIM": "建議減碼", "SELL": "建議賣出", "WATCH": "暫不動作",
}


def _fmt_pct(x, digits=1):
    return f"{x * 100:+.{digits}f}%" if x is not None else "—"


def score_signals(ind: dict, news: dict) -> tuple[int, list[dict]]:
    """回傳 (總分, 理由清單)。理由: {rule, points, detail}"""
    reasons: list[dict] = []

    def add(rule: str, points: float, detail: str):
        if points:
            reasons.append({"rule": rule, "points": round(points), "detail": detail})

    price, sma_m, sma_s = ind["price"], ind["sma_mid"], ind["sma_slow"]

    # --- 長短期趨勢 ---
    if sma_s:
        if price > sma_s:
            add("長期趨勢", +15, f"股價站上 200 日均線(${sma_s:,.2f}),長線多頭格局")
        else:
            add("長期趨勢", -15, f"股價跌破 200 日均線(${sma_s:,.2f}),長線轉弱訊號")
    if sma_m:
        if price > sma_m:
            add("中期趨勢", +10, f"股價在 50 日均線(${sma_m:,.2f})之上,中期偏多")
        else:
            add("中期趨勢", -10, f"股價在 50 日均線(${sma_m:,.2f})之下,中期偏空")
    if ind.get("sma_cross") == "golden":
        add("黃金交叉", +10, "50 日均線近期上穿 200 日均線 — 經典的中長期轉多訊號")
    elif ind.get("sma_cross") == "death":
        add("死亡交叉", -10, "50 日均線近期下穿 200 日均線 — 中長期轉空警訊")

    # --- 動能 (RSI) ---
    r = ind.get("rsi")
    if r is not None:
        if r >= 75:
            add("RSI 過熱", -10, f"RSI={r:.0f},短線漲多過熱,追高風險上升")
        elif r >= 70:
            add("RSI 偏熱", -6, f"RSI={r:.0f},接近超買區,不宜追價")
        elif r <= 30:
            add("RSI 超賣", +8, f"RSI={r:.0f},進入超賣區,留意止跌反轉機會(仍需趨勢配合)")
        elif 40 <= r <= 60:
            add("RSI 中性", +3, f"RSI={r:.0f},動能健康,沒有過熱或過冷")

    # --- MACD ---
    hist, hist_prev = ind.get("macd_hist"), ind.get("macd_hist_prev")
    if ind.get("macd_cross") == "golden":
        add("MACD 黃金交叉", +8, "MACD 快線近 5 日上穿訊號線,短中期動能翻多")
    elif ind.get("macd_cross") == "death":
        add("MACD 死亡交叉", -8, "MACD 快線近 5 日下穿訊號線,短中期動能轉弱")
    elif hist is not None and hist_prev is not None:
        if hist > 0 and hist >= hist_prev:
            add("MACD 動能", +7, "MACD 柱狀體為正且擴大,多方動能延續")
        elif hist > 0:
            add("MACD 動能", +3, "MACD 柱狀體為正但收斂,漲勢動能放緩")
        elif hist < 0 and hist <= hist_prev:
            add("MACD 動能", -7, "MACD 柱狀體為負且擴大,空方動能增強")
        else:
            add("MACD 動能", -3, "MACD 柱狀體為負但收斂,跌勢趨緩")

    # --- 布林通道 ---
    pb = ind.get("bb_pct_b")
    if pb is not None:
        if pb > 1.0:
            add("布林通道", -5, "收盤價衝出布林上軌,短線乖離過大,易回檔整理")
        elif pb < 0.0:
            add("布林通道", +5, "收盤價跌破布林下軌,短線超跌,留意技術性反彈")

    # --- 量價 ---
    vr, chg = ind.get("vol_ratio"), ind.get("change_1d")
    if vr is not None and chg is not None and vr >= 1.5:
        if chg > 0:
            add("量價齊揚", +5, f"成交量為 20 日均量的 {vr:.1f} 倍且收漲,買盤積極")
        else:
            add("帶量下跌", -6, f"成交量為 20 日均量的 {vr:.1f} 倍且收跌,賣壓沉重")

    # --- 52 週位置 ---
    dh = ind.get("dist_high_52w")
    if dh is not None:
        if dh >= -0.03:
            add("52週高點", +5, "股價貼近 52 週新高,強勢動能(注意勿重倉追高)")
        elif dh <= -0.35:
            add("52週低檔", -5, "股價距 52 週高點回檔逾 35%,趨勢受損,須確認止跌")

    # --- 新聞情緒 ---
    s = news.get("agg_sentiment", 0)
    if s >= 0.5:
        add("新聞情緒", +8, f"近期新聞偏正面(情緒分 {s:+.1f})")
    elif s <= -0.5:
        add("新聞情緒", -8, f"近期新聞偏負面(情緒分 {s:+.1f}),留意消息面風險")

    total = int(max(-100, min(100, sum(x["points"] for x in reasons))))
    return total, reasons


def decide(ticker: str, ind: dict, news: dict, position: dict | None,
           portfolio_ctx: dict, cfg: dict) -> dict:
    """產出單一標的的完整決策記錄(含不動作)。"""
    th, risk = cfg["thresholds"], cfg["risk"]
    score, reasons = score_signals(ind, news)
    price = ind["price"]
    risk_notes: list[str] = []
    action = None

    held = position is not None and position.get("shares", 0) > 0
    total_value = portfolio_ctx.get("total_value") or 0

    pos_detail = None
    if held:
        shares, avg = position["shares"], position["avg_cost"]
        pnl_pct = price / avg - 1 if avg else None
        weight = (shares * price / total_value) if total_value else None
        pos_detail = {
            "shares": shares, "avg_cost": avg,
            "market_value": round(shares * price, 2),
            "pnl_pct": pnl_pct, "pnl_usd": round((price - avg) * shares, 2),
            "weight": weight,
        }
        # --- 風控優先 ---
        if pnl_pct is not None and pnl_pct <= risk["stop_loss_pct"]:
            action = "SELL"
            risk_notes.append(
                f"⚠ 觸發停損紀律:未實現損益 {_fmt_pct(pnl_pct)} 已低於停損線 "
                f"{_fmt_pct(risk['stop_loss_pct'])}。停損的意義是保住本金、避免小虧變大虧。"
            )
        elif (pnl_pct is not None and pnl_pct >= risk["take_profit_review_pct"]
              and (ind.get("rsi") or 0) >= th["trim_rsi"] and score < th["add_score"]):
            action = "TRIM"
            risk_notes.append(
                f"獲利已達 {_fmt_pct(pnl_pct)} 且 RSI={ind.get('rsi'):.0f} 過熱:"
                "建議減碼 1/3~1/2 鎖定部分獲利,讓剩餘部位繼續參與趨勢。"
            )
        if weight is not None and weight > risk["max_position_weight"]:
            risk_notes.append(
                f"部位集中度警示:{ticker} 佔投資組合 {weight*100:.1f}%,"
                f"超過上限 {risk['max_position_weight']*100:.0f}%,漲跌都會被單一標的放大。"
            )

    if action is None:
        if held:
            if score <= th["sell_score"]:
                action = "SELL"
            elif score >= th["add_score"]:
                action = "ADD"
            else:
                action = "HOLD"
        else:
            action = "BUY" if score >= th["buy_score"] else "WATCH"

    # 建議股數(僅供參考)
    suggested = None
    if action in ("BUY", "ADD") and total_value:
        target = total_value * risk["default_new_position_weight"]
        cash = portfolio_ctx.get("cash") or 0
        reserve = total_value * risk["min_cash_reserve_pct"]
        budget = max(0.0, min(target, cash - reserve))
        qty = int(budget // price)
        if qty <= 0:
            risk_notes.append("現金不足(或會低於保留現金比例),暫不給出加碼股數 — 紀律優先於機會。")
            if action == "BUY":
                action = "WATCH"
        else:
            suggested = qty

    if action == "WATCH" and score >= 20:
        summary = f"分數 {score:+d} 未達買進門檻 {th['buy_score']}:訊號偏多但不夠強,今日不動作,續列觀察。"
    elif action == "WATCH":
        summary = f"分數 {score:+d} 未達門檻:條件不成熟,今日不動作。空手等待也是一種決策。"
    elif action == "HOLD":
        summary = f"分數 {score:+d} 介於加碼({th['add_score']})與賣出({th['sell_score']})門檻之間:續抱,不加不減。"
    else:
        summary = f"綜合評分 {score:+d} → {ACTION_ZH[action]}。"

    confidence = "高" if abs(score) >= 60 else ("中" if abs(score) >= 35 else "低")

    return {
        "ticker": ticker,
        "action": action,
        "action_zh": ACTION_ZH[action],
        "score": score,
        "confidence": confidence,
        "price": round(price, 2),
        "summary": summary,
        "reasons": reasons,
        "risk_notes": risk_notes,
        "suggested_qty": suggested,
        "position": pos_detail,
        "acted": action in ("BUY", "ADD", "TRIM", "SELL"),
    }


def portfolio_review(positions_decided: list[dict], portfolio_ctx: dict, cfg: dict) -> list[str]:
    """投資組合層級的整體提醒。"""
    notes = []
    risk = cfg["risk"]
    tv, cash = portfolio_ctx.get("total_value") or 0, portfolio_ctx.get("cash") or 0
    if tv:
        cash_pct = cash / tv
        if cash_pct < risk["min_cash_reserve_pct"]:
            notes.append(
                f"現金水位 {cash_pct*100:.1f}% 低於建議保留 {risk['min_cash_reserve_pct']*100:.0f}%:"
                "手上留現金才有能力在回檔時行動,也避免被迫在低點賣股。"
            )
        held = [d for d in positions_decided if d.get("position")]
        if len(held) in (1, 2) and tv > cash * 2:
            notes.append("持股檔數偏少:單一公司的個別風險(財報、訴訟、產品)無法被分散,可考慮 5~10 檔或搭配 ETF。")
    else:
        notes.append("尚未設定持倉與現金(config/portfolio.json),目前僅提供訊號分析;補上後即可啟用部位建議與風控。")
    return notes
