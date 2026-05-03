import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategies.breakout as breakout


def _df(close=100.0, volume=200.0):
    rows = 30
    return pd.DataFrame({
        "open": [99.5] * rows,
        "high": [100.5] * rows,
        "low": [99.0] * rows,
        "close": [close] * rows,
        "volume": [volume] * rows,
    })


def test_resolve_breakout_sl_pct_min_clamp():
    sl_pct, raw_sl_pct, sl_mode = breakout.resolve_breakout_sl_pct(
        atr_pct=0.0020,
        operating_mode="normal",
    )
    assert round(sl_pct, 6) == 0.005
    assert round(raw_sl_pct, 6) == 0.003
    assert sl_mode == "adaptive_min_clamp"


def test_resolve_breakout_sl_pct_raw_mode():
    sl_pct, raw_sl_pct, sl_mode = breakout.resolve_breakout_sl_pct(
        atr_pct=0.0060,
        operating_mode="normal",
    )
    assert round(sl_pct, 6) == 0.009
    assert round(raw_sl_pct, 6) == 0.009
    assert sl_mode == "adaptive_raw"


def test_resolve_breakout_sl_pct_max_clamp():
    sl_pct, raw_sl_pct, sl_mode = breakout.resolve_breakout_sl_pct(
        atr_pct=0.0100,
        operating_mode="normal",
    )
    assert round(sl_pct, 6) == 0.012
    assert round(raw_sl_pct, 6) == 0.015
    assert sl_mode == "adaptive_max_clamp"


def test_check_breakout_long_uses_adaptive_sl(monkeypatch):
    df = _df(close=102.0, volume=500.0)

    monkeypatch.setattr(
        breakout,
        "bollinger",
        lambda _df: pd.DataFrame({
            "upper": [101.0] * len(_df),
            "lower": [99.0] * len(_df),
        }),
    )
    monkeypatch.setattr(
        breakout,
        "volume_ma",
        lambda _df, period=20: pd.Series([100.0] * len(_df)),
    )

    sig = breakout.check_breakout(
        df_15m=df,
        squeeze_active=True,
        session="london",
        cvd_divergence=None,
        funding_rate=0.0,
        liquidation_cascade=False,
        adx_value=30.0,
        atr_pct=0.0060,
        operating_mode="normal",
        min_rr=2.0,
        volume_spike_multiplier=1.2,
    )

    assert sig is not None
    assert sig.direction == "LONG"
    assert sig.stop_loss == 101.08
    assert round(sig.sl_pct_used, 6) == 0.009
    assert sig.sl_mode == "adaptive_raw"
    assert sig.rr_ratio == round((102.0 * 0.03) / (102.0 * 0.009), 2)


def test_check_breakout_short_uses_max_clamp(monkeypatch):
    df = _df(close=98.0, volume=500.0)

    monkeypatch.setattr(
        breakout,
        "bollinger",
        lambda _df: pd.DataFrame({
            "upper": [101.0] * len(_df),
            "lower": [99.0] * len(_df),
        }),
    )
    monkeypatch.setattr(
        breakout,
        "volume_ma",
        lambda _df, period=20: pd.Series([100.0] * len(_df)),
    )

    sig = breakout.check_breakout(
        df_15m=df,
        squeeze_active=True,
        session="ny",
        cvd_divergence=None,
        funding_rate=0.0,
        liquidation_cascade=False,
        adx_value=30.0,
        atr_pct=0.0100,
        operating_mode="normal",
        min_rr=2.0,
        volume_spike_multiplier=1.2,
    )

    assert sig is not None
    assert sig.direction == "SHORT"
    assert sig.stop_loss == 99.18
    assert round(sig.sl_pct_used, 6) == 0.012
    assert sig.sl_mode == "adaptive_max_clamp"


def test_check_breakout_falls_back_to_fixed_sl(monkeypatch):
    df = _df(close=102.0, volume=500.0)

    monkeypatch.setattr(
        breakout,
        "bollinger",
        lambda _df: pd.DataFrame({
            "upper": [101.0] * len(_df),
            "lower": [99.0] * len(_df),
        }),
    )
    monkeypatch.setattr(
        breakout,
        "volume_ma",
        lambda _df, period=20: pd.Series([100.0] * len(_df)),
    )

    sig = breakout.check_breakout(
        df_15m=df,
        squeeze_active=True,
        session="london",
        cvd_divergence=None,
        funding_rate=0.0,
        liquidation_cascade=False,
        adx_value=30.0,
        atr_pct=None,
        operating_mode="normal",
        min_rr=2.0,
        volume_spike_multiplier=1.2,
    )

    assert sig is not None
    assert sig.sl_pct_used == breakout.settings.breakout_sl_pct
    assert sig.sl_mode == "fixed_fallback"


def test_check_breakout_quiet_tp_is_capped_by_common_resolver(monkeypatch):
    df = _df(close=102.0, volume=500.0)

    monkeypatch.setattr(
        breakout,
        "bollinger",
        lambda _df: pd.DataFrame({
            "upper": [101.0] * len(_df),
            "lower": [99.0] * len(_df),
        }),
    )
    monkeypatch.setattr(
        breakout,
        "volume_ma",
        lambda _df, period=20: pd.Series([100.0] * len(_df)),
    )

    sig = breakout.check_breakout(
        df_15m=df,
        squeeze_active=True,
        session="london",
        cvd_divergence=None,
        funding_rate=0.0,
        liquidation_cascade=False,
        adx_value=35.0,
        atr_pct=0.0060,
        operating_mode="quiet",
        min_rr=1.0,
        volume_spike_multiplier=1.03,
    )

    assert sig is not None
    assert sig.direction == "LONG"
    assert sig.take_profit == round(sig.entry_market * (1 + breakout.settings.quiet_tp_max_pct), 2)
    assert sig.rr_ratio < round((102.0 * 0.03) / (102.0 * 0.009), 2)


if __name__ == "__main__":
    test_resolve_breakout_sl_pct_min_clamp()
    test_resolve_breakout_sl_pct_raw_mode()
    test_resolve_breakout_sl_pct_max_clamp()
    print("[OK] Breakout adaptive SL tests passed")
