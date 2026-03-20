"""
Order Flow context evaluation.

OI Liquidation Cascade:
    OI dropped ≥ 2% AND price moved ≥ 1.2% in last 60 minutes → cascade

Funding Rate:
    > +0.05%  → market overleveraged LONG
    < −0.05%  → market overleveraged SHORT
    > +0.10%  → extreme LONG (blocks LONG signals)
    < −0.10%  → extreme SHORT (blocks SHORT signals)
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from config.settings import settings


@dataclass
class OrderFlowContext:
    funding_rate:         float
    oi_change_pct:        Optional[float]   # None if no prior snapshot
    liquidation_cascade:  bool
    cvd_divergence:       Optional[str]     # bullish | bearish | None
    current_cvd:          float


def evaluate_funding(
    funding_rate: float,
    direction: str,
) -> Tuple[int, str]:
    """
    Returns (confidence_delta, reason_label).
    direction: 'LONG' or 'SHORT'
    """
    fr  = funding_rate
    ext = settings.funding_extreme_threshold   # 0.0005 = 0.05%
    blk = settings.funding_block_threshold     # 0.001  = 0.10%

    # Hard blocks
    if fr >  blk and direction == "LONG":
        return -15, f"Funding extreme +{fr*100:.3f}% blocks LONG"
    if fr < -blk and direction == "SHORT":
        return -15, f"Funding extreme {fr*100:.3f}% blocks SHORT"

    # Bonus: signal is counter-funding
    if fr >  ext and direction == "SHORT":
        return +10, f"Funding +{fr*100:.3f}% → counter SHORT"
    if fr < -ext and direction == "LONG":
        return +10, f"Funding {fr*100:.3f}% → counter LONG"

    return 0, ""


def evaluate_oi_cascade(
    oi_now: float,
    oi_60m_ago: Optional[float],
    price_now: float,
    price_60m_ago: Optional[float],
) -> Tuple[bool, Optional[float]]:
    """
    Returns (cascade_detected, oi_change_pct).
    cascade_detected=True if OI dropped ≥ 2% AND price moved ≥ 1.2%.
    """
    if oi_60m_ago is None or price_60m_ago is None or oi_60m_ago == 0:
        return False, None

    oi_chg    = (oi_now - oi_60m_ago) / oi_60m_ago
    price_chg = abs(price_now - price_60m_ago) / price_60m_ago

    cascade = (
        oi_chg <= -settings.oi_drop_threshold_pct and
        price_chg >= settings.oi_price_move_pct
    )
    return cascade, round(oi_chg * 100, 3)
