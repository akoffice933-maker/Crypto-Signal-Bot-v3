"""
Market State Engine
    ADX(14) on 15m:
        > 25  → trending
        20–25 → dead_zone (skip all signals)
        < 20  → ranging

Volatility Regime (ATR%):
        < 0.7%  → low      (skip)
        0.7–1.5% → normal
        > 1.5%  → high
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config.settings import settings
from engine.indicators import adx as calc_adx, atr_pct as calc_atr_pct, trend_direction


@dataclass
class MarketContext:
    market_state:     str            # trending | ranging | dead_zone
    volatility_regime: str           # low | normal | high
    adx_value:        float
    atr_pct:          float
    trend_direction:  Optional[str]  # LONG | SHORT | None
    session:          Optional[str]  # asian | london | ny | None
    hour_utc:         int
    tradeable:        bool           # False if dead_zone or low volatility or no session

    def __str__(self) -> str:
        return (f"MarketContext({self.market_state}, vol={self.volatility_regime}, "
                f"adx={self.adx_value:.1f}, trend={self.trend_direction}, "
                f"atr={self.atr_pct*100:.2f}%, "
                f"session={self.session}, tradeable={self.tradeable})")


def get_market_context(df_15m: pd.DataFrame) -> MarketContext:
    """
    Compute full market context from 15m candles.
    df_15m must have columns: open, high, low, close, volume
    with at least 50 rows.
    """
    adx_val  = float(calc_adx(df_15m).iloc[-1])
    atr_val  = calc_atr_pct(df_15m, period=14, lookback=20)
    trend_dir = trend_direction(df_15m, period=14)

    # Market state
    t = settings.adx_trending_threshold
    dz_min, dz_max = settings.adx_dead_zone_min, settings.adx_dead_zone_max
    if dz_min <= adx_val <= dz_max:
        market_state = "dead_zone"
    elif adx_val > t:
        market_state = "trending"
    else:
        market_state = "ranging"

    # Volatility
    if atr_val < settings.atr_low_threshold:
        vol = "low"
    elif atr_val <= settings.atr_normal_max:
        vol = "normal"
    else:
        vol = "high"

    # Session
    now_utc  = datetime.now(timezone.utc)
    hour_utc = now_utc.hour
    session  = settings.get_session(hour_utc)

    tradeable = (
        market_state != "dead_zone"
        and vol != "low"
        and session is not None
    )

    return MarketContext(
        market_state=market_state,
        volatility_regime=vol,
        adx_value=round(adx_val, 2),
        atr_pct=round(atr_val, 5),
        trend_direction=trend_dir,
        session=session,
        hour_utc=hour_utc,
        tradeable=tradeable,
    )
