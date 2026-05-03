"""
Enhanced Logging for Crypto Signal Bot
Provides detailed analysis logs for debugging and transparency
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _level_field(level: Any, field: str):
    """Read liquidity level fields from dataclasses/objects or legacy dict payloads."""
    if isinstance(level, dict):
        return level[field]
    return getattr(level, field)


def log_analysis_summary(
    cycle_time: str,
    market_state: str,
    volatility_regime: str,
    session: Optional[str],
    adx_value: float,
    atr_pct: float,
    squeeze_active: bool,
    liquidity_levels: int,
    cvd_divergence: Optional[str],
    oi_cascade: bool,
    funding_rate: float,
    confidence_score: int = 0,
    confidence_breakdown: Optional[Dict] = None,
    signal_found: bool = False,
    blockers: Optional[List[str]] = None,
):
    """
    Log comprehensive analysis summary for each cycle.
    
    Example output:
    ═══════════════════════════════════════════════════════
    ANALYSIS CYCLE SUMMARY — 2026-03-20 13:00:03 UTC
    ═══════════════════════════════════════════════════════
    
    Market State:
      • ADX: 21.6 (dead_zone)
      • ATR%: 0.35% (low volatility)
      • Session: NY (+20 points)
    
    Liquidity & Order Flow:
      • Levels found: 12 (4 active)
      • Squeeze active: No
      • CVD divergence: None
      • OI cascade: No
      • Funding rate: 0.015%
    
    Signal Detection:
      • Signal found: No
      • Confidence score: 45/100
      • Top blockers:
        - Low volatility (-30)
        - ADX dead zone (-25)
        - No sweep pattern (-30)
    
    Decision: SKIP (confidence 45 < threshold 65)
    ═══════════════════════════════════════════════════════
    """
    
    logger.info("═" * 60)
    logger.info(f"ANALYSIS CYCLE SUMMARY — {cycle_time}")
    logger.info("═" * 60)
    
    # Market State
    logger.info("")
    logger.info("Market State:")
    logger.info(f"  • ADX: {adx_value:.1f} ({market_state})")
    logger.info(f"  • ATR%: {atr_pct*100:.2f}% ({volatility_regime} volatility)")
    if session:
        logger.info(f"  • Session: {session.upper()} (+20 points)")
    else:
        logger.info("  • Session: None (off-hours) (-30 points)")

    # Liquidity & Order Flow
    logger.info("")
    logger.info("Liquidity & Order Flow:")
    logger.info(f"  • Levels found: {liquidity_levels}")
    logger.info(f"  • Squeeze active: {'Yes' if squeeze_active else 'No'}")

    if cvd_divergence:
        logger.info(f"  • CVD divergence: {cvd_divergence.upper()} (+15 points)")
    else:
        logger.info("  • CVD divergence: None")

    logger.info(f"  • OI cascade: {'Yes' if oi_cascade else 'No'}")
    logger.info(f"  • Funding rate: {funding_rate*100:.3f}%")

    # Signal Detection
    logger.info("")
    logger.info("Signal Detection:")
    logger.info(f"  • Signal found: {'Yes' if signal_found else 'No'}")

    if confidence_breakdown:
        logger.info(f"  • Confidence score: {confidence_score}/100")
        logger.info("  • Breakdown:")
        for factor, delta in confidence_breakdown.items():
            sign = "+" if delta >= 0 else ""
            logger.info(f"    {sign}{delta} {factor}")

    # Blockers
    if blockers:
        logger.info("  • Top blockers:")
        for blocker in blockers[:3]:
            logger.info(f"    - {blocker}")

    # Decision
    logger.info("")
    if signal_found and confidence_score >= 65:
        logger.info(f"✅ Decision: SEND SIGNAL (confidence {confidence_score} ≥ 65)")
    elif signal_found:
        logger.info(f"❌ Decision: SKIP (confidence {confidence_score} < 65)")
    else:
        logger.info("❌ Decision: NO SIGNAL (market conditions not met)")
    
    logger.info("═" * 60)


def log_liquidity_levels(levels: List[Any]):
    """Log detected liquidity levels."""
    if not levels:
        logger.info("🎯 No liquidity levels detected")
        return
    
    logger.info(f"🎯 Detected {len(levels)} liquidity levels:")
    for level in sorted(levels, key=lambda x: _level_field(x, "strength"), reverse=True)[:5]:
        emoji = "🔴" if _level_field(level, "pool_type") == "equal_highs" else "🟢"
        logger.info(
            f"  {emoji} {_level_field(level, 'timeframe')} {_level_field(level, 'pool_type')}: "
            f"${_level_field(level, 'price'):,.2f} (touches: {_level_field(level, 'touch_count')}, "
            f"strength: {_level_field(level, 'strength'):.2f}, "
            f"score: {_level_field(level, 'level_score')}, "
            f"fresh: {_level_field(level, 'freshness_score')})"
        )

    top_by_score = sorted(
        levels,
        key=lambda x: (
            _level_field(x, "level_score"),
            _level_field(x, "freshness_score"),
            _level_field(x, "strength"),
        ),
        reverse=True,
    )[:5]
    logger.info("🎯 Top liquidity levels by quality:")
    for level in top_by_score:
        emoji = "🔴" if _level_field(level, "pool_type") == "equal_highs" else "🟢"
        logger.info(
            f"  {emoji} {_level_field(level, 'timeframe')} {_level_field(level, 'pool_type')}: "
            f"${_level_field(level, 'price'):,.2f} (score: {_level_field(level, 'level_score')}, "
            f"fresh: {_level_field(level, 'freshness_score')}, "
            f"touches: {_level_field(level, 'touch_count')}, "
            f"strength: {_level_field(level, 'strength'):.2f})"
        )


def log_liquidity_filter_diagnostics(
    *,
    operating_mode: str,
    min_level_score: int,
    levels: List[Any],
    filtered_levels: List[Any],
):
    """Log how many liquidity levels pass the level-score filter used by sweep detection."""
    total = len(levels)
    passed = len(filtered_levels)
    filtered_out = total - passed
    logger.info(
        f"🎯 Liquidity filter ({operating_mode.upper()}): "
        f"{passed}/{total} levels pass level_score >= {min_level_score}"
    )
    if total:
        stale_count = sum(1 for lvl in levels if _level_field(lvl, "touch_count") > 15)
        logger.info(
            f"  Filter stats: filtered_out={filtered_out}, "
            f"stale_touch_gt15={stale_count}"
        )

    if filtered_levels:
        logger.info("  Top eligible levels:")
        for level in sorted(
            filtered_levels,
            key=lambda x: (
                _level_field(x, "level_score"),
                _level_field(x, "freshness_score"),
                _level_field(x, "strength"),
            ),
            reverse=True,
        )[:3]:
            logger.info(
                f"    • {_level_field(level, 'timeframe')} {_level_field(level, 'pool_type')} "
                f"${_level_field(level, 'price'):,.2f} "
                f"(score={_level_field(level, 'level_score')}, "
                f"fresh={_level_field(level, 'freshness_score')}, "
                f"touches={_level_field(level, 'touch_count')})"
            )
    else:
        logger.info("  Top eligible levels: none")

    if filtered_out > 0:
        logger.info("  Top filtered-out levels:")
        excluded = [lvl for lvl in levels if lvl not in filtered_levels]
        for level in sorted(
            excluded,
            key=lambda x: (
                _level_field(x, "touch_count"),
                -_level_field(x, "freshness_score"),
                _level_field(x, "strength"),
            ),
            reverse=True,
        )[:3]:
            logger.info(
                f"    • {_level_field(level, 'timeframe')} {_level_field(level, 'pool_type')} "
                f"${_level_field(level, 'price'):,.2f} "
                f"(score={_level_field(level, 'level_score')}, "
                f"fresh={_level_field(level, 'freshness_score')}, "
                f"touches={_level_field(level, 'touch_count')})"
            )


def log_confidence_calculation(
    strategy: str,
    base_score: int,
    factors: Dict[str, int],
    final_score: int,
):
    """Log confidence score calculation."""
    logger.info(f"📊 Confidence Calculation ({strategy}):")
    logger.info(f"  Base score: {base_score}")
    logger.info("  Factors:")
    for factor, delta in factors.items():
        sign = "+" if delta >= 0 else ""
        logger.info(f"    {sign}{delta} {factor}")
    logger.info(f"  Final score: {final_score}/100")

    if final_score >= 65:
        logger.info("  ✅ PASS (≥ 65)")
    elif final_score >= 50:
        logger.info(f"  ⚠️  CLOSE (50-64, needed {65-final_score} more points)")
    else:
        logger.info(f"  ❌ FAIL (< 50, needed {65-final_score} more points)")


def log_hourly_summary(
    hour: int,
    cycles: int,
    signals: int,
    avg_confidence: float,
    top_blockers: Dict[str, int],
):
    """Log hourly summary."""
    logger.info("\n" + "═" * 60)
    logger.info(f"HOURLY SUMMARY — Hour {hour:02d}:00 UTC")
    logger.info("═" * 60)
    logger.info(f"  • Analysis cycles: {cycles}")
    logger.info(f"  • Signals generated: {signals}")
    logger.info(f"  • Avg confidence: {avg_confidence:.1f}")
    
    if top_blockers:
        logger.info("  • Top blockers this hour:")
        for blocker, count in sorted(top_blockers.items(), key=lambda x: x[1], reverse=True)[:3]:
            logger.info(f"    - {blocker}: {count} times")
    
    logger.info("═" * 60 + "\n")
