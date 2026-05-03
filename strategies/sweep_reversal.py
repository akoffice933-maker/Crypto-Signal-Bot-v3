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
from engine.logger import log_liquidity_filter_diagnostics
from engine.liquidity_map import LiquidityLevel, select_target_level
from strategies.target_resolver import resolve_take_profit

logger = logging.getLogger(__name__)


@dataclass
class SweepSignal:
    direction:    str           # LONG | SHORT
    entry_market: float
    entry_limit:  Optional[float]
    stop_loss:    float
    tp1_price:    Optional[float]
    tp1_rr:       Optional[float]
    tp1_size_pct: Optional[float]
    final_tp_size_pct: float
    take_profit:  float
    rr_ratio:     float
    rr_market:    float
    rr_limit:     Optional[float]
    execution_basis: str
    swept_level:  LiquidityLevel
    target_level: Optional[LiquidityLevel]
    volume_spike: bool
    confidence:   ConfidenceResult


def _make_signal_id(pair: str, direction: str, entry: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{pair}{direction}{entry:.2f}{now}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _calculate_rr(direction: str, entry: float, stop_loss: float, take_profit: float) -> float:
    if direction == "LONG":
        risk = entry - stop_loss
        reward = take_profit - entry
    else:
        risk = stop_loss - entry
        reward = entry - take_profit
    return reward / risk if risk > 0 else 0.0


def _price_at_rr(direction: str, entry: float, stop_loss: float, rr_multiple: float) -> float:
    risk = abs(entry - stop_loss)
    if direction == "LONG":
        return entry + risk * rr_multiple
    return entry - risk * rr_multiple


def _filter_candidate_levels(levels: list, operating_mode: str) -> tuple[list, int]:
    min_level_score = (
        settings.quiet_level_score_min
        if operating_mode == 'quiet'
        else settings.normal_level_score_min
    )
    filtered_levels = [
        lvl for lvl in levels
        if lvl.level_score >= min_level_score
        and lvl.touch_count <= settings.max_level_touches
    ]
    return filtered_levels, min_level_score


def _resolve_sweep_stop_loss(
    *,
    direction: str,
    entry_reference: float,
    sweep_extreme: float,
    atr_pct: Optional[float],
    operating_mode: str,
) -> float:
    """
    Build a sweep stop from the swept candle extreme, but never tighter than:
      - min_stop_loss_pct
      - mode-specific ATR distance
    """
    atr_mult = (
        settings.quiet_sl_atr_mult
        if operating_mode == "quiet"
        else settings.normal_sl_atr_mult
    )
    atr_stop_pct = (atr_pct or 0.0) * atr_mult
    stop_pct = max(settings.min_stop_loss_pct, atr_stop_pct)

    if direction == "LONG":
        extreme_stop = sweep_extreme * 0.999
        atr_stop = entry_reference * (1 - stop_pct)
        return min(extreme_stop, atr_stop)

    extreme_stop = sweep_extreme * 1.001
    atr_stop = entry_reference * (1 + stop_pct)
    return max(extreme_stop, atr_stop)


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
    atr_pct: Optional[float] = None,
    operating_mode: str = 'normal',  # NEW: 'normal' | 'quiet' | 'blocked'
    min_rr: Optional[float] = None,
    volume_spike_multiplier: Optional[float] = None,
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

    filtered_levels, min_level_score = _filter_candidate_levels(levels, operating_mode)

    log_liquidity_filter_diagnostics(
        operating_mode=operating_mode,
        min_level_score=min_level_score,
        levels=levels,
        filtered_levels=filtered_levels,
    )

    for level in filtered_levels:
        signal = _check_one_level(
            level, sweep_c, rej_c, vol_ma20, current_price,
            all_levels=levels,  # Pass original for target selection
            operating_mode=operating_mode,
            squeeze_active=squeeze_active, cvd_divergence=cvd_divergence,
            funding_rate=funding_rate, liquidation_cascade=liquidation_cascade,
            market_state=market_state, adx_value=adx_value,
            trend_direction=trend_direction, session=session,
            atr_pct=atr_pct,
            min_rr=min_rr, volume_spike_multiplier=volume_spike_multiplier,
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
    operating_mode: str,  # NEW: 'normal' | 'quiet' | 'blocked'
    squeeze_active: bool,
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
    market_state: str,
    adx_value: float,
    trend_direction: Optional[str],
    session: Optional[str],
    atr_pct: Optional[float],
    min_rr: Optional[float],
    volume_spike_multiplier: Optional[float],
) -> Optional[SweepSignal]:

    lp    = level.price
    tol   = settings.sweep_tolerance_pct
    parts = candle_parts(rej_c)
    
    # Mode-specific min RR
    rr_min = (
        min_rr
        if min_rr is not None
        else (settings.quiet_min_rr if operating_mode == 'quiet' else settings.normal_min_rr)
    )
    
    # Mode-specific volume multiplier
    vol_mult = (
        volume_spike_multiplier
        if volume_spike_multiplier is not None
        else (settings.quiet_volume_spike_multiplier if operating_mode == 'quiet' else settings.normal_volume_spike_multiplier)
    )
    
    # Mode-specific wick ratio for rejection detection
    wick_ratio = (
        settings.quiet_rejection_wick_ratio if operating_mode == 'quiet'
        else settings.rejection_wick_ratio
    )

    # ── LONG setup: sweep of equal_lows ───────────────────────

    if level.pool_type == "equal_lows":
        swept    = float(sweep_c["low"]) < lp * (1 - tol)
        returned = float(sweep_c["close"]) > lp

        if not (swept and returned):
            if not swept:
                logger.debug(f"  ❌ [DIAG] LONG sweep FAIL: low={float(sweep_c['low']):.2f} not below level={lp:.2f} (tol={tol*100:.2f}%, threshold={lp*(1-tol):.2f})")
            elif not returned:
                logger.debug(f"  ❌ [DIAG] LONG sweep FAIL: close={float(sweep_c['close']):.2f} not above level={lp:.2f}")
            return None

        # Rejection candle: long LOWER wick
        if not _is_rejection(parts, direction="LONG", wick_ratio=wick_ratio):
            logger.debug(f"  ❌ [DIAG] LONG rejection FAIL: body={parts['body']:.2f} lower_wick={parts['lower_wick']:.2f} range={parts['range']:.2f} wick_ratio={wick_ratio}")
            return None

        direction = "LONG"
        entry_market = float(rej_c["close"])

        # Limit entry: 50% of sweep candle body (from low toward close)
        sweep_body_low  = min(float(sweep_c["open"]), float(sweep_c["close"]))
        sweep_body_high = max(float(sweep_c["open"]), float(sweep_c["close"]))
        entry_limit     = sweep_body_low + (sweep_body_high - sweep_body_low) * settings.limit_entry_pct
        stop_loss = _resolve_sweep_stop_loss(
            direction=direction,
            entry_reference=entry_limit,
            sweep_extreme=float(sweep_c["low"]),
            atr_pct=atr_pct,
            operating_mode=operating_mode,
        )

    # ── SHORT setup: sweep of equal_highs ─────────────────────

    elif level.pool_type == "equal_highs":
        swept    = float(sweep_c["high"]) > lp * (1 + tol)
        returned = float(sweep_c["close"]) < lp

        if not (swept and returned):
            if not swept:
                logger.debug(f"  ❌ [DIAG] SHORT sweep FAIL: high={float(sweep_c['high']):.2f} not above level={lp:.2f} (tol={tol*100:.2f}%, threshold={lp*(1+tol):.2f})")
            elif not returned:
                logger.debug(f"  ❌ [DIAG] SHORT sweep FAIL: close={float(sweep_c['close']):.2f} not below level={lp:.2f}")
            return None

        if not _is_rejection(parts, direction="SHORT", wick_ratio=wick_ratio):
            logger.debug(f"  ❌ [DIAG] SHORT rejection FAIL: body={parts['body']:.2f} upper_wick={parts['upper_wick']:.2f} range={parts['range']:.2f} wick_ratio={wick_ratio}")
            return None

        direction = "SHORT"
        entry_market = float(rej_c["close"])

        sweep_body_low  = min(float(sweep_c["open"]), float(sweep_c["close"]))
        sweep_body_high = max(float(sweep_c["open"]), float(sweep_c["close"]))
        entry_limit     = sweep_body_high - (sweep_body_high - sweep_body_low) * settings.limit_entry_pct
        stop_loss = _resolve_sweep_stop_loss(
            direction=direction,
            entry_reference=entry_limit,
            sweep_extreme=float(sweep_c["high"]),
            atr_pct=atr_pct,
            operating_mode=operating_mode,
        )

    else:
        return None

    execution_basis = settings.execution_basis
    rr_entry = entry_limit if execution_basis == "limit" and entry_limit is not None else entry_market

    # ── Target liquidity ──────────────────────────────────────

    target = select_target_level(all_levels, current_price, direction)
    take_profit, dist_to_target = resolve_take_profit(
        direction=direction,
        entry_price=rr_entry,
        stop_loss=stop_loss,
        current_price=current_price,
        operating_mode=operating_mode,
        target_price=target.price if target else None,
        fallback_rr=None if target else rr_min,
        logger=logger,
    )

    # ── RR check ──────────────────────────────────────────────

    rr_market = _calculate_rr(direction, entry_market, stop_loss, take_profit)
    rr_limit = _calculate_rr(direction, entry_limit, stop_loss, take_profit) if entry_limit is not None else None
    rr_selected = rr_limit if execution_basis == "limit" and rr_limit is not None else rr_market
    tp1_rr = settings.tp1_rr_multiple
    tp1_size_pct = settings.tp1_size_pct
    final_tp_size_pct = max(0.0, 1.0 - tp1_size_pct)
    tp1_entry = rr_entry
    tp1_price_candidate = _price_at_rr(direction, tp1_entry, stop_loss, tp1_rr)

    if (
        (direction == "LONG" and take_profit > tp1_price_candidate) or
        (direction == "SHORT" and take_profit < tp1_price_candidate)
    ):
        tp1_price = tp1_price_candidate
    else:
        tp1_price = None
        tp1_size_pct = None
        final_tp_size_pct = 1.0

    if rr_selected < rr_min:
        logger.debug(f"RR {rr_selected:.2f} < {rr_min} at level {lp:.2f} ({execution_basis})")
        return None

    # ── Distance to target check ──────────────────────────────

    if dist_to_target < settings.liquidity_min_distance_pct:
        logger.debug(f"Target too close: {dist_to_target*100:.2f}%")
        return None

    # ── Volume spike ──────────────────────────────────────────

    vol_sweep = float(sweep_c["volume"])
    vol_rej   = float(rej_c["volume"])
    volume_spike = (vol_sweep >= vol_ma20 * vol_mult or
                    vol_rej   >= vol_ma20 * vol_mult)

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
        level_freshness_score=level.freshness_score,  # NEW: freshness bonus
        volume_spike_multiplier=vol_mult,
    )
    apply_adx_counter_trend_penalty(conf, adx_value, is_counter)

    return SweepSignal(
        direction=direction,
        entry_market=round(entry_market, 2),
        entry_limit=round(entry_limit, 2),
        stop_loss=round(stop_loss, 2),
        tp1_price=round(tp1_price, 2) if tp1_price is not None else None,
        tp1_rr=tp1_rr if tp1_price is not None else None,
        tp1_size_pct=tp1_size_pct,
        final_tp_size_pct=final_tp_size_pct,
        take_profit=round(take_profit, 2),
        rr_ratio=round(rr_selected, 2),
        rr_market=round(rr_market, 2),
        rr_limit=round(rr_limit, 2) if rr_limit is not None else None,
        execution_basis=execution_basis,
        swept_level=level,
        target_level=target,
        volume_spike=volume_spike,
        confidence=conf,
    )


def _is_rejection(parts: dict, direction: str, wick_ratio: float = 2.5) -> bool:
    """
    Pin-bar rules:
      • wick ≥ wick_ratio × body (default 2.5, QUIET mode uses 2.0)
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

    wick_ok = wick >= wick_ratio * body
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
        "signal_id":   _make_signal_id(settings.symbol, sig.direction, sig.entry_market),
        "pair":        settings.symbol,
        "strategy":    "sweep_reversal",
        "direction":   sig.direction,
        "session":     session,
        "entry_market": sig.entry_market,
        "entry_limit":  sig.entry_limit,
        "stop_loss":    sig.stop_loss,
        "tp1_price":    sig.tp1_price,
        "tp1_rr":       sig.tp1_rr,
        "tp1_size_pct": sig.tp1_size_pct,
        "final_tp_size_pct": sig.final_tp_size_pct,
        "take_profit":  sig.take_profit,
        "rr_ratio":     sig.rr_ratio,
        "rr_market":    sig.rr_market,
        "rr_limit":     sig.rr_limit,
        "execution_basis": sig.execution_basis,
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
