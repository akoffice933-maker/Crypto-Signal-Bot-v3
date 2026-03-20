"""
Confidence Score Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Factor                          Delta   Condition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Liquidity sweep confirmed        +30    sweep_reversal strategy
Volume spike                     +20    vol ≥ 1.2× MA20
Session active                   +20    asian / london / ny  (once only)
Volatility squeeze (4h)          +20    squeeze active
Trend alignment (ADX >25)        +10    ADX >25, signal WITH trend
CVD divergence                   +15    classic divergence
Funding extreme (counter)        +10    >0.05% counter-direction
Liquidation cascade              +15    OI drop + price move
ADX >40 against trend            −25    ADX >40 AND signal against trend
Funding >+0.10% + LONG           −15    extreme funding blocks
Funding <−0.10% + SHORT          −15    extreme funding blocks
Outside all sessions             −30    (filtered earlier, shown for info)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No upper cap.  Threshold for signal: ≥ 65.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ScoreFactor:
    label: str
    delta: int

    def __str__(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"{sign}{self.delta} {self.label}"


@dataclass
class ConfidenceResult:
    score:   int
    factors: List[ScoreFactor] = field(default_factory=list)

    def add(self, label: str, delta: int):
        self.score += delta
        self.factors.append(ScoreFactor(label, delta))

    @property
    def breakdown_str(self) -> str:
        return "\n".join(str(f) for f in self.factors)

    @property
    def breakdown_json(self) -> list:
        return [{"factor": f.label, "delta": f.delta} for f in self.factors]


def compute_confidence(
    *,
    strategy: str,                         # sweep_reversal | breakout
    direction: str,                        # LONG | SHORT
    session: Optional[str],                # asian | london | ny | None
    market_state: str,                     # trending | ranging | dead_zone
    adx_value: float,
    volume_spike: bool,
    squeeze_active: bool,
    cvd_divergence: Optional[str],         # bullish | bearish | None
    funding_rate: float,
    liquidation_cascade: bool,
) -> ConfidenceResult:

    result = ConfidenceResult(score=0)

    # ── Base factor: strategy-specific ────────────────────────

    if strategy == "sweep_reversal":
        result.add("Liquidity sweep confirmed", +30)
    elif strategy == "breakout":
        result.add("Squeeze breakout", +25)   # slightly less certain

    # ── Volume spike ──────────────────────────────────────────

    if volume_spike:
        result.add("Volume spike ≥1.2×", +20)

    # ── Session (once, no double-counting) ───────────────────

    if session:
        result.add(f"Session: {session}", +20)
    else:
        result.add("Outside sessions", -30)

    # ── Squeeze ───────────────────────────────────────────────

    if squeeze_active:
        result.add("Volatility squeeze (4h)", +20)

    # ── Trend alignment ───────────────────────────────────────
    # +10 whenever market is trending (ADX > 25).
    # Counter-trend penalty (-25 when ADX > 40) is applied separately
    # via apply_adx_counter_trend_penalty() after this function returns.

    if market_state == "trending" and adx_value > 25:
        result.add(f"Trend alignment (ADX {adx_value:.0f})", +10)

    # ── CVD divergence ────────────────────────────────────────

    if cvd_divergence:
        cvd_matches = (
            (direction == "LONG"  and cvd_divergence == "bullish") or
            (direction == "SHORT" and cvd_divergence == "bearish")
        )
        if cvd_matches:
            result.add(f"CVD {cvd_divergence} divergence", +15)

    # ── Funding rate ──────────────────────────────────────────

    fr = funding_rate
    if fr > 0.001 and direction == "LONG":
        result.add(f"Funding +{fr*100:.3f}% blocks LONG", -15)
    elif fr < -0.001 and direction == "SHORT":
        result.add(f"Funding {fr*100:.3f}% blocks SHORT", -15)
    elif fr > 0.0005 and direction == "SHORT":
        result.add(f"Funding +{fr*100:.3f}% → counter SHORT", +10)
    elif fr < -0.0005 and direction == "LONG":
        result.add(f"Funding {fr*100:.3f}% → counter LONG", +10)

    # ── Liquidation cascade ───────────────────────────────────

    if liquidation_cascade:
        result.add("Liquidation cascade (OI drop)", +15)

    return result


def apply_adx_counter_trend_penalty(
    result: ConfidenceResult,
    adx_value: float,
    is_counter_trend: bool,
) -> ConfidenceResult:
    """
    Call after compute_confidence if direction is against the trend.
    ADX > 40 AND counter-trend → -25.
    """
    if is_counter_trend and adx_value > 40:
        result.add(f"ADX {adx_value:.0f} against trend", -25)
    return result
