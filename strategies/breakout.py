"""
Volatility Breakout Strategy

Conditions:
  • Squeeze active on 4H (detected by squeeze.py)
  • Breakout candle on 15m: close breaks above upper BB OR below lower BB
    OR close breaks beyond a known liquidity level
  • Entry: market (breakout candle close)
  • SL: fixed 0.7% from entry
  • TP: 2–4% from entry (aggressive)
  • No ADX filter (by spec)
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config.settings import settings
from engine.confidence import ConfidenceResult, compute_confidence
from engine.indicators import bollinger, volume_ma
from strategies.target_resolver import resolve_take_profit

logger = logging.getLogger(__name__)


@dataclass
class BreakoutSignal:
    direction:    str        # LONG | SHORT
    entry_market: float
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
    sl_pct_used:  float
    sl_pct_raw:   Optional[float]
    sl_mode:      str
    breakout_type: str       # bb_upper | bb_lower | level_break
    confidence:   ConfidenceResult


def _make_signal_id(pair: str, direction: str, entry: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return hashlib.sha256(f"{pair}{direction}{entry:.2f}{now}break".encode()).hexdigest()[:16]


def resolve_breakout_sl_pct(
    atr_pct: Optional[float],
    operating_mode: str = "normal",
) -> tuple[float, Optional[float], str]:
    """
    Resolve breakout stop size as a percentage of entry.

    Returns:
      sl_pct_used: final clamped percent as fraction
      raw_sl_pct: raw ATR-based percent before clamp, if available
      sl_mode: descriptive mode for logs
    """
    if atr_pct is None or atr_pct <= 0:
        return settings.breakout_sl_pct, None, "fixed_fallback"

    atr_mult = (
        settings.breakout_sl_quiet_atr_mult
        if operating_mode == "quiet"
        else settings.breakout_sl_normal_atr_mult
    )
    raw_sl_pct = atr_pct * atr_mult
    sl_pct_used = min(
        max(raw_sl_pct, settings.breakout_sl_min_pct),
        settings.breakout_sl_max_pct,
    )

    if sl_pct_used == settings.breakout_sl_min_pct and raw_sl_pct < sl_pct_used:
        sl_mode = "adaptive_min_clamp"
    elif sl_pct_used == settings.breakout_sl_max_pct and raw_sl_pct > sl_pct_used:
        sl_mode = "adaptive_max_clamp"
    else:
        sl_mode = "adaptive_raw"

    return sl_pct_used, raw_sl_pct, sl_mode


def _price_at_rr(direction: str, entry: float, stop_loss: float, rr_multiple: float) -> float:
    risk = abs(entry - stop_loss)
    if direction == "LONG":
        return entry + risk * rr_multiple
    return entry - risk * rr_multiple


def check_breakout(
    df_15m: pd.DataFrame,
    squeeze_active: bool,
    session: Optional[str],
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
    adx_value: float,
    atr_pct: Optional[float] = None,
    operating_mode: str = "normal",
    min_rr: Optional[float] = None,
    volume_spike_multiplier: Optional[float] = None,
) -> Optional[BreakoutSignal]:
    """
    Returns BreakoutSignal or None.
    squeeze_active must be True (caller verifies 4H squeeze).
    """
    if not squeeze_active:
        return None
    if len(df_15m) < 25:
        return None

    bb       = bollinger(df_15m)
    last     = df_15m.iloc[-1]
    vol_ma20 = volume_ma(df_15m, 20).iloc[-1]

    close  = float(last["close"])
    upper  = float(bb["upper"].iloc[-1])
    lower  = float(bb["lower"].iloc[-1])

    direction      = None
    breakout_type  = None
    rr_min = min_rr if min_rr is not None else settings.min_rr
    vol_mult = (
        volume_spike_multiplier
        if volume_spike_multiplier is not None
        else settings.volume_spike_multiplier
    )
    volume_spike   = float(last["volume"]) >= vol_ma20 * vol_mult

    if close > upper:
        direction     = "LONG"
        breakout_type = "bb_upper"
    elif close < lower:
        direction     = "SHORT"
        breakout_type = "bb_lower"
    else:
        return None

    entry = close
    sl_pct, raw_sl_pct, sl_mode = resolve_breakout_sl_pct(
        atr_pct=atr_pct,
        operating_mode=operating_mode,
    )
    tp_pct = (settings.breakout_tp_min + settings.breakout_tp_max) / 2  # 3%

    if direction == "LONG":
        stop_loss   = round(entry * (1 - sl_pct), 2)
    else:
        stop_loss   = round(entry * (1 + sl_pct), 2)

    take_profit, _ = resolve_take_profit(
        direction=direction,
        entry_price=entry,
        stop_loss=stop_loss,
        current_price=entry,
        operating_mode=operating_mode,
        fallback_pct=tp_pct,
        logger=logger,
    )
    take_profit = round(take_profit, 2)

    risk   = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    rr     = reward / risk if risk else 0
    tp1_price_candidate = _price_at_rr(direction, entry, stop_loss, settings.tp1_rr_multiple)
    if (
        (direction == "LONG" and take_profit > tp1_price_candidate) or
        (direction == "SHORT" and take_profit < tp1_price_candidate)
    ):
        tp1_price = round(tp1_price_candidate, 2)
        tp1_rr = settings.tp1_rr_multiple
        tp1_size_pct = settings.tp1_size_pct
        final_tp_size_pct = max(0.0, 1.0 - settings.tp1_size_pct)
    else:
        tp1_price = None
        tp1_rr = None
        tp1_size_pct = None
        final_tp_size_pct = 1.0

    if rr < rr_min:
        return None

    conf = compute_confidence(
        strategy="breakout",
        direction=direction,
        session=session,
        market_state="ranging",  # breakout strategy ignores ADX
        adx_value=adx_value,
        volume_spike=volume_spike,
        squeeze_active=squeeze_active,
        cvd_divergence=cvd_divergence,
        funding_rate=funding_rate,
        liquidation_cascade=liquidation_cascade,
        volume_spike_multiplier=vol_mult,
    )

    return BreakoutSignal(
        direction=direction,
        entry_market=round(entry, 2),
        stop_loss=stop_loss,
        tp1_price=tp1_price,
        tp1_rr=tp1_rr,
        tp1_size_pct=tp1_size_pct,
        final_tp_size_pct=final_tp_size_pct,
        take_profit=take_profit,
        rr_ratio=round(rr, 2),
        rr_market=round(rr, 2),
        rr_limit=None,
        execution_basis="market",
        sl_pct_used=sl_pct,
        sl_pct_raw=raw_sl_pct,
        sl_mode=sl_mode,
        breakout_type=breakout_type,
        confidence=conf,
    )


def signal_to_dict(
    sig: BreakoutSignal,
    session: str,
    volatility_regime: str,
    adx_value: float,
    atr_pct: float,
    oi_change_pct: Optional[float],
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
) -> dict:
    return {
        "signal_id":   _make_signal_id(settings.symbol, sig.direction, sig.entry_market),
        "pair":        settings.symbol,
        "strategy":    "breakout",
        "direction":   sig.direction,
        "session":     session,
        "entry_market": sig.entry_market,
        "entry_limit":  None,
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
        "position_size_pct": None,
        "confidence_score":  sig.confidence.score,
        "confidence_breakdown": json.dumps(sig.confidence.breakdown_json),
        "market_state":      "ranging",
        "volatility_regime": volatility_regime,
        "adx_value":         adx_value,
        "atr_pct":           atr_pct,
        "target_liquidity_price": None,
        "target_liquidity_tf":    None,
        "target_liquidity_type":  None,
        "distance_to_target_pct": None,
        "cvd_divergence":      cvd_divergence,
        "oi_change_pct":       oi_change_pct,
        "liquidation_cascade": liquidation_cascade,
        "funding_rate":        funding_rate,
        "squeeze_active":      True,
    }
