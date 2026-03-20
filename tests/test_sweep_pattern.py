import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from engine.indicators import candle_parts
from strategies.sweep_reversal import _is_counter_trend, _is_rejection


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
    test_candle_parts_bull()
    test_candle_parts_bear()
    print("\n✅ All sweep pattern tests passed")
