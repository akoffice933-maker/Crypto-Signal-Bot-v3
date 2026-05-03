"""
Pure-function technical indicators.
All functions accept pd.DataFrame with columns [open, high, low, close, volume]
and return pd.Series or scalar.
"""

import pandas as pd


def directional_indices(
    df: pd.DataFrame,
    period: int = 14,
) -> tuple[pd.Series, pd.Series]:
    """Return (+DI, -DI) series used by ADX-based trend direction checks."""
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    ph, pl = h - h.shift(1), l.shift(1) - l
    dm_plus = ph.clip(lower=0).where(ph > pl, 0)
    dm_minus = pl.clip(lower=0).where(pl > ph, 0)
    atr_s = tr.rolling(period).mean()
    di_p = 100 * dm_plus.rolling(period).mean() / atr_s
    di_m = 100 * dm_minus.rolling(period).mean() / atr_s
    return di_p, di_m


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def atr_pct(df: pd.DataFrame, period: int = 14, lookback: int = 20) -> float:
    """ATR(14) divided by mean(close, last N candles) — as a fraction."""
    a    = atr(df, period).iloc[-1]
    mean = df["close"].iloc[-lookback:].mean()
    return a / mean if mean else 0.0


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    di_p, di_m = directional_indices(df, period)
    dx = 100 * (di_p - di_m).abs() / (di_p + di_m + 1e-10)
    return dx.rolling(period).mean()


def trend_direction(df: pd.DataFrame, period: int = 14) -> str | None:
    """Return LONG when +DI dominates, SHORT when -DI dominates, else None."""
    di_p, di_m = directional_indices(df, period)
    last_p = di_p.iloc[-1]
    last_m = di_m.iloc[-1]
    if pd.isna(last_p) or pd.isna(last_m):
        return None
    if last_p > last_m:
        return "LONG"
    if last_m > last_p:
        return "SHORT"
    return None


def bollinger(df: pd.DataFrame, period: int = 20,
              std_mult: float = 2.0) -> pd.DataFrame:
    mid   = df["close"].rolling(period).mean()
    sigma = df["close"].rolling(period).std()
    return pd.DataFrame({
        "mid":   mid,
        "upper": mid + std_mult * sigma,
        "lower": mid - std_mult * sigma,
        "width": (2 * std_mult * sigma) / mid,   # normalised width
    })


def volume_ma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["volume"].rolling(period).mean()


def candle_parts(candle: pd.Series) -> dict:
    """
    Returns body size, upper wick, lower wick, total range.
    All values are positive.
    """
    o, h, l, c = float(candle["open"]), float(candle["high"]), \
                 float(candle["low"]),  float(candle["close"])
    body      = abs(c - o)
    rng       = h - l
    top       = max(o, c)
    bot       = min(o, c)
    upper_wick = h - top
    lower_wick = bot - l
    return {
        "body":       body,
        "range":      rng,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "is_bull":    c >= o,
    }
