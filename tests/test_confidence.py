"""
Tests for confidence.py with freshness bonus
"""
import io
import logging
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.confidence import (
    compute_confidence,
    apply_adx_counter_trend_penalty,
)
from engine.pipeline import _log_confidence_fail


def _base(**overrides):
    defaults = dict(
        strategy="sweep_reversal",
        direction="LONG",
        session="london",
        market_state="ranging",
        adx_value=20.0,
        volume_spike=True,
        squeeze_active=False,
        cvd_divergence=None,
        funding_rate=0.0,
        liquidation_cascade=False,
        level_freshness_score=0,  # Default: stale level
    )
    defaults.update(overrides)
    return defaults


def test_minimum_sweep_score():
    """Base sweep + volume + session → 30+20+20 = 70, -10 stale = 60."""
    r = compute_confidence(**_base())
    assert r.score == 60, f"Expected 60, got {r.score}"
    print(f"[OK] Base sweep score: {r.score}")


def test_all_bonuses():
    """Max positive factors (no negatives)."""
    r = compute_confidence(**_base(
        squeeze_active=True,
        cvd_divergence="bullish",
        funding_rate=-0.0006,
        liquidation_cascade=True,
        market_state="trending",
        adx_value=28.0,
    ))
    # 30 + 20 + 20 + 20 + 15 + 10 + 15 + 10 = 140, -10 stale = 130
    assert r.score == 130, f"Expected 130, got {r.score}\n{r.breakdown_str}"
    print(f"[OK] All-bonus score: {r.score}")


def test_funding_block_long():
    """Funding >+0.10% blocks LONG → -15."""
    r = compute_confidence(**_base(funding_rate=0.0011))
    # 30 + 20 + 20 - 15 = 55, -10 stale = 45
    assert r.score == 45, f"Expected 45, got {r.score}"
    print(f"[OK] Funding block LONG: {r.score}")


def test_funding_block_short():
    """Funding <-0.10% blocks SHORT → -15."""
    r = compute_confidence(**_base(direction="SHORT", funding_rate=-0.0011))
    # 30 + 20 + 20 - 15 = 55, -10 stale = 45
    assert r.score == 45, f"Expected 45, got {r.score}"
    print(f"[OK] Funding block SHORT: {r.score}")


def test_no_session_penalty():
    """No session → -30 instead of +20."""
    r = compute_confidence(**_base(session=None))
    # 30 + 20 - 30 = 20, -10 stale = 10
    assert r.score == 10, f"Expected 10, got {r.score}"
    print(f"[OK] No session score: {r.score}")


def test_adx_counter_trend_penalty():
    """ADX > 40 counter-trend → additional -25."""
    r = compute_confidence(**_base(market_state="trending", adx_value=45.0))
    apply_adx_counter_trend_penalty(r, adx_value=45.0, is_counter_trend=True)
    # 30 + 20 + 20 + 10 - 25 = 55, -10 stale = 45
    assert r.score == 45, f"Expected 45, got {r.score}\n{r.breakdown_str}"
    print(f"[OK] ADX counter-trend penalty: {r.score}")


def test_session_no_double_count():
    """Session bonus counted once."""
    r = compute_confidence(**_base())
    session_factors = [f for f in r.factors if "Session" in f.label]
    assert len(session_factors) == 1, "Session should be counted once"
    print("[OK] Session no double count")


def test_cvd_wrong_direction_no_bonus():
    """CVD bearish for LONG → no bonus."""
    r = compute_confidence(**_base(cvd_divergence="bearish"))
    cvd_factors = [f for f in r.factors if "CVD" in f.label]
    assert len(cvd_factors) == 0, "Wrong CVD direction should give no bonus"
    print("[OK] CVD wrong direction no bonus")


def test_fresh_level_bonus():
    """Fresh level (score 8+) → +10 bonus."""
    r = compute_confidence(**_base(level_freshness_score=9))
    # Should have +10 for fresh level
    fresh_factors = [f for f in r.factors if "Fresh" in f.label]
    assert len(fresh_factors) == 1, "Fresh level should give +10"
    assert fresh_factors[0].delta == 10, "Fresh level bonus should be +10"
    print(f"[OK] Fresh level bonus: {r.score}")


def test_stale_level_penalty():
    """Stale level (score 0-2) → -10 penalty."""
    r = compute_confidence(**_base(level_freshness_score=1))
    # Should have -10 for stale level
    stale_factors = [f for f in r.factors if "Stale" in f.label]
    assert len(stale_factors) == 1, "Stale level should give -10"
    assert stale_factors[0].delta == -10, "Stale level penalty should be -10"
    print(f"[OK] Stale level penalty: {r.score}")


def test_confidence_fail_logging_includes_breakdown():
    """Pipeline should log explicit confidence fail details."""
    r = compute_confidence(**_base(funding_rate=0.0011))  # 45 with stale
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    pipeline_logger = logging.getLogger("engine.pipeline")
    old_level = pipeline_logger.level
    pipeline_logger.setLevel(logging.INFO)
    pipeline_logger.addHandler(handler)
    try:
        _log_confidence_fail("Sweep", r, threshold=65)
    finally:
        pipeline_logger.removeHandler(handler)
        pipeline_logger.setLevel(old_level)

    text = stream.getvalue()
    assert "CONFIDENCE FAIL (Sweep): 45 < 65" in text
    assert "+30 Liquidity sweep confirmed" in text
    assert "-15 Funding +0.110% blocks LONG" in text
    print("[OK] Confidence fail logging includes breakdown")


def test_volume_spike_label_uses_actual_multiplier():
    r = compute_confidence(**_base(
        volume_spike=True,
        volume_spike_multiplier=1.05,
    ))
    labels = [f.label for f in r.factors]
    assert "Volume spike ≥1.05×" in labels
    print("[OK] Volume spike label uses actual multiplier")


if __name__ == "__main__":
    test_minimum_sweep_score()
    test_all_bonuses()
    test_funding_block_long()
    test_funding_block_short()
    test_no_session_penalty()
    test_adx_counter_trend_penalty()
    test_session_no_double_count()
    test_cvd_wrong_direction_no_bonus()
    test_fresh_level_bonus()
    test_stale_level_penalty()
    test_confidence_fail_logging_includes_breakdown()
    test_volume_spike_label_uses_actual_multiplier()
    
    print("\n" + "="*60)
    print("  [OK] ALL CONFIDENCE TESTS PASSED!")
    print("="*60)
