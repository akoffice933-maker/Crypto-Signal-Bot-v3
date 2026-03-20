"""
Volatility Squeeze Detector — 4H timeframe

All three conditions must hold simultaneously:
  1. BB width = (upper − lower) / price → at minimum of last 50 candles (strictly)
  2. ATR(14) < average ATR over last 50 candles
  3. High − Low range of last 20 candles < 1.5%

Signal is given ON the squeeze (no need to wait for breakout).
"""

import logging

import pandas as pd

from config.settings import settings
from engine.indicators import atr as calc_atr, bollinger

logger = logging.getLogger(__name__)


def is_squeeze(df_4h: pd.DataFrame) -> bool:
    """
    Returns True if all three squeeze conditions are met on the latest candle.
    df_4h: DataFrame with open/high/low/close/volume, at least 55 rows.
    """
    lb = settings.squeeze_lookback          # 50
    rng_n = settings.squeeze_range_candles  # 20

    if len(df_4h) < lb + 5:
        logger.debug("Not enough 4H candles for squeeze detection")
        return False

    bb   = bollinger(df_4h)
    atr_ = calc_atr(df_4h, period=14)

    # ── Condition 1: BB width at its minimum over last lb candles ──
    current_width    = bb["width"].iloc[-1]
    historical_width = bb["width"].iloc[-(lb + 1):-1]   # exclude current
    if historical_width.empty:
        return False
    min_historical = historical_width.min()
    cond1 = current_width <= min_historical   # strictly at/below all prior

    # ── Condition 2: ATR below its 50-candle average ──
    current_atr  = atr_.iloc[-1]
    avg_atr_50   = atr_.iloc[-lb:].mean()
    cond2 = current_atr < avg_atr_50

    # ── Condition 3: 20-candle range < 1.5% ──
    recent = df_4h.iloc[-rng_n:]
    price_range_pct = (recent["high"].max() - recent["low"].min()) / recent["close"].mean()
    cond3 = price_range_pct < settings.squeeze_range_max_pct

    active = cond1 and cond2 and cond3
    if active:
        logger.info(
            f"Squeeze detected: bb_width={current_width:.5f} "
            f"(min={min_historical:.5f}), atr={current_atr:.2f}<avg={avg_atr_50:.2f}, "
            f"range={price_range_pct*100:.2f}%"
        )
    return active
