"""
Market State Engine
    ADX(14) on 15m:
        > 25  → trending
        20–25 → dead_zone (skip all signals)
        < 20  → ranging

Volatility Regime (ATR%):
        < 0.20%  → blocked (QUIET minimum)
        0.20-0.60% → quiet (low vol but tradeable)
        0.60-1.5% → normal
        > 1.5%  → high

Operating Mode:
        BLOCKED  → ATR < 0.20% (skip all)
        QUIET    → 0.20% ≤ ATR < 0.60% (sweep only, all sessions allowed)
        NORMAL   → ATR ≥ 0.60% (all strategies)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Literal

import pandas as pd

from config.settings import settings
from engine.indicators import adx as calc_adx, atr_pct as calc_atr_pct, trend_direction as calc_trend_direction


@dataclass
class MarketContext:
    market_state:     str            # trending | ranging | dead_zone
    volatility_regime: str           # blocked | quiet | normal | high
    adx_value:        float
    atr_pct:          float
    session:          Optional[str]  # asian | london | ny | None
    hour_utc:         int
    tradeable:        bool           # False if dead_zone or blocked or no session
    operating_mode:   Literal['normal', 'quiet', 'blocked'] = 'normal'
    trend_direction:  Optional[str] = None  # LONG | SHORT | None

    def __str__(self) -> str:
        return (f"MarketContext({self.market_state}, vol={self.volatility_regime}, "
                f"adx={self.adx_value:.1f}, atr={self.atr_pct*100:.2f}%, "
                f"mode={self.operating_mode}, session={self.session}, tradeable={self.tradeable})")


def get_operating_mode(atr_pct: float) -> Literal['normal', 'quiet', 'blocked']:
    """
    Determine operating mode based on ATR%.

    Args:
        atr_pct: ATR as percentage (e.g., 0.0030 = 0.30%)

    Returns:
        'normal' if ATR >= 0.60%
        'quiet' if 0.20% <= ATR < 0.60%
        'blocked' if ATR < 0.20%
    """
    if atr_pct < settings.quiet_atr_min:
        return 'blocked'
    elif atr_pct < settings.quiet_atr_max:
        return 'quiet'
    else:
        return 'normal'


def get_market_context(df_15m: pd.DataFrame) -> MarketContext:
    """
    Compute full market context from 15m candles.
    df_15m must have columns: open, high, low, close, volume
    with at least 50 rows.
    """
    adx_val  = float(calc_adx(df_15m).iloc[-1])
    atr_val  = calc_atr_pct(df_15m, period=14, lookback=20)
    
    # Determine operating mode FIRST
    operating_mode = get_operating_mode(atr_val)
    
    trend_direction = calc_trend_direction(df_15m, period=14)

    # Market state
    t = settings.adx_trending_threshold
    dz_min, dz_max = settings.adx_dead_zone_min, settings.adx_dead_zone_max
    if dz_min <= adx_val <= dz_max:
        market_state = "dead_zone"
    elif adx_val > t:
        market_state = "trending"
    else:
        market_state = "ranging"

    # Volatility regime (updated for dual-mode)
    if atr_val < settings.quiet_atr_min:
        vol = "blocked"
    elif atr_val < settings.quiet_atr_max:
        vol = "quiet"
    elif atr_val <= settings.atr_normal_max:
        vol = "normal"
    else:
        vol = "high"

    # Session
    now_utc  = datetime.now(timezone.utc)
    hour_utc = now_utc.hour
    session  = settings.get_session(hour_utc)

    # Tradeable logic (updated for dual-mode)
    tradeable = (
        market_state != "dead_zone"
        and operating_mode != 'blocked'  # BLOCKED mode not tradeable
        and session is not None
    )
    
    # QUIET mode is restricted to the configured session allowlist.
    if operating_mode == 'quiet' and session not in settings.quiet_allowed_sessions:
        tradeable = False

    return MarketContext(
        market_state=market_state,
        volatility_regime=vol,
        adx_value=round(adx_val, 2),
        atr_pct=round(atr_val, 5),
        session=session,
        hour_utc=hour_utc,
        tradeable=tradeable,
        operating_mode=operating_mode,  # NEW!
        trend_direction=trend_direction,  # Для совместимости
    )
