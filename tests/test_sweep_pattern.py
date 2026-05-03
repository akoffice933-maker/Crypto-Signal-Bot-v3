import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from engine.indicators import candle_parts
from engine.liquidity_map import LiquidityLevel
import strategies.sweep_reversal as sweep_mod
from strategies.sweep_reversal import (
    _calculate_rr,
    _check_one_level,
    _filter_candidate_levels,
    _is_counter_trend,
    _is_rejection,
)
from config.settings import settings


def _candle(open_, high, low, close):
    return pd.Series({"open": open_, "high": high, "low": low, "close": close})


# ── Pin-bar / rejection candle tests ─────────────────────────

def test_long_rejection_valid():
    """Lower wick ≥ 2.5× body AND body ≤ 1/3 range → valid LONG rejection."""
    # body = 100, lower wick = 300 (3× body), upper wick = 50
    # range = 450, body/range = 0.22 < 1/3 ✓
    c = _candle(open_=60200, high=60250, low=59900, close=60300)
    parts = candle_parts(c)
    assert _is_rejection(parts, "LONG"), f"Should be valid LONG rejection: {parts}"
    print(f"✅ Valid LONG rejection: wick={parts['lower_wick']:.0f} body={parts['body']:.0f}")


def test_short_rejection_valid():
    """Upper wick ≥ 2.5× body AND body ≤ 1/3 range → valid SHORT rejection."""
    c = _candle(open_=60300, high=60700, low=60250, close=60200)
    parts = candle_parts(c)
    assert _is_rejection(parts, "SHORT"), f"Should be valid SHORT rejection: {parts}"
    print(f"✅ Valid SHORT rejection: wick={parts['upper_wick']:.0f} body={parts['body']:.0f}")


def test_rejection_fails_large_body():
    """Body > 1/3 of range → not a rejection candle."""
    # body=300, range=400, body/range=0.75 > 1/3
    c = _candle(open_=60000, high=60350, low=59950, close=60300)
    parts = candle_parts(c)
    assert not _is_rejection(parts, "LONG"), \
        f"Should NOT be rejection (body too large): {parts}"
    print(f"✅ Large body rejected: body/range={parts['body']/parts['range']:.2f}")


def test_rejection_fails_small_wick():
    """Wick < 2.5× body → not a rejection candle."""
    # body=200, lower_wick=100 (0.5× body) → fail
    c = _candle(open_=60000, high=60050, low=59900, close=60200)
    parts = candle_parts(c)
    assert not _is_rejection(parts, "LONG"), \
        f"Should NOT be rejection (wick too small): {parts}"
    print(f"✅ Small wick rejected: wick/body={parts['lower_wick']/max(parts['body'],1):.2f}")


def test_doji_is_rejection():
    """Doji (body=0) with any wick is valid rejection."""
    c = _candle(open_=60000, high=60100, low=59850, close=60000)
    parts = candle_parts(c)
    assert _is_rejection(parts, "LONG"), f"Doji should be valid rejection: {parts}"
    print(f"✅ Doji is valid rejection")


def test_wrong_wick_direction():
    """LONG signal but only upper wick present → not valid."""
    # upper_wick=400, lower_wick=10
    c = _candle(open_=60000, high=60400, low=59990, close=60010)
    parts = candle_parts(c)
    result = _is_rejection(parts, "LONG")
    # lower_wick = min(open,close) - low = 59990 - 59990 = 0 → no lower wick
    assert not result, f"Upper-wick candle should not be LONG rejection: {parts}"
    print(f"✅ Wrong wick direction rejected for LONG")


def test_counter_trend_requires_opposite_bias():
    """Counter-trend penalty should only apply when trend direction is known and opposite."""
    assert not _is_counter_trend("LONG", None)
    assert not _is_counter_trend("LONG", "LONG")
    assert _is_counter_trend("LONG", "SHORT")
    print("✅ Counter-trend logic only triggers on opposite directional bias")


def test_calculate_rr_for_long_and_short():
    long_rr = _calculate_rr("LONG", entry=100.0, stop_loss=95.0, take_profit=110.0)
    short_rr = _calculate_rr("SHORT", entry=100.0, stop_loss=105.0, take_profit=90.0)
    assert round(long_rr, 2) == 2.0
    assert round(short_rr, 2) == 2.0
    print("✅ RR helper calculates LONG/SHORT symmetrically")


def test_filter_candidate_levels_excludes_overused_levels():
    original_max_touches = settings.max_level_touches
    settings.max_level_touches = 15
    try:
        fresh = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_highs",
            price=61000.0,
            touch_count=5,
            strength=15.0,
            mitigated=False,
            distance_pct=0.02,
        )
        stale = LiquidityLevel(
            timeframe="4h",
            pool_type="equal_lows",
            price=59000.0,
            touch_count=22,
            strength=22.0,
            mitigated=False,
            distance_pct=0.02,
        )

        filtered, min_score = _filter_candidate_levels([fresh, stale], "quiet")

        assert min_score == settings.quiet_level_score_min
        assert fresh in filtered
        assert stale not in filtered
    finally:
        settings.max_level_touches = original_max_touches


# ── Mode-specific wick ratio tests ────────────────────────────

def test_quiet_mode_wick_ratio_2_0():
    """QUIET mode uses wick_ratio=2.0 (more lenient)."""
    # body=100, lower_wick=200 (2.0× body) → should pass in QUIET (2.0) but fail in NORMAL (2.5)
    # open=60000, close=60100 (bull), low=59800, high=60150
    # lower_wick = open - low = 60000 - 59800 = 200
    # upper_wick = high - close = 60150 - 60100 = 50
    # body = close - open = 100
    # range = high - low = 350
    # body/range = 100/350 = 0.286 < 0.333 ✓
    c = _candle(open_=60000, high=60150, low=59800, close=60100)
    parts = candle_parts(c)
    # wick/body = 200/100 = 2.0
    # QUIET: 2.0 >= 2.0 ✓, NORMAL: 2.0 >= 2.5 ✗
    assert _is_rejection(parts, "LONG", wick_ratio=2.0), f"Should pass QUIET (2.0): {parts}"
    assert not _is_rejection(parts, "LONG", wick_ratio=2.5), f"Should fail NORMAL (2.5): {parts}"
    print(f"✅ QUIET wick_ratio=2.0 passes where NORMAL=2.5 fails: wick/body={parts['lower_wick']/parts['body']:.2f}")


def test_normal_mode_wick_ratio_2_5():
    """NORMAL mode requires wick_ratio=2.5 (stricter)."""
    # body=100, lower_wick=250 (2.5× body) → should pass both
    c = _candle(open_=60100, high=60150, low=59850, close=60200)
    parts = candle_parts(c)
    # wick/body = 250/100 = 2.5
    assert _is_rejection(parts, "LONG", wick_ratio=2.0), f"Should pass QUIET (2.0): {parts}"
    assert _is_rejection(parts, "LONG", wick_ratio=2.5), f"Should pass NORMAL (2.5): {parts}"
    print(f"✅ Strong rejection (2.5×) passes both modes: wick/body={parts['lower_wick']/parts['body']:.2f}")


def test_quiet_mode_tp_cap_does_not_raise_name_error(monkeypatch=None):
    """Quiet-mode TP cap should use operating_mode and not reference undefined volatility_regime."""
    original_tp_cap = settings.quiet_tp_max_pct
    original_min_distance = settings.liquidity_min_distance_pct
    settings.quiet_tp_max_pct = 0.011
    settings.liquidity_min_distance_pct = 0.005
    try:
        level = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_lows",
            price=100.0,
            touch_count=3,
            strength=9.0,
            mitigated=False,
            distance_pct=0.01,
        )
        target = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_highs",
            price=105.0,
            touch_count=3,
            strength=9.0,
            mitigated=False,
            distance_pct=0.05,
        )

        original_compute_confidence = sweep_mod.compute_confidence
        original_apply_penalty = sweep_mod.apply_adx_counter_trend_penalty
        try:
            sweep_mod.compute_confidence = lambda **_kwargs: type(
                "Conf", (),
                {"score": 80, "breakdown_json": [], "factors": []}
            )()
            sweep_mod.apply_adx_counter_trend_penalty = lambda *_args, **_kwargs: None

            sweep_c = pd.Series({
                "open": 100.6, "high": 100.8, "low": 99.4, "close": 100.5, "volume": 150.0
            })
            rej_c = pd.Series({
                "open": 100.0, "high": 100.25, "low": 99.4, "close": 100.2, "volume": 160.0
            })

            signal = _check_one_level(
                level=level,
                sweep_c=sweep_c,
                rej_c=rej_c,
                vol_ma20=100.0,
                current_price=100.2,
                all_levels=[level, target],
                operating_mode="quiet",
                squeeze_active=False,
                cvd_divergence=None,
                funding_rate=0.0,
                liquidation_cascade=False,
                market_state="ranging",
                adx_value=18.0,
                trend_direction=None,
                session="london",
                atr_pct=0.003,
                min_rr=0.8,
                volume_spike_multiplier=1.05,
            )
        finally:
            sweep_mod.compute_confidence = original_compute_confidence
            sweep_mod.apply_adx_counter_trend_penalty = original_apply_penalty

        assert signal is not None
        assert signal.take_profit <= round(signal.entry_limit * (1 + settings.quiet_tp_max_pct), 2)
        print("✅ QUIET TP cap uses operating_mode without NameError")
    finally:
        settings.quiet_tp_max_pct = original_tp_cap
        settings.liquidity_min_distance_pct = original_min_distance


def test_quiet_long_sweep_stop_uses_atr_distance():
    original_quiet_sl = settings.quiet_sl_atr_mult
    original_min_stop = settings.min_stop_loss_pct
    original_min_distance = settings.liquidity_min_distance_pct
    try:
        settings.quiet_sl_atr_mult = 1.0
        settings.min_stop_loss_pct = 0.0045
        settings.liquidity_min_distance_pct = 0.005
        level = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_lows",
            price=100.0,
            touch_count=3,
            strength=9.0,
            mitigated=False,
            distance_pct=0.01,
        )
        target = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_highs",
            price=103.0,
            touch_count=3,
            strength=9.0,
            mitigated=False,
            distance_pct=0.03,
        )

        original_compute_confidence = sweep_mod.compute_confidence
        original_apply_penalty = sweep_mod.apply_adx_counter_trend_penalty
        try:
            sweep_mod.compute_confidence = lambda **_kwargs: type(
                "Conf", (),
                {"score": 80, "breakdown_json": [], "factors": []}
            )()
            sweep_mod.apply_adx_counter_trend_penalty = lambda *_args, **_kwargs: None

            sweep_c = pd.Series({
                "open": 100.6, "high": 100.8, "low": 99.7, "close": 100.4, "volume": 150.0
            })
            rej_c = pd.Series({
                "open": 100.0, "high": 100.3, "low": 99.6, "close": 100.2, "volume": 160.0
            })

            signal = _check_one_level(
                level=level,
                sweep_c=sweep_c,
                rej_c=rej_c,
                vol_ma20=100.0,
                current_price=100.2,
                all_levels=[level, target],
                operating_mode="quiet",
                squeeze_active=False,
                cvd_divergence=None,
                funding_rate=0.0,
                liquidation_cascade=False,
                market_state="ranging",
                adx_value=18.0,
                trend_direction=None,
                session="london",
                atr_pct=0.01,
                min_rr=0.5,
                volume_spike_multiplier=1.03,
            )
        finally:
            sweep_mod.compute_confidence = original_compute_confidence
            sweep_mod.apply_adx_counter_trend_penalty = original_apply_penalty

        assert signal is not None
        assert signal.entry_limit is not None
        expected_stop = round(signal.entry_limit * (1 - 0.01), 2)
        assert signal.stop_loss == expected_stop
        print("✅ QUIET LONG sweep SL uses ATR-based distance from entry")
    finally:
        settings.quiet_sl_atr_mult = original_quiet_sl
        settings.min_stop_loss_pct = original_min_stop
        settings.liquidity_min_distance_pct = original_min_distance


def test_normal_short_sweep_stop_uses_atr_distance():
    original_normal_sl = settings.normal_sl_atr_mult
    original_min_stop = settings.min_stop_loss_pct
    original_min_distance = settings.liquidity_min_distance_pct
    try:
        settings.normal_sl_atr_mult = 0.8
        settings.min_stop_loss_pct = 0.0045
        settings.liquidity_min_distance_pct = 0.005
        level = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_highs",
            price=100.0,
            touch_count=3,
            strength=9.0,
            mitigated=False,
            distance_pct=0.01,
        )
        target = LiquidityLevel(
            timeframe="1d",
            pool_type="equal_lows",
            price=96.0,
            touch_count=3,
            strength=9.0,
            mitigated=False,
            distance_pct=0.04,
        )

        original_compute_confidence = sweep_mod.compute_confidence
        original_apply_penalty = sweep_mod.apply_adx_counter_trend_penalty
        try:
            sweep_mod.compute_confidence = lambda **_kwargs: type(
                "Conf", (),
                {"score": 80, "breakdown_json": [], "factors": []}
            )()
            sweep_mod.apply_adx_counter_trend_penalty = lambda *_args, **_kwargs: None

            sweep_c = pd.Series({
                "open": 99.6, "high": 100.3, "low": 99.3, "close": 99.5, "volume": 150.0
            })
            rej_c = pd.Series({
                "open": 100.0, "high": 100.4, "low": 99.85, "close": 99.9, "volume": 160.0
            })

            signal = _check_one_level(
                level=level,
                sweep_c=sweep_c,
                rej_c=rej_c,
                vol_ma20=100.0,
                current_price=99.9,
                all_levels=[level, target],
                operating_mode="normal",
                squeeze_active=False,
                cvd_divergence=None,
                funding_rate=0.0,
                liquidation_cascade=False,
                market_state="trending",
                adx_value=30.0,
                trend_direction="SHORT",
                session="london",
                atr_pct=0.01,
                min_rr=0.5,
                volume_spike_multiplier=1.2,
            )
        finally:
            sweep_mod.compute_confidence = original_compute_confidence
            sweep_mod.apply_adx_counter_trend_penalty = original_apply_penalty

        assert signal is not None
        assert signal.entry_limit is not None
        expected_stop = round(max(100.3 * 1.001, signal.entry_limit * (1 + 0.008)), 2)
        assert signal.stop_loss == expected_stop
        print("✅ NORMAL SHORT sweep SL uses the wider of ATR distance and sweep extreme")
    finally:
        settings.normal_sl_atr_mult = original_normal_sl
        settings.min_stop_loss_pct = original_min_stop
        settings.liquidity_min_distance_pct = original_min_distance


# ── candle_parts correctness ──────────────────────────────────

def test_candle_parts_bull():
    """Bullish candle: open<close → lower_wick = open-low, upper_wick = high-close."""
    c = _candle(open_=100, high=120, low=80, close=110)
    p = candle_parts(c)
    assert p["is_bull"]        == True
    assert p["body"]           == 10     # close - open
    assert p["upper_wick"]     == 10     # high - close
    assert p["lower_wick"]     == 20     # open - low
    assert p["range"]          == 40
    print(f"✅ Bull candle parts: {p}")


def test_candle_parts_bear():
    """Bearish candle: open>close → lower_wick = close-low, upper_wick = high-open."""
    c = _candle(open_=110, high=120, low=80, close=100)
    p = candle_parts(c)
    assert p["is_bull"]        == False
    assert p["body"]           == 10
    assert p["upper_wick"]     == 10     # high - open
    assert p["lower_wick"]     == 20     # close - low
    print(f"✅ Bear candle parts: {p}")


if __name__ == "__main__":
    print("Running sweep pattern tests...\n")
    test_long_rejection_valid()
    test_short_rejection_valid()
    test_rejection_fails_large_body()
    test_rejection_fails_small_wick()
    test_doji_is_rejection()
    test_wrong_wick_direction()
    test_counter_trend_requires_opposite_bias()
    test_calculate_rr_for_long_and_short()
    test_quiet_mode_wick_ratio_2_0()
    test_normal_mode_wick_ratio_2_5()
    test_quiet_mode_tp_cap_does_not_raise_name_error()
    test_quiet_long_sweep_stop_uses_atr_distance()
    test_normal_short_sweep_stop_uses_atr_distance()
    test_candle_parts_bull()
    test_candle_parts_bear()
    print("\n✅ All sweep pattern tests passed")
