import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine.market_state as market_state
from config.settings import settings


def _df():
    return pd.DataFrame({
        "open": [100.0] * 60,
        "high": [101.0] * 60,
        "low": [99.0] * 60,
        "close": [100.0] * 60,
        "volume": [1000.0] * 60,
    })


def _freeze_utc_hour(monkeypatch, hour: int):
    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2024, 1, 1, hour, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(market_state, "datetime", FakeDatetime)


def _mock_context_inputs(monkeypatch, *, adx_value: float, atr_pct: float, trend: str | None = None):
    monkeypatch.setattr(market_state, "calc_adx", lambda df: pd.Series([adx_value] * len(df)))
    monkeypatch.setattr(market_state, "calc_atr_pct", lambda df, period=14, lookback=20: atr_pct)
    monkeypatch.setattr(market_state, "calc_trend_direction", lambda df, period=14: trend)


def test_operating_mode_selection():
    assert market_state.get_operating_mode(0.0010) == "blocked"
    assert market_state.get_operating_mode(0.0020) == "quiet"
    assert market_state.get_operating_mode(0.0059) == "quiet"
    assert market_state.get_operating_mode(0.0060) == "normal"


def test_blocked_mode_not_tradeable(monkeypatch):
    _mock_context_inputs(monkeypatch, adx_value=18.0, atr_pct=0.0015)
    _freeze_utc_hour(monkeypatch, 9)

    ctx = market_state.get_market_context(_df())

    assert ctx.operating_mode == "blocked"
    assert ctx.volatility_regime == "blocked"
    assert ctx.session == "london"
    assert ctx.tradeable is False


def test_quiet_mode_blocks_disallowed_session(monkeypatch):
    """Asian session is now ALLOWED in QUIET mode (updated config)."""
    _mock_context_inputs(monkeypatch, adx_value=18.0, atr_pct=0.0030)
    _freeze_utc_hour(monkeypatch, 3)

    ctx = market_state.get_market_context(_df())

    assert ctx.operating_mode == "quiet"
    assert ctx.session == "asian"
    # Asian is now in quiet_allowed_sessions, so tradeable=True
    assert ctx.tradeable is True


def test_quiet_mode_allows_configured_session(monkeypatch):
    _mock_context_inputs(monkeypatch, adx_value=18.0, atr_pct=0.0030)
    _freeze_utc_hour(monkeypatch, 9)

    ctx = market_state.get_market_context(_df())

    assert ctx.operating_mode == "quiet"
    assert ctx.session == "london"
    assert ctx.tradeable is True


def test_quiet_mode_uses_configured_allowlist(monkeypatch):
    _mock_context_inputs(monkeypatch, adx_value=18.0, atr_pct=0.0030)
    _freeze_utc_hour(monkeypatch, 3)
    original = settings.quiet_allowed_sessions
    settings.quiet_allowed_sessions = ["asian"]
    try:
        ctx = market_state.get_market_context(_df())
    finally:
        settings.quiet_allowed_sessions = original

    assert ctx.operating_mode == "quiet"
    assert ctx.session == "asian"
    assert ctx.tradeable is True


def test_normal_mode_tradeable(monkeypatch):
    _mock_context_inputs(monkeypatch, adx_value=18.0, atr_pct=0.0080)
    _freeze_utc_hour(monkeypatch, 9)

    ctx = market_state.get_market_context(_df())

    assert ctx.operating_mode == "normal"
    assert ctx.volatility_regime == "normal"
    assert ctx.tradeable is True


def test_dead_zone_remains_not_tradeable(monkeypatch):
    _mock_context_inputs(monkeypatch, adx_value=22.5, atr_pct=0.0080)
    _freeze_utc_hour(monkeypatch, 9)

    ctx = market_state.get_market_context(_df())

    assert ctx.operating_mode == "normal"
    assert ctx.market_state == "dead_zone"
    assert ctx.tradeable is False
