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

logger = logging.getLogger(__name__)


@dataclass
class BreakoutSignal:
    direction:    str        # LONG | SHORT
    entry_market: float
    stop_loss:    float
    take_profit:  float
    rr_ratio:     float
    breakout_type: str       # bb_upper | bb_lower | level_break
    confidence:   ConfidenceResult


def _make_signal_id(direction: str, entry: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return hashlib.sha256(f"{direction}{entry:.2f}{now}break".encode()).hexdigest()[:16]


def check_breakout(
    df_15m: pd.DataFrame,
    squeeze_active: bool,
    session: Optional[str],
    cvd_divergence: Optional[str],
    funding_rate: float,
    liquidation_cascade: bool,
    adx_value: float,
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
    volume_spike   = float(last["volume"]) >= vol_ma20 * settings.volume_spike_multiplier

    if close > upper:
        direction     = "LONG"
        breakout_type = "bb_upper"
    elif close < lower:
        direction     = "SHORT"
        breakout_type = "bb_lower"
    else:
        return None

    entry = close
    sl_pct = settings.breakout_sl_pct   # 0.7%
    tp_pct = (settings.breakout_tp_min + settings.breakout_tp_max) / 2  # 3%

    if direction == "LONG":
        stop_loss   = round(entry * (1 - sl_pct), 2)
        take_profit = round(entry * (1 + tp_pct), 2)
    else:
        stop_loss   = round(entry * (1 + sl_pct), 2)
        take_profit = round(entry * (1 - tp_pct), 2)

    risk   = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    rr     = reward / risk if risk else 0

    if rr < settings.min_rr:
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
    )

    return BreakoutSignal(
        direction=direction,
        entry_market=round(entry, 2),
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr_ratio=round(rr, 2),
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
        "signal_id":   _make_signal_id(sig.direction, sig.entry_market),
        "pair":        settings.symbol,
        "strategy":    "breakout",
        "direction":   sig.direction,
        "session":     session,
        "entry_market": sig.entry_market,
        "entry_limit":  None,
        "stop_loss":    sig.stop_loss,
        "take_profit":  sig.take_profit,
        "rr_ratio":     sig.rr_ratio,
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
