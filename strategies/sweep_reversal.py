"""
Liquidity Sweep Reversal Strategy

Conditions:
  1. Liquidity pool exists (equal highs/lows on 1D or 4H)
  2. Sweep candle: price breaks level, closes back (within same candle)
  3. Rejection candle (next candle or sweep candle itself):
       • wick ≥ 2.5 × body
       • body ≤ 1/3 of full range
       • correct wick direction (lower for LONG, upper for SHORT)
  4. Volume spike: vol ≥ 1.2× MA20 on sweep or rejection candle
  5. Entry:
       Market:  close of rejection candle
       Limit:   50% of sweep candle body
  6. SL: beyond sweep extreme (low for LONG, high for SHORT)
  7. TP: target liquidity level, ensuring RR ≥ 2
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config.settings import settings
from engine.confidence import (
    ConfidenceResult,
    apply_adx_counter_trend_penalty,
    compute_confidence,
)
from engine.indicators import candle_parts, volume_ma
from engine.liquidity_map import LiquidityLevel, select_target_level

logger = logging.getLogger(__name__)


@dataclass
class SweepSignal:
    direction:    str           # LONG | SHORT
    entry_market: float
    entry_limit:  Optional[float]
    stop_loss:    float
    take_profit:  float
    rr_ratio:     float
    swept_level:  LiquidityLevel
    target_level: Optional[LiquidityLevel]
    volume_spike: bool
    confidence:   ConfidenceResult


def _make_signal_id(direction: str, entry: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{direction}{entry:.2f}{now}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def check_sweep_reversal(
    df_15m: pd.DataFrame,
    levels: list,
    squeeze_active: bool,
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
    market_state: str,
    adx_value: float,
    trend_direction: Optional[str],
    session: Optional[str],
) -> Optional[SweepSignal]:
    """
    Scan the last 2 candles for a sweep + rejection pattern.
    Returns SweepSignal or None.

    df_15m: at least 30 rows, OHLCV.
    levels: List[LiquidityLevel] from build_liquidity_map().
    """
    if len(df_15m) < 25:
        return None

    vol_ma20     = volume_ma(df_15m, 20).iloc[-1]
    current_price = float(df_15m["close"].iloc[-1])

    sweep_c = df_15m.iloc[-2]   # potential sweep candle
    rej_c   = df_15m.iloc[-1]   # potential rejection candle

    for level in levels:
        signal = _check_one_level(
            level, sweep_c, rej_c, vol_ma20, current_price,
            levels, squeeze_active, cvd_divergence,
            funding_rate, liquidation_cascade,
            market_state, adx_value, trend_direction, session,
        )
        if signal:
            return signal

    return None


def _check_one_level(
    level: LiquidityLevel,
    sweep_c: pd.Series,
    rej_c: pd.Series,
    vol_ma20: float,
    current_price: float,
    all_levels: list,
    squeeze_active: bool,
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
    market_state: str,
    adx_value: float,
    trend_direction: Optional[str],
    session: Optional[str],
) -> Optional[SweepSignal]:

    lp    = level.price
    tol   = settings.sweep_tolerance_pct
    parts = candle_parts(rej_c)

    # ── LONG setup: sweep of equal_lows ───────────────────────

    if level.pool_type == "equal_lows":
        swept    = float(sweep_c["low"]) < lp * (1 - tol)
        returned = float(sweep_c["close"]) > lp

        if not (swept and returned):
            return None

        # Rejection candle: long LOWER wick
        if not _is_rejection(parts, direction="LONG"):
            return None

        direction = "LONG"
        entry_market = float(rej_c["close"])
        stop_loss    = float(sweep_c["low"]) - float(
            rej_c["close"] - rej_c["open"]  # 1 ATR proxy
        ) * 0.5
        stop_loss = min(stop_loss, float(sweep_c["low"]) * 0.999)

        # Limit entry: 50% of sweep candle body (from low toward close)
        sweep_body_low  = min(float(sweep_c["open"]), float(sweep_c["close"]))
        sweep_body_high = max(float(sweep_c["open"]), float(sweep_c["close"]))
        entry_limit     = sweep_body_low + (sweep_body_high - sweep_body_low) * settings.limit_entry_pct

    # ── SHORT setup: sweep of equal_highs ─────────────────────

    elif level.pool_type == "equal_highs":
        swept    = float(sweep_c["high"]) > lp * (1 + tol)
        returned = float(sweep_c["close"]) < lp

        if not (swept and returned):
            return None

        if not _is_rejection(parts, direction="SHORT"):
            return None

        direction = "SHORT"
        entry_market = float(rej_c["close"])
        stop_loss    = float(sweep_c["high"]) * 1.001

        sweep_body_low  = min(float(sweep_c["open"]), float(sweep_c["close"]))
        sweep_body_high = max(float(sweep_c["open"]), float(sweep_c["close"]))
        entry_limit     = sweep_body_high - (sweep_body_high - sweep_body_low) * settings.limit_entry_pct

    else:
        return None

    # ── Target liquidity ──────────────────────────────────────

    target = select_target_level(all_levels, current_price, direction)
    if target:
        take_profit = target.price
        dist_to_target = target.distance_pct
    else:
        # Fallback: RR 2 from entry/stop
        risk = abs(entry_market - stop_loss)
        take_profit = (entry_market + risk * settings.min_rr
                       if direction == "LONG"
                       else entry_market - risk * settings.min_rr)
        dist_to_target = abs(take_profit - current_price) / current_price

    # ── RR check ──────────────────────────────────────────────

    risk   = abs(entry_market - stop_loss)
    reward = abs(take_profit  - entry_market)
    rr     = reward / risk if risk else 0

    if rr < settings.min_rr:
        logger.debug(f"RR {rr:.2f} < {settings.min_rr} at level {lp:.2f}")
        return None

    # ── Distance to target check ──────────────────────────────

    if dist_to_target < settings.liquidity_min_distance_pct:
        logger.debug(f"Target too close: {dist_to_target*100:.2f}%")
        return None

    # ── Volume spike ──────────────────────────────────────────

    vol_sweep = float(sweep_c["volume"])
    vol_rej   = float(rej_c["volume"])
    volume_spike = (vol_sweep >= vol_ma20 * settings.volume_spike_multiplier or
                    vol_rej   >= vol_ma20 * settings.volume_spike_multiplier)

    # ── Confidence ────────────────────────────────────────────

    is_counter = (
        market_state == "trending" and
        _is_counter_trend(direction, trend_direction)
    )

    conf = compute_confidence(
        strategy="sweep_reversal",
        direction=direction,
        session=session,
        market_state=market_state,
        adx_value=adx_value,
        volume_spike=volume_spike,
        squeeze_active=squeeze_active,
        cvd_divergence=cvd_divergence,
        funding_rate=funding_rate,
        liquidation_cascade=liquidation_cascade,
    )
    apply_adx_counter_trend_penalty(conf, adx_value, is_counter)

    return SweepSignal(
        direction=direction,
        entry_market=round(entry_market, 2),
        entry_limit=round(entry_limit, 2),
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        rr_ratio=round(rr, 2),
        swept_level=level,
        target_level=target,
        volume_spike=volume_spike,
        confidence=conf,
    )


def _is_rejection(parts: dict, direction: str) -> bool:
    """
    Pin-bar rules:
      • wick ≥ 2.5 × body
      • body ≤ 1/3 of full range
    """
    body  = parts["body"]
    rng   = parts["range"]
    if rng == 0:
        return False

    if direction == "LONG":
        wick = parts["lower_wick"]
    else:
        wick = parts["upper_wick"]

    if body == 0:
        return True   # doji with wick is a valid rejection

    wick_ok = wick >= settings.rejection_wick_ratio * body
    body_ok = body <= settings.rejection_body_range_max * rng
    return wick_ok and body_ok


def _is_counter_trend(direction: str, trend_direction: Optional[str]) -> bool:
    """Only penalise when the prevailing directional trend is known and opposite."""
    return trend_direction in {"LONG", "SHORT"} and direction != trend_direction


def signal_to_dict(
    sig: SweepSignal,
    session: str,
    market_state: str,
    volatility_regime: str,
    adx_value: float,
    atr_pct: float,
    oi_change_pct: Optional[float],
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
    squeeze_active: bool,
) -> dict:
    """Convert SweepSignal to flat dict for DB storage and Telegram."""
    return {
        "signal_id":   _make_signal_id(sig.direction, sig.entry_market),
        "pair":        settings.symbol,
        "strategy":    "sweep_reversal",
        "direction":   sig.direction,
        "session":     session,
        "entry_market": sig.entry_market,
        "entry_limit":  sig.entry_limit,
        "stop_loss":    sig.stop_loss,
        "take_profit":  sig.take_profit,
        "rr_ratio":     sig.rr_ratio,
        "position_size_pct": None,   # filled by risk manager
        "confidence_score":  sig.confidence.score,
        "confidence_breakdown": json.dumps(sig.confidence.breakdown_json),
        "market_state":     market_state,
        "volatility_regime": volatility_regime,
        "adx_value":         adx_value,
        "atr_pct":           atr_pct,
        "target_liquidity_price": sig.target_level.price if sig.target_level else None,
        "target_liquidity_tf":    sig.target_level.timeframe if sig.target_level else None,
        "target_liquidity_type":  sig.target_level.pool_type if sig.target_level else None,
        "distance_to_target_pct": sig.target_level.distance_pct if sig.target_level else None,
        "cvd_divergence":     cvd_divergence,
        "oi_change_pct":      oi_change_pct,
        "liquidation_cascade": liquidation_cascade,
        "funding_rate":        funding_rate,
        "squeeze_active":      squeeze_active,
    }
