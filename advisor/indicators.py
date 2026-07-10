"""技術指標:純 pandas 實作(不依賴 TA-Lib),每個指標都對應教學內容。"""
from __future__ import annotations

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI:衡量近期漲跌力道,>70 過熱、<30 超賣。"""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist


def bollinger(close: pd.Series, period=20, n_std=2):
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std()
    upper, lower = mid + n_std * std, mid - n_std * std
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower)
    return upper, mid, lower, pct_b, width


def _cross_within(a: pd.Series, b: pd.Series, days: int) -> str | None:
    """a 是否在最近 days 天內上穿(golden)或下穿(death) b。"""
    diff = (a - b).dropna()
    if len(diff) < days + 2:
        return None
    recent = diff.iloc[-(days + 1):]
    sign = recent.gt(0)
    if not sign.iloc[-1] == sign.iloc[0]:
        return "golden" if sign.iloc[-1] else "death"
    return None


def compute_all(df: pd.DataFrame, cfg: dict) -> dict:
    """回傳最新指標快照 + 畫圖用序列。所有數值轉為原生 float,方便 JSON 化。"""
    c = df["Close"]
    v = df["Volume"].astype("float64")
    ind = cfg["indicators"]

    sma_f = sma(c, ind["sma_fast"])
    sma_m = sma(c, ind["sma_mid"])
    sma_s = sma(c, ind["sma_slow"])
    rsi_s = rsi(c, ind["rsi_period"])
    macd_line, macd_sig, macd_hist = macd(
        c, ind["macd_fast"], ind["macd_slow"], ind["macd_signal"]
    )
    bb_u, bb_m, bb_l, pct_b, bb_w = bollinger(c, ind["bb_period"], ind["bb_std"])
    vol_avg = v.rolling(ind["volume_avg_days"], min_periods=5).mean()

    last = -1
    price = float(c.iloc[last])
    year = c.iloc[-252:] if len(c) >= 252 else c
    hi52, lo52 = float(year.max()), float(year.min())

    def f(series, idx=last):
        try:
            val = series.iloc[idx]
            return None if pd.isna(val) else float(val)
        except (IndexError, KeyError):
            return None

    def pct_chg(n: int):
        if len(c) > n:
            return float(c.iloc[last] / c.iloc[last - n] - 1)
        return None

    n_chart = int(ind.get("chart_days", 130))
    tail = df.iloc[-n_chart:]
    chart = {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "close": [round(float(x), 2) for x in tail["Close"]],
        "sma_fast": [None if pd.isna(x) else round(float(x), 2) for x in sma_f.iloc[-n_chart:]],
        "sma_mid": [None if pd.isna(x) else round(float(x), 2) for x in sma_m.iloc[-n_chart:]],
        "volume": [int(x) if not pd.isna(x) else 0 for x in tail["Volume"]],
    }

    macd_cross = _cross_within(macd_line, macd_sig, 5)
    sma_cross = _cross_within(sma_m, sma_s, 12)

    return {
        "price": price,
        "prev_close": f(c, -2),
        "change_1d": pct_chg(1),
        "change_5d": pct_chg(5),
        "change_20d": pct_chg(20),
        "change_60d": pct_chg(60),
        "sma_fast": f(sma_f), "sma_mid": f(sma_m), "sma_slow": f(sma_s),
        "rsi": f(rsi_s),
        "macd_line": f(macd_line), "macd_signal": f(macd_sig), "macd_hist": f(macd_hist),
        "macd_hist_prev": f(macd_hist, -2),
        "macd_cross": macd_cross,          # golden / death / None (近5日)
        "sma_cross": sma_cross,            # 中期均線對長期均線 (近12日)
        "bb_pct_b": f(pct_b), "bb_width": f(bb_w),
        "vol_ratio": (float(v.iloc[last] / vol_avg.iloc[last])
                      if vol_avg.iloc[last] and not pd.isna(vol_avg.iloc[last]) else None),
        "high_52w": hi52, "low_52w": lo52,
        "dist_high_52w": price / hi52 - 1 if hi52 else None,
        "dist_low_52w": price / lo52 - 1 if lo52 else None,
        "atr_pct": _atr_pct(df),
        "chart": chart,
        "last_date": df.index[-1].strftime("%Y-%m-%d"),
        "source": df.attrs.get("source", "unknown"),
    }


def _atr_pct(df: pd.DataFrame, period: int = 14):
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    val = atr.iloc[-1] / c.iloc[-1]
    return None if pd.isna(val) else float(val)
