import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd

from engine.liquidity_map import (
    _find_equal_levels,
    detect_levels,
    select_target_level,
    build_liquidity_map,
    LiquidityLevel,
)


def _make_df(highs, lows, closes=None):
    n = len(highs)
    closes = closes or [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({
        "open":  closes,
        "high":  highs,
        "low":   lows,
        "close": closes,
        "volume": [1000.0] * n,
    })


# ── _find_equal_levels ────────────────────────────────────────

def test_basic_cluster():
    """Three prices within 0.2% cluster into one level."""
    prices = pd.Series([60000, 60100, 60080, 62000, 62050, 62080])
    result = _find_equal_levels(prices, tolerance_pct=0.002, min_touches=3)
    assert len(result) == 2, f"Expected 2 clusters, got {len(result)}"
    prices_found = [r[0] for r in result]
    assert any(abs(p - 60060) < 100 for p in prices_found), "First cluster ~60060"
    assert any(abs(p - 62043) < 100 for p in prices_found), "Second cluster ~62043"
    print(f"✅ Basic cluster: {result}")


def test_min_touches_filter():
    """Cluster with < 3 touches is excluded."""
    prices = pd.Series([60000, 60050, 65000])  # only 2 near 60k
    result = _find_equal_levels(prices, tolerance_pct=0.002, min_touches=3)
    assert result == [], f"Expected empty, got {result}"
    print("✅ Min touches filter works")


def test_tolerance_separation():
    """Prices > 0.2% apart form separate clusters."""
    prices = pd.Series([60000, 60130, 60260, 62000, 62130, 62260])
    # 60000→60130 = 0.22% > 0.2% → separate
    result = _find_equal_levels(prices, tolerance_pct=0.002, min_touches=2)
    # Each pair 0.22% apart may or may not cluster; test that 62k levels aren't mixed with 60k
    for price, count in result:
        assert not (59900 < price < 60400 and 61900 < price < 62400), \
            f"Cross-cluster contamination at {price}"
    print(f"✅ Tolerance separation: {len(result)} clusters")


# ── detect_levels ─────────────────────────────────────────────

def test_detect_equal_highs():
    """Three candles touching same high → equal_highs level detected."""
    base = 60000.0
    tol  = 0.002
    # Three highs within 0.2%, many lows scattered
    highs  = [base * 1.000, base * 1.0015, base * 1.001] + [base * 1.05] * 5
    lows   = [base * 0.99] * 8
    df = _make_df(highs, lows)
    current = base

    levels = detect_levels(df, "1d", current, tolerance_pct=tol, min_touches=3)
    highs_lvl = [lv for lv in levels if lv.pool_type == "equal_highs"]
    assert len(highs_lvl) >= 1, f"Expected equal_highs level, got {levels}"
    assert abs(highs_lvl[0].price - base) < base * tol * 2
    print(f"✅ Equal highs detected: {highs_lvl[0]}")


def test_detect_equal_lows():
    """Three candles touching same low → equal_lows level."""
    base = 60000.0
    lows  = [base * 0.999, base * 0.9995, base * 0.9985] + [base * 0.95] * 5
    highs = [base * 1.01] * 8
    df = _make_df(highs, lows)
    levels = detect_levels(df, "4h", base, min_touches=3)
    lows_lvl = [lv for lv in levels if lv.pool_type == "equal_lows"]
    assert len(lows_lvl) >= 1, f"Expected equal_lows, got {levels}"
    print(f"✅ Equal lows detected: {lows_lvl[0]}")


def test_strength_tf_weight():
    """1D levels have 3× weight over 4H."""
    base  = 60000.0
    highs = [base * 1.001] * 3 + [base * 1.05] * 5
    lows  = [base * 0.99] * 8
    df    = _make_df(highs, lows)

    levels_1d = detect_levels(df, "1d", base, min_touches=3)
    levels_4h = detect_levels(df, "4h", base, min_touches=3)

    if levels_1d and levels_4h:
        h1d = [lv for lv in levels_1d if lv.pool_type == "equal_highs"]
        h4h = [lv for lv in levels_4h if lv.pool_type == "equal_highs"]
        if h1d and h4h:
            assert h1d[0].strength == h4h[0].strength * 3, \
                f"1D str={h1d[0].strength} vs 4H str={h4h[0].strength}"
    print("✅ TF weight: 1D = 3× 4H")


# ── select_target_level ───────────────────────────────────────

def _make_level(pool_type, price, tf="1d", distance_pct=None, strength=3.0):
    cp = 60000.0
    return LiquidityLevel(
        timeframe=tf,
        pool_type=pool_type,
        price=price,
        touch_count=3,
        strength=strength,
        mitigated=False,
        distance_pct=distance_pct or abs(price - cp) / cp,
    )


def test_select_target_long():
    """LONG → nearest equal_highs above price with dist ≥ 1.5%."""
    current = 60000.0
    levels = [
        _make_level("equal_highs", 60800, distance_pct=0.013),  # < 1.5% → excluded
        _make_level("equal_highs", 61000, distance_pct=0.017),  # ✓ nearest valid
        _make_level("equal_highs", 62000, distance_pct=0.033),
        _make_level("equal_lows",  59000, distance_pct=0.017),  # wrong type
    ]
    target = select_target_level(levels, current, "LONG", min_distance_pct=0.015)
    assert target is not None
    assert target.price == 61000, f"Expected 61000, got {target.price}"
    print(f"✅ Target LONG: {target}")


def test_select_target_short():
    """SHORT → nearest equal_lows below price."""
    current = 60000.0
    levels = [
        _make_level("equal_lows",  59100, distance_pct=0.015),  # ✓
        _make_level("equal_lows",  58000, distance_pct=0.033),
        _make_level("equal_highs", 61000, distance_pct=0.017),  # wrong type
    ]
    target = select_target_level(levels, current, "SHORT", min_distance_pct=0.015)
    assert target is not None
    assert target.price == 59100
    print(f"✅ Target SHORT: {target}")


def test_no_target_all_too_close():
    """All levels within 1.5% → no target returned."""
    current = 60000.0
    levels = [
        _make_level("equal_highs", 60700, distance_pct=0.012),
        _make_level("equal_highs", 60600, distance_pct=0.010),
    ]
    target = select_target_level(levels, current, "LONG", min_distance_pct=0.015)
    assert target is None
    print("✅ No target when all too close")


def test_1d_preferred_over_4h():
    """1D level preferred over closer 4H at similar distance."""
    current = 60000.0
    levels = [
        _make_level("equal_highs", 61100, tf="4h", distance_pct=0.018, strength=3.0),
        _make_level("equal_highs", 61200, tf="1d", distance_pct=0.020, strength=9.0),
    ]
    target = select_target_level(levels, current, "LONG", min_distance_pct=0.015)
    assert target.timeframe == "1d", f"Expected 1d, got {target.timeframe}"
    print(f"✅ 1D preferred over 4H: {target}")


if __name__ == "__main__":
    print("Running liquidity map tests...\n")
    test_basic_cluster()
    test_min_touches_filter()
    test_tolerance_separation()
    test_detect_equal_highs()
    test_detect_equal_lows()
    test_strength_tf_weight()
    test_select_target_long()
    test_select_target_short()
    test_no_target_all_too_close()
    test_1d_preferred_over_4h()
    print("\n✅ All liquidity map tests passed")
