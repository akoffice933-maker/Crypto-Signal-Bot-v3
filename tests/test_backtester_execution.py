import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from backtesting.backtester import BTConfig, BTTrade, Backtester


def test_limit_entry_and_tp1_then_final_tp():
    bt = Backtester(BTConfig(initial_balance=10_000, max_position_pct=0.10))

    signal = {
        "direction": "LONG",
        "entry_market": 100.0,
        "entry_limit": 99.0,
        "stop_loss": 98.0,
        "take_profit": 103.0,
        "tp1_price": 101.0,
        "tp1_size_pct": 0.5,
        "final_tp_size_pct": 0.5,
        "execution_basis": "limit",
        "rr": 4.0,
        "confidence": 80,
        "confidence_threshold": 60,
        "confirmation_delay": 0,
    }

    placed_row = pd.Series({"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2})
    trade = bt._maybe_enter_or_queue(signal, placed_row, equity=10_000, idx=100)
    assert trade is None
    assert len(bt._pending_entries) == 1

    fill_row = pd.Series({"open": 100.2, "high": 100.5, "low": 98.9, "close": 99.6})
    trade = bt._fill_pending_entry(fill_row, equity=10_000, idx=101)
    assert trade is not None
    assert trade["entry_price"] == 99.0
    assert trade["tp1_price"] == 101.0

    tp1_row = pd.Series({"open": 99.6, "high": 101.2, "low": 99.4, "close": 100.9})
    result = bt._manage(trade, pd.DataFrame(), 102, tp1_row)
    assert result is None
    assert trade["tp1_hit"] is True
    assert trade["realized_pnl_net"] > 0

    final_tp_row = pd.Series({"open": 101.0, "high": 103.2, "low": 100.8, "close": 102.9})
    result = bt._manage(trade, pd.DataFrame(), 103, final_tp_row)
    assert result is not None
    assert result["reason"] == "tp1_tp"
    assert abs(result["rr"] - 3.0) < 1e-9
    assert result["pnl_net"] > trade["realized_pnl_net"]


def test_metrics_include_tp1_and_exit_buckets():
    bt = Backtester(BTConfig(initial_balance=10_000))
    bt.trades = [
        BTTrade(
            entry_date="2026-01-01 00:00:00+00:00",
            exit_date="2026-01-01 01:00:00+00:00",
            strategy="sweep_reversal",
            direction="LONG",
            entry_price=100.0,
            exit_price=103.0,
            pnl_pct=2.0,
            pnl_net=20.0,
            rr_achieved=3.0,
            confidence=80,
            exit_reason="tp1_tp",
        ),
        BTTrade(
            entry_date="2026-01-01 02:00:00+00:00",
            exit_date="2026-01-01 03:00:00+00:00",
            strategy="breakout",
            direction="SHORT",
            entry_price=100.0,
            exit_price=101.0,
            pnl_pct=-1.0,
            pnl_net=-10.0,
            rr_achieved=1.0,
            confidence=70,
            exit_reason="sl",
        ),
        BTTrade(
            entry_date="2026-01-01 04:00:00+00:00",
            exit_date="2026-01-01 05:00:00+00:00",
            strategy="sweep_reversal",
            direction="LONG",
            entry_price=100.0,
            exit_price=100.5,
            pnl_pct=0.5,
            pnl_net=5.0,
            rr_achieved=0.5,
            confidence=65,
            exit_reason="timeout",
        ),
    ]
    bt.equity_curve = [
        {"date": "2026-01-01 00:00:00+00:00", "equity": 10000.0, "in_pos": False},
        {"date": "2026-01-01 05:00:00+00:00", "equity": 10015.0, "in_pos": False},
    ]

    metrics = bt._metrics()
    assert metrics["tp1_hits"] == 1
    assert metrics["full_tp_hits"] == 1
    assert metrics["sl_hits"] == 1
    assert metrics["timeout_hits"] == 1
