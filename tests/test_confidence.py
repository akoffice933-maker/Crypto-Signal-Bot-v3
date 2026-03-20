import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.confidence import compute_confidence, apply_adx_counter_trend_penalty


def _base(**overrides):
    defaults = dict(
        strategy="sweep_reversal",
        direction="LONG",
        session="london",
        market_state="ranging",
        adx_value=18.0,
        volume_spike=True,
        squeeze_active=False,
        cvd_divergence=None,
        funding_rate=0.0,
        liquidation_cascade=False,
    )
    defaults.update(overrides)
    return defaults


def test_minimum_sweep_score():
    """Base sweep + volume + session → 30+20+20 = 70 ≥ threshold."""
    r = compute_confidence(**_base())
    assert r.score == 70, f"Expected 70, got {r.score}"
    print(f"✅ Base sweep score: {r.score}")


def test_all_bonuses():
    """Max positive factors (no negatives)."""
    r = compute_confidence(**_base(
        squeeze_active=True,
        cvd_divergence="bullish",
        funding_rate=-0.0006,       # negative → counter LONG → +10
        liquidation_cascade=True,
        market_state="trending",
        adx_value=28.0,
    ))
    # 30 + 20 + 20 + 20 + 15 + 10 + 15 + 10 = 140
    assert r.score == 140, f"Expected 140, got {r.score}\n{r.breakdown_str}"
    print(f"✅ All-bonus score: {r.score}")


def test_funding_block_long():
    """Funding >+0.10% blocks LONG → -15."""
    r = compute_confidence(**_base(funding_rate=0.0011))
    # 30 + 20 + 20 - 15 = 55
    assert r.score == 55, f"Expected 55, got {r.score}"
    print(f"✅ Funding block LONG: {r.score}")


def test_funding_block_short():
    """Funding <-0.10% blocks SHORT → -15."""
    r = compute_confidence(**_base(direction="SHORT", funding_rate=-0.0011))
    assert r.score == 55, f"Expected 55, got {r.score}"
    print(f"✅ Funding block SHORT: {r.score}")


def test_no_session_penalty():
    """No session → -30 instead of +20."""
    r = compute_confidence(**_base(session=None))
    # 30 + 20 - 30 = 20
    assert r.score == 20, f"Expected 20, got {r.score}"
    print(f"✅ No session score: {r.score}")


def test_adx_counter_trend_penalty():
    """ADX > 40 counter-trend → additional -25."""
    r = compute_confidence(**_base(market_state="trending", adx_value=45.0))
    apply_adx_counter_trend_penalty(r, adx_value=45.0, is_counter_trend=True)
    # 30 + 20 + 20 + 10 - 25 = 55
    assert r.score == 55, f"Expected 55, got {r.score}\n{r.breakdown_str}"
    print(f"✅ ADX counter-trend penalty: {r.score}")


def test_session_no_double_count():
    """Session adds +20 exactly once regardless of overlap logic."""
    r = compute_confidence(**_base(session="london"))
    session_factors = [f for f in r.factors if "Session" in f.label]
    assert len(session_factors) == 1, "Session counted more than once!"
    assert session_factors[0].delta == 20
    print(f"✅ Session counted once: {session_factors[0]}")


def test_cvd_wrong_direction_no_bonus():
    """CVD bearish on LONG signal → no bonus."""
    r = compute_confidence(**_base(cvd_divergence="bearish", direction="LONG"))
    cvd_factors = [f for f in r.factors if "CVD" in f.label]
    assert len(cvd_factors) == 0, f"CVD should not add bonus on mismatch: {cvd_factors}"
    print(f"✅ CVD mismatch: no bonus applied")


if __name__ == "__main__":
    print("Running confidence score tests...\n")
    test_minimum_sweep_score()
    test_all_bonuses()
    test_funding_block_long()
    test_funding_block_short()
    test_no_session_penalty()
    test_adx_counter_trend_penalty()
    test_session_no_double_count()
    test_cvd_wrong_direction_no_bonus()
    print("\n✅ All confidence tests passed")
