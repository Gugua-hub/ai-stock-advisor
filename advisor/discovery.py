"""潛力公司發掘:掃描市場漲幅榜 / 成交活躍榜,產出「值得研究」的候選清單。

重要原則:候選 ≠ 建議買進。這個模組只負責把市場上「正在發生事情」的公司
撈出來並附上快速體檢數據;要不要納入觀察清單,由你決定(或在聊天中跟 Claude 討論)。
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

_DEMO_CANDIDATES = [
    {"ticker": "示範-A", "name": "【示範】雲端資安公司", "price": 48.2, "change_pct": 0.121,
     "volume": 18_400_000, "market_cap": 6.2e9, "note": "示範:法說會後大漲、量能為均量 3 倍"},
    {"ticker": "示範-B", "name": "【示範】電力設備供應商", "price": 112.5, "change_pct": 0.083,
     "volume": 9_100_000, "market_cap": 14.8e9, "note": "示範:受惠資料中心供電題材,創 52 週新高"},
    {"ticker": "示範-C", "name": "【示範】生技新藥公司", "price": 27.9, "change_pct": 0.154,
     "volume": 22_000_000, "market_cap": 3.1e9, "note": "示範:三期臨床數據優於預期"},
]


def _via_screener(cfg: dict, exclude: set[str]) -> list[dict]:
    import yfinance as yf

    if not hasattr(yf, "screen"):
        raise RuntimeError("此版 yfinance 不支援 screen()")
    out, seen = [], set()
    for scr in ("day_gainers", "most_actives"):
        try:
            res = yf.screen(scr, count=25)
        except Exception:  # noqa: BLE001
            continue
        for q in (res or {}).get("quotes", []):
            sym = q.get("symbol", "")
            if not sym or sym in seen or sym.upper() in exclude:
                continue
            price = q.get("regularMarketPrice")
            mcap = q.get("marketCap")
            if not price or price < cfg["discovery"]["min_price"]:
                continue
            if not mcap or mcap < 2e9:  # 避開流動性差的小型/水餃股
                continue
            seen.add(sym)
            out.append({
                "ticker": sym,
                "name": q.get("shortName") or q.get("longName") or sym,
                "price": float(price),
                "change_pct": (q.get("regularMarketChangePercent") or 0) / 100.0,
                "volume": int(q.get("regularMarketVolume") or 0),
                "market_cap": float(mcap),
                "note": f"來源:{'當日漲幅榜' if scr == 'day_gainers' else '成交活躍榜'}",
            })
    if not out:
        raise RuntimeError("screener 無結果")
    out.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return out


def discover(cfg: dict, watchlist: list[str], allow_demo: bool = False) -> dict:
    """回傳 {candidates: [...], source, note}。失敗時優雅降級。"""
    if not cfg["discovery"]["enabled"]:
        return {"candidates": [], "source": "off", "note": "發掘模組已停用(settings.json)"}
    exclude = {t.upper() for t in watchlist}
    try:
        cands = _via_screener(cfg, exclude)[: cfg["discovery"]["max_candidates"]]
        return {"candidates": cands, "source": "yahoo_screener",
                "note": "依當日漲幅/量能初篩(市值>20億、股價>5美元),僅供研究、非買進建議。"}
    except Exception as e:  # noqa: BLE001
        if allow_demo:
            rng = random.Random(str(datetime.now(timezone.utc).date()))
            cands = rng.sample(_DEMO_CANDIDATES, k=len(_DEMO_CANDIDATES))
            return {"candidates": cands, "source": "demo",
                    "note": "示範資料 — 真實環境會掃描 Yahoo 漲幅榜與成交活躍榜。"}
        return {"candidates": [], "source": "unavailable",
                "note": f"今日掃描不可用({type(e).__name__}),不影響其他功能。"}
