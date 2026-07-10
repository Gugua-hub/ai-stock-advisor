"""行情資料層:多重來源自動切換 — yfinance → Stooq → 本地快取 → 示範資料。

每個回傳的 DataFrame 都帶有 attrs["source"],讓下游與儀表板清楚標示資料來源。
示範資料只在 allow_demo=True 時啟用,且會被明確標記,絕不冒充真實行情。
"""
from __future__ import annotations

import io
import math
import random
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "output" / "cache"

# 示範模式用的合理價格量級(僅決定數列起點的數量級,非真實報價)
_DEMO_BASE = {
    "AAPL": 230, "MSFT": 500, "NVDA": 170, "GOOGL": 200, "AMZN": 220,
    "META": 700, "TSLA": 320, "SPY": 620, "QQQ": 560,
}

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _normalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["Close"])
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.attrs["source"] = source
    return df


def _fetch_yfinance(ticker: str, days: int) -> pd.DataFrame:
    import yfinance as yf

    period_days = max(days + 40, 260)
    df = yf.Ticker(ticker).history(period=f"{period_days}d", auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError("yfinance 回傳空資料")
    return _normalize(df, "yahoo")


def _fetch_stooq(ticker: str, days: int) -> pd.DataFrame:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(days * 1.7) + 60)
    sym = ticker.lower().replace(".", "-") + ".us"
    url = (
        f"https://stooq.com/q/d/l/?s={sym}&i=d"
        f"&d1={start.strftime('%Y%m%d')}&d2={end.strftime('%Y%m%d')}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode("utf-8", errors="replace")
    if "Date" not in raw.splitlines()[0]:
        raise RuntimeError("Stooq 回應非 CSV")
    df = pd.read_csv(io.StringIO(raw), parse_dates=["Date"]).set_index("Date")
    if df.empty:
        raise RuntimeError("Stooq 回傳空資料")
    return _normalize(df, "stooq")


def _load_cache(ticker: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{ticker.upper()}.csv"
    if not path.exists():
        raise RuntimeError("無快取")
    df = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
    age_days = (datetime.now(timezone.utc).date() - df.index.max().date()).days
    df = _normalize(df, f"cache(舊{age_days}天)")
    df.attrs["cache_age_days"] = age_days
    return df


def _save_cache(ticker: str, df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.reset_index().rename(columns={"index": "Date"}).to_csv(
        CACHE_DIR / f"{ticker.upper()}.csv", index=False
    )


def _demo_history(ticker: str, days: int) -> pd.DataFrame:
    """可重現的隨機漫步示範數列 — 僅供功能展示,非真實行情。"""
    rng = random.Random(f"demo-{ticker.upper()}")
    base = _DEMO_BASE.get(ticker.upper(), rng.uniform(20, 400))
    drift = rng.uniform(-0.0002, 0.0012)
    vol = rng.uniform(0.012, 0.028)
    end = datetime.now(timezone.utc).date()
    dates = pd.bdate_range(end=end, periods=days)
    price = base * rng.uniform(0.55, 0.8)
    rows = []
    for i, d in enumerate(dates):
        shock = rng.gauss(drift, vol)
        # 加一點趨勢段落,讓指標有東西可看
        if i % 90 < 45:
            shock += 0.0012
        else:
            shock -= 0.0006
        price = max(1.0, price * math.exp(shock))
        o = price * (1 + rng.gauss(0, vol / 3))
        h = max(o, price) * (1 + abs(rng.gauss(0, vol / 2)))
        low = min(o, price) * (1 - abs(rng.gauss(0, vol / 2)))
        v = int(abs(rng.gauss(1, 0.35)) * 4e7) + 1_000_000
        rows.append((d, o, h, low, price, v))
    df = pd.DataFrame(rows, columns=["Date", *COLUMNS]).set_index("Date")
    return _normalize(df, "demo")


def fetch_history(ticker: str, days: int = 430, allow_demo: bool = False) -> pd.DataFrame:
    """依序嘗試 yfinance → Stooq → 快取 → (可選)示範資料。"""
    errors = []
    for fn in (_fetch_yfinance, _fetch_stooq):
        try:
            df = fn(ticker, days)
            if len(df) >= 60:
                _save_cache(ticker, df)
                return df
            errors.append(f"{fn.__name__}: 資料太短({len(df)})")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{fn.__name__}: {type(e).__name__} {e}")
    try:
        return _load_cache(ticker)
    except Exception as e:  # noqa: BLE001
        errors.append(f"cache: {e}")
    if allow_demo:
        return _demo_history(ticker, days)
    raise RuntimeError(f"{ticker} 所有資料來源皆失敗: " + " | ".join(errors))
