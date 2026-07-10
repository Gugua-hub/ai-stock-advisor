"""新聞監控:Yahoo Finance 新聞 + Google News RSS(免金鑰),關鍵詞情緒評分。

情緒評分是簡化的關鍵詞法 — 它的目的是「排序與提示」,不是精準的 NLP。
日誌與儀表板都會保留原始標題與連結,讓人可以自行查證。
"""
from __future__ import annotations

import random
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

POSITIVE = [
    "beat", "beats", "record", "surge", "surges", "soar", "soars", "rally",
    "upgrade", "upgraded", "raises", "raised", "hike", "outperform", "buyback",
    "strong", "growth", "profit", "gains", "jump", "jumps", "partnership",
    "approval", "approved", "wins", "win", "expands", "breakthrough", "tops",
    "bullish", "dividend increase", "all-time high", "better-than-expected",
]
NEGATIVE = [
    "miss", "misses", "cut", "cuts", "downgrade", "downgraded", "lawsuit",
    "probe", "investigation", "recall", "layoff", "layoffs", "plunge",
    "plunges", "sink", "sinks", "drop", "drops", "falls", "fall", "weak",
    "warning", "warns", "fraud", "fine", "fined", "delay", "delays", "halt",
    "bankruptcy", "sell-off", "selloff", "short seller", "bearish", "slump",
    "worse-than-expected", "misses estimates", "guidance cut", "tumble",
]

_DEMO_HEADLINES = [
    ("【示範】{t} 最新季度財報優於市場預期,盤後走高", 2),
    ("【示範】分析師調升 {t} 目標價,看好長期成長動能", 1),
    ("【示範】{t} 宣布擴大 AI 產品線投資", 1),
    ("【示範】市場觀望氣氛濃,{t} 成交量低於均量", 0),
    ("【示範】{t} 面臨供應鏈成本上升壓力", -1),
    ("【示範】監管機構對 {t} 展開例行問詢", -1),
]


def _score_headline(title: str) -> int:
    t = title.lower()
    score = sum(1 for w in POSITIVE if w in t) - sum(1 for w in NEGATIVE if w in t)
    return max(-2, min(2, score))


def _from_yfinance(ticker: str, limit: int) -> list[dict]:
    import yfinance as yf

    items = []
    for raw in (yf.Ticker(ticker).news or [])[: limit * 2]:
        content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
        title = content.get("title") or ""
        if not title:
            continue
        url = ""
        cu = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        if isinstance(cu, dict):
            url = cu.get("url", "")
        url = url or raw.get("link", "")
        provider = content.get("provider") or {}
        source = provider.get("displayName") if isinstance(provider, dict) else ""
        pub = content.get("pubDate") or content.get("displayTime") or ""
        items.append({"title": title, "url": url, "source": source or "Yahoo Finance",
                      "published": str(pub)[:19]})
    return items


def _from_google_rss(query: str, limit: int) -> list[dict]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        source = item.findtext("source") or "Google News"
        items.append({
            "title": title,
            "url": (item.findtext("link") or "").strip(),
            "source": source.strip() if isinstance(source, str) else "Google News",
            "published": (item.findtext("pubDate") or "")[:25],
        })
        if len(items) >= limit:
            break
    return items


def _demo_news(ticker: str, limit: int) -> list[dict]:
    rng = random.Random(f"news-{ticker}-{datetime.now(timezone.utc).date()}")
    picks = rng.sample(_DEMO_HEADLINES, k=min(4, limit))
    out = []
    for tmpl, s in picks:
        out.append({
            "title": tmpl.format(t=ticker), "url": "", "source": "示範資料",
            "published": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "sentiment": s,
        })
    return out


def fetch_news(ticker: str, limit: int = 6, allow_demo: bool = False) -> dict:
    """回傳 {items:[{title,url,source,published,sentiment}], agg_sentiment, label}。"""
    items: list[dict] = []
    for fn in (lambda: _from_yfinance(ticker, limit),
               lambda: _from_google_rss(f"{ticker} stock", limit)):
        try:
            items = fn()
            if items:
                break
        except Exception:  # noqa: BLE001
            continue
    if not items and allow_demo:
        items = _demo_news(ticker, limit)

    seen, dedup = set(), []
    for it in items:
        key = re.sub(r"\W+", "", it["title"].lower())[:70]
        if key in seen:
            continue
        seen.add(key)
        if "sentiment" not in it:
            it["sentiment"] = _score_headline(it["title"])
        dedup.append(it)
        if len(dedup) >= limit:
            break

    if dedup:
        avg = sum(i["sentiment"] for i in dedup) / len(dedup)
    else:
        avg = 0.0
    label = "正面" if avg >= 0.5 else ("負面" if avg <= -0.5 else "中性")
    return {"items": dedup, "agg_sentiment": round(avg, 2), "label": label}
