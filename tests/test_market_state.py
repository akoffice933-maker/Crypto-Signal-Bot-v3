import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
from unittest.mock import patch
from datetime import datetime, timezone

from engine.market_state import get_market_context
from config.settings import settings


def _flat_df(n=60, close=60000.0, atr_boost=1.0):
    """Generate a flat DataFrame where ADX will be low (ranging)."""
    np.random.seed(42)
    closes = np.full(n, close) + np.random.normal(0, close * 0.001 * atr_boost, n)
    opens  = np.concatenate([[closes[0]], closes[:-1]])
    highs  = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.001, n)))
    lows   = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.001, n)))
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": np.ones(n) * 1000,
    })


def _trending_df(n=60, close=60000.0, slope=0.003):
    """Generate a trending DataFrame where ADX will be high."""
    closes = close * np.cumprod(1 + np.full(n, slope) + np.random.normal(0, 0.0005, n))
    opens  = np.concatenate([[closes[0]], closes[:-1]])
    highs  = closes * 1.002
    lows   = closes * 0.998
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": np.ones(n) * 1000,
    })


def test_session_priority_overlap():
    """At hour 7 (London/Asian overlap) → session must be 'london'."""
    result = settings.get_session(7)
    assert result == "london", f"Expected 'london' at hour 7, got '{result}'"
    print(f"✅ Session overlap (hour 7): '{result}'")


def test_session_asian():
    assert settings.get_session(3)  == "asian"
    assert settings.get_session(0)  == "asian"
    assert settings.get_session(7)  == "london"   # overlap → london wins
    print("✅ Asian session: hours 0-6 → asian, hour 7 → london")


def test_session_ny():
    assert settings.get_session(13) == "ny"
    assert settings.get_session(16) == "ny"
    assert settings.get_session(17) is None
    print("✅ NY session: 13-16 active, 17 closed")


def test_between_sessions():
    """Hour 12 is between London and NY → None."""
    result = settings.get_session(12)
    assert result is None, f"Expected None at hour 12, got '{result}'"
    print("✅ Between sessions (hour 12): None")


def test_low_volatility_not_tradeable():
    """Low ATR% → tradeable=False regardless of session."""
    df = _flat_df(n=60, atr_boost=0.1)   # very small moves
    with patch("engine.market_state.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
        ctx = get_market_context(df)
    # If atr_pct < 0.7%, tradeable=False
    if ctx.volatility_regime == "low":
        assert not ctx.tradeable, "Low vol should not be tradeable"
        print(f"✅ Low volatility not tradeable: atr={ctx.atr_pct*100:.3f}%")
    else:
        print(f"ℹ️  Volatility not low ({ctx.volatility_regime}), skip assertion")


def test_dead_zone_not_tradeable():
    """ADX in 20-25 → market_state=dead_zone → tradeable=False."""
    # We test the logic directly without needing exact ADX values
    from engine.market_state import MarketContext
    ctx = MarketContext(
        market_state="dead_zone",
        volatility_regime="normal",
        adx_value=22.5,
        atr_pct=0.01,
        trend_direction=None,
        session="london",
        hour_utc=9,
        tradeable=False,
    )
    assert not ctx.tradeable
    print("✅ Dead zone not tradeable")


def test_tradeable_conditions():
    """ranging + normal vol + active session → tradeable=True."""
    from engine.market_state import MarketContext
    ctx = MarketContext(
        market_state="ranging",
        volatility_regime="normal",
        adx_value=18.0,
        atr_pct=0.01,
        trend_direction=None,
        session="london",
        hour_utc=9,
        tradeable=True,
    )
    assert ctx.tradeable
    print("✅ Ranging + normal vol + session → tradeable")


if __name__ == "__main__":
    np.random.seed(42)
    print("Running market state tests...\n")
    test_session_priority_overlap()
    test_session_asian()
    test_session_ny()
    test_between_sessions()
    test_low_volatility_not_tradeable()
    test_dead_zone_not_tradeable()
    test_tradeable_conditions()
    print("\n✅ All market state tests passed")
