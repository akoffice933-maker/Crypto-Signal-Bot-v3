import os
import sqlite3
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.signal_replay import ReplayConfig, ensure_results_table, replay_signal, save_results_to_db


def _signal_row(**overrides):
    base = {
        "signal_id": "sig-1",
        "created_at": "2026-03-27 10:00:04",
        "pair": "BTCUSDT",
        "strategy": "sweep_reversal",
        "direction": "LONG",
        "session": "ny",
        "entry_market": 100.0,
        "entry_limit": 99.0,
        "stop_loss": 98.0,
        "tp1_price": 101.0,
        "tp1_rr": 2.0,
        "tp1_size_pct": 0.5,
        "final_tp_size_pct": 0.5,
        "take_profit": 103.0,
        "rr_ratio": 4.0,
        "rr_market": 3.0,
        "rr_limit": 4.0,
        "execution_basis": "limit",
        "position_size_pct": 0.10,
        "confidence_score": 80,
        "status": "sent",
    }
    base.update(overrides)
    return base


def test_replay_limit_signal_tp1_then_final_tp():
    future = pd.DataFrame(
        [
            {
                "open_time": pd.Timestamp("2026-03-27 10:15:00+00:00"),
                "open": 100.0,
                "high": 100.2,
                "low": 98.9,
                "close": 99.4,
                "volume": 1000.0,
            },
            {
                "open_time": pd.Timestamp("2026-03-27 10:30:00+00:00"),
                "open": 99.4,
                "high": 101.2,
                "low": 99.2,
                "close": 100.8,
                "volume": 900.0,
            },
            {
                "open_time": pd.Timestamp("2026-03-27 10:45:00+00:00"),
                "open": 100.8,
                "high": 103.2,
                "low": 100.7,
                "close": 102.9,
                "volume": 1200.0,
            },
        ]
    )

    result = replay_signal(_signal_row(), future, ReplayConfig())

    assert result["validation_status"] == "validated"
    assert result["entry_filled"] == 1
    assert result["fill_price"] == 99.0
    assert result["tp1_hit"] == 1
    assert result["final_tp_hit"] == 1
    assert result["exit_reason"] == "tp1_tp"
    assert round(float(result["rr_achieved"]), 2) == 3.00


def test_replay_limit_signal_no_fill():
    future = pd.DataFrame(
        [
            {
                "open_time": pd.Timestamp("2026-03-27 10:15:00+00:00"),
                "open": 100.0,
                "high": 100.4,
                "low": 99.7,
                "close": 100.1,
                "volume": 1000.0,
            },
            {
                "open_time": pd.Timestamp("2026-03-27 10:30:00+00:00"),
                "open": 100.1,
                "high": 100.5,
                "low": 99.8,
                "close": 100.2,
                "volume": 900.0,
            },
        ]
    )

    result = replay_signal(_signal_row(), future, ReplayConfig(limit_order_expiry_candles=2))

    assert result["validation_status"] == "no_fill"
    assert result["entry_filled"] == 0
    assert result["exit_reason"] == "no_fill"


def test_replay_reports_configured_exit_levels_and_rr():
    future = pd.DataFrame(
        [
            {
                "open_time": pd.Timestamp("2026-03-27 10:15:00+00:00"),
                "open": 100.0,
                "high": 99.5,
                "low": 98.9,
                "close": 99.1,
                "volume": 1000.0,
            },
            {
                "open_time": pd.Timestamp("2026-03-27 10:30:00+00:00"),
                "open": 99.1,
                "high": 103.4,
                "low": 99.0,
                "close": 103.0,
                "volume": 900.0,
            },
            {
                "open_time": pd.Timestamp("2026-03-27 10:45:00+00:00"),
                "open": 103.0,
                "high": 105.3,
                "low": 102.8,
                "close": 105.0,
                "volume": 1200.0,
            },
        ]
    )

    result = replay_signal(
        _signal_row(take_profit=103.0, tp1_price=101.0),
        future,
        ReplayConfig(sl_atr_multiplier=1.0, tp1_multiplier=2.0, reduced_rr_multiple=3.0, tp_model="reduced_multiple"),
    )

    assert result["validation_status"] == "validated"
    assert result["stop_loss"] == 97.0
    assert result["tp1_price"] == 103.0
    assert result["take_profit"] == 105.0
    assert round(float(result["rr_ratio"]), 2) == 3.00
    assert round(float(result["rr_market"]), 2) == 1.67
    assert round(float(result["rr_limit"]), 2) == 3.00


def test_save_results_to_db_keeps_distinct_configs_per_signal():
    tmp_root = Path(__file__).resolve().parent / "_tmp_signal_replay"
    tmp_dir = tmp_root / uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_dir / "replay.db"
    conn = sqlite3.connect(db_path)
    try:
        ensure_results_table(conn)
        base = {
            "signal_id": "sig-1",
            "created_at": "2026-03-27 10:00:04",
            "pair": "BTCUSDT",
            "strategy": "sweep_reversal",
            "direction": "LONG",
            "execution_basis": "limit",
            "entry_market": 100.0,
            "entry_limit": 99.0,
            "stop_loss": 98.0,
            "tp1_price": 101.0,
            "take_profit": 103.0,
            "rr_ratio": 4.0,
            "rr_market": 3.0,
            "rr_limit": 4.0,
            "entry_filled": 1,
            "fill_price": 99.0,
            "fill_time": "2026-03-27 10:15:00+00:00",
            "candles_to_fill": 1,
            "tp1_hit": 1,
            "tp1_hit_candles": 1,
            "tp1_hit_minutes": 15,
            "tp1_hit_time": "2026-03-27 10:30:00+00:00",
            "tp1_hit_price": 101.0,
            "final_tp_hit": 1,
            "sl_hit": 0,
            "timeout_hit": 0,
            "exit_reason": "tp1_tp",
            "exit_type_detail": "partial_tp1_tp2",
            "exit_price": 103.0,
            "exit_time": "2026-03-27 10:45:00+00:00",
            "candles_held": 2,
            "pnl_pct": 1.5,
            "pnl_net": 15.0,
            "rr_achieved": 3.0,
            "timeout_pnl_pct": None,
            "mfe_pct": 2.0,
            "mae_pct": 0.5,
            "mfe_mae_ratio": 4.0,
            "validation_status": "validated",
            "validated_at": "2026-03-27T11:00:00+00:00",
        }
        results = [
            {**base, "config_id": "A1"},
            {**base, "config_id": "B2", "take_profit": 102.0, "rr_ratio": 2.5},
        ]

        save_results_to_db(conn, results)
        rows = conn.execute(
            """
            SELECT signal_id, config_id, take_profit, rr_ratio
            FROM signal_replay_results
            ORDER BY config_id
            """
        ).fetchall()
        assert rows == [
            ("sig-1", "A1", 103.0, 4.0),
            ("sig-1", "B2", 102.0, 2.5),
        ]
    finally:
        conn.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_replay_limit_signal_tp1_then_final_tp()
    test_replay_limit_signal_no_fill()
    test_replay_reports_configured_exit_levels_and_rr()
    test_save_results_to_db_keeps_distinct_configs_per_signal()
    print("[OK] signal replay tests passed")
