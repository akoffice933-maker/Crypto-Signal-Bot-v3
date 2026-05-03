#!/usr/bin/env python3
"""
Replay live signals from signals.db against future 15m candles.

The script validates saved signals using the same exit model as the backtester:
    - market or limit execution basis
    - TP1 partial at 2R (if present)
    - final TP / SL / timeout
    - limit order expiry

Outputs:
    - CSV report in results/
    - SQLite table signal_replay_results in the same DB

Usage:
    python scripts/signal_replay.py
    python scripts/signal_replay.py --limit 50
    python scripts/signal_replay.py --signal-id 85325a8415d6fc4a
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtesting.backtester import BTConfig, Backtester
from config.settings import settings
from data.binance_client import BinanceFuturesClient, KLINE_COLS


DEFAULT_DB_PATH = Path("data/signals.db")
DEFAULT_OUTPUT_DIR = Path("results")
INTERVAL_MS_15M = 900_000

SIGNAL_COLUMNS = [
    "signal_id",
    "created_at",
    "pair",
    "strategy",
    "direction",
    "session",
    "entry_market",
    "entry_limit",
    "stop_loss",
    "tp1_price",
    "tp1_rr",
    "tp1_size_pct",
    "final_tp_size_pct",
    "take_profit",
    "rr_ratio",
    "rr_market",
    "rr_limit",
    "execution_basis",
    "position_size_pct",
    "confidence_score",
    "volatility_regime",
    "status",
]

RESULT_COLUMNS = [
    "signal_id",
    "created_at",
    "pair",
    "strategy",
    "direction",
    "execution_basis",
    "entry_market",
    "entry_limit",
    "stop_loss",
    "tp1_price",
    "take_profit",
    "rr_ratio",
    "rr_market",
    "rr_limit",
    "entry_filled",
    "fill_price",
    "fill_time",
    "candles_to_fill",
    "tp1_hit",
    "tp1_hit_candles",
    "tp1_hit_minutes",
    "tp1_hit_time",
    "tp1_hit_price",
    "final_tp_hit",
    "sl_hit",
    "timeout_hit",
    "exit_reason",
    "exit_type_detail",
    "exit_price",
    "exit_time",
    "candles_held",
    "pnl_pct",
    "pnl_net",
    "rr_achieved",
    "timeout_pnl_pct",
    "mfe_pct",
    "mae_pct",
    "mfe_mae_ratio",
    "validation_status",
    "config_id",
    "validated_at",
]

RESULTS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_replay_results (
    signal_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pair TEXT NOT NULL,
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,
    execution_basis TEXT,
    entry_market REAL,
    entry_limit REAL,
    stop_loss REAL,
    tp1_price REAL,
    take_profit REAL,
    rr_ratio REAL,
    rr_market REAL,
    rr_limit REAL,
    entry_filled INTEGER NOT NULL DEFAULT 0,
    fill_price REAL,
    fill_time TEXT,
    candles_to_fill INTEGER,
    tp1_hit INTEGER NOT NULL DEFAULT 0,
    tp1_hit_candles INTEGER,
    tp1_hit_minutes INTEGER,
    tp1_hit_time TEXT,
    tp1_hit_price REAL,
    final_tp_hit INTEGER NOT NULL DEFAULT 0,
    sl_hit INTEGER NOT NULL DEFAULT 0,
    timeout_hit INTEGER NOT NULL DEFAULT 0,
    exit_reason TEXT,
    exit_type_detail TEXT,
    exit_price REAL,
    exit_time TEXT,
    candles_held INTEGER,
    pnl_pct REAL,
    pnl_net REAL,
    rr_achieved REAL,
    timeout_pnl_pct REAL,
    mfe_pct REAL,
    mae_pct REAL,
    mfe_mae_ratio REAL,
    validation_status TEXT NOT NULL,
    config_id TEXT NOT NULL DEFAULT 'default',
    validated_at TEXT NOT NULL,
    PRIMARY KEY (signal_id, config_id)
)
"""


@dataclass
class ReplayConfig:
    initial_balance: float = 10_000.0
    default_position_pct: float = 0.10
    max_candles_hold: int = 20
    limit_order_expiry_candles: int = 2
    default_execution_basis: str = "limit"
    fee_pct: float = 0.0004
    tp_model: str = "liquidity"
    tp_max_pct: float | None = None
    sl_atr_multiplier: float = 0.5
    baseline_sl_multiplier: float = 0.5
    tp1_multiplier: float = 2.0
    reduced_rr_multiple: float = 3.0
    config_id: str = "default"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay live signals from signals.db")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite DB")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of signals")
    parser.add_argument("--signal-id", default=None, help="Replay only one signal_id")
    parser.add_argument("--pair", default=None, help="Filter by pair")
    parser.add_argument("--out", default=None, help="CSV output path")
    parser.add_argument("--initial-balance", type=float, default=10_000.0)
    parser.add_argument("--position-pct", type=float, default=0.10)
    parser.add_argument("--max-candles-hold", type=int, default=20)
    parser.add_argument("--limit-expiry", type=int, default=2)
    parser.add_argument("--default-basis", choices=["market", "limit"], default="limit")
    parser.add_argument("--tp-model", choices=["liquidity", "capped", "reduced_multiple"], default="liquidity")
    parser.add_argument("--tp-max-pct", type=float, default=None)
    parser.add_argument("--sl-mult", type=float, default=0.5)
    parser.add_argument("--tp1-mult", type=float, default=2.0)
    parser.add_argument("--reduced-rr-mult", type=float, default=3.0)
    return parser.parse_args()


def _parse_ts(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def fetch_signals(
    conn: sqlite3.Connection,
    *,
    limit: int | None,
    signal_id: str | None,
    pair: str | None,
) -> list[sqlite3.Row]:
    existing = _table_columns(conn, "signals")
    select_expr = [
        col if col in existing else f"NULL AS {col}"
        for col in SIGNAL_COLUMNS
    ]
    query = f"""
        SELECT {", ".join(select_expr)}
        FROM signals
        WHERE 1=1
    """
    params: list[Any] = []
    if signal_id:
        query += " AND signal_id = ?"
        params.append(signal_id)
    if pair:
        query += " AND pair = ?"
        params.append(pair.upper())
    query += " ORDER BY created_at DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return list(reversed(rows))


def ensure_results_table(conn: sqlite3.Connection) -> None:
    _migrate_results_table_if_needed(conn)
    conn.execute(RESULTS_TABLE_SCHEMA)
    for column, definition in (
        ("tp1_hit_candles", "INTEGER"),
        ("tp1_hit_minutes", "INTEGER"),
        ("tp1_hit_time", "TEXT"),
        ("tp1_hit_price", "REAL"),
        ("exit_type_detail", "TEXT"),
        ("timeout_pnl_pct", "REAL"),
        ("mfe_pct", "REAL"),
        ("mae_pct", "REAL"),
        ("mfe_mae_ratio", "REAL"),
        ("config_id", "TEXT NOT NULL DEFAULT 'default'"),
    ):
        _ensure_column(conn, "signal_replay_results", column, definition)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_signal_replay_created ON signal_replay_results(created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_signal_replay_status ON signal_replay_results(validation_status, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_signal_replay_config ON signal_replay_results(config_id, created_at DESC)"
    )
    conn.commit()


def _table_sql(conn: sqlite3.Connection, table: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row[0] if row and row[0] else None


def _has_config_aware_pk(table_sql: str | None) -> bool:
    if not table_sql:
        return False
    normalized = " ".join(table_sql.lower().split())
    return "primary key (signal_id, config_id)" in normalized


def _migrate_results_table_if_needed(conn: sqlite3.Connection) -> None:
    table_sql = _table_sql(conn, "signal_replay_results")
    if not table_sql or _has_config_aware_pk(table_sql):
        return

    legacy_table = "signal_replay_results_legacy"
    conn.execute(f"DROP TABLE IF EXISTS {legacy_table}")
    conn.execute(f"ALTER TABLE signal_replay_results RENAME TO {legacy_table}")
    conn.execute(RESULTS_TABLE_SCHEMA)

    legacy_columns = _table_columns(conn, legacy_table)
    insert_columns = list(RESULT_COLUMNS)
    select_expr: list[str] = []
    for column in insert_columns:
        if column == "config_id":
            if "config_id" in legacy_columns:
                select_expr.append("COALESCE(config_id, 'default') AS config_id")
            else:
                select_expr.append("'default' AS config_id")
        elif column == "validated_at" and column not in legacy_columns:
            select_expr.append("CURRENT_TIMESTAMP AS validated_at")
        elif column in legacy_columns:
            select_expr.append(column)
        else:
            select_expr.append(f"NULL AS {column}")

    conn.execute(
        f"""
        INSERT INTO signal_replay_results ({", ".join(insert_columns)})
        SELECT {", ".join(select_expr)}
        FROM {legacy_table}
        """
    )
    conn.execute(f"DROP TABLE {legacy_table}")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = _table_columns(conn, table)
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _normalize_num(value: Any) -> float | None:
    return None if value is None else float(value)


def _calculate_rr(
    direction: str,
    entry_price: float | None,
    stop_loss: float,
    take_profit: float,
) -> float | None:
    if entry_price is None:
        return None
    if direction == "LONG":
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
    else:
        risk = stop_loss - entry_price
        reward = entry_price - take_profit
    if risk <= 0:
        return None
    return reward / risk


def calculate_mfe_mae(candles: pd.DataFrame, entry_price: float, direction: str) -> tuple[float | None, float | None]:
    if candles.empty:
        return None, None
    if direction == "LONG":
        mfe = (float(candles["high"].max()) - entry_price) / entry_price * 100
        mae = (entry_price - float(candles["low"].min())) / entry_price * 100
    else:
        mfe = (entry_price - float(candles["low"].min())) / entry_price * 100
        mae = (float(candles["high"].max()) - entry_price) / entry_price * 100
    return mfe, mae


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def _compute_exit_prices(row: sqlite3.Row, cfg: ReplayConfig, basis: str) -> tuple[float, float, float | None, float | None, float]:
    entry_price = _normalize_num(row["entry_limit"]) if basis == "limit" and row["entry_limit"] is not None else float(row["entry_market"])
    original_stop = float(row["stop_loss"])
    original_tp = float(row["take_profit"])
    original_risk = abs(entry_price - original_stop)
    scaled_risk = original_risk * (cfg.sl_atr_multiplier / cfg.baseline_sl_multiplier)

    if row["direction"] == "LONG":
        stop_loss = entry_price - scaled_risk
        if cfg.tp_model == "capped" and cfg.tp_max_pct is not None and row["volatility_regime"] == "quiet":
            take_profit = min(original_tp, entry_price * (1 + cfg.tp_max_pct / 100))
        elif cfg.tp_model == "reduced_multiple":
            take_profit = entry_price + scaled_risk * cfg.reduced_rr_multiple
        else:
            take_profit = original_tp
        tp1_price = entry_price + scaled_risk * cfg.tp1_multiplier
    else:
        stop_loss = entry_price + scaled_risk
        if cfg.tp_model == "capped" and cfg.tp_max_pct is not None and row["volatility_regime"] == "quiet":
            take_profit = max(original_tp, entry_price * (1 - cfg.tp_max_pct / 100))
        elif cfg.tp_model == "reduced_multiple":
            take_profit = entry_price - scaled_risk * cfg.reduced_rr_multiple
        else:
            take_profit = original_tp
        tp1_price = entry_price - scaled_risk * cfg.tp1_multiplier

    tp1_size = _normalize_num(row["tp1_size_pct"])
    final_tp_size = _normalize_num(row["final_tp_size_pct"])
    if tp1_size is None:
        tp1_size = settings.tp1_size_pct
    if final_tp_size is None:
        final_tp_size = 1.0 - tp1_size if tp1_price is not None else 1.0

    # Drop TP1 if final target is already closer than TP1.
    if row["direction"] == "LONG" and take_profit <= tp1_price:
        tp1_price, tp1_size, final_tp_size = None, None, 1.0
    if row["direction"] == "SHORT" and take_profit >= tp1_price:
        tp1_price, tp1_size, final_tp_size = None, None, 1.0

    return stop_loss, take_profit, tp1_price, tp1_size, final_tp_size


def _exit_type_detail(reason: str | None) -> str | None:
    if reason is None:
        return None
    mapping = {
        "sl": "sl",
        "tp": "tp2",
        "timeout": "timeout",
        "tp1_tp": "partial_tp1_tp2",
        "tp1_sl": "partial_tp1_sl",
        "tp1_timeout": "partial_tp1_timeout",
        "no_fill": "no_fill",
    }
    return mapping.get(reason, reason)


def _row_to_signal(row: sqlite3.Row, cfg: ReplayConfig) -> dict[str, Any]:
    basis = row["execution_basis"]
    if not basis:
        basis = cfg.default_execution_basis if row["entry_limit"] is not None else "market"
    stop_loss, take_profit, tp1_price, tp1_size, final_tp_size = _compute_exit_prices(row, cfg, basis)
    return {
        "strategy": row["strategy"],
        "direction": row["direction"],
        "entry_market": float(row["entry_market"]),
        "entry_limit": _normalize_num(row["entry_limit"]),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "tp1_price": tp1_price,
        "tp1_size_pct": tp1_size,
        "final_tp_size_pct": final_tp_size,
        "execution_basis": basis,
        "rr": abs(take_profit - (float(row["entry_market"]) if basis == "market" or row["entry_limit"] is None else float(row["entry_limit"]))) / abs((float(row["entry_market"]) if basis == "market" or row["entry_limit"] is None else float(row["entry_limit"])) - stop_loss),
        "confidence": int(row["confidence_score"] or 0),
    }


def _build_backtester(signal_row: sqlite3.Row, cfg: ReplayConfig, basis: str) -> Backtester:
    pos_pct = _normalize_num(signal_row["position_size_pct"]) or cfg.default_position_pct
    return Backtester(
        BTConfig(
            initial_balance=cfg.initial_balance,
            fee_pct=cfg.fee_pct,
            slippage_pct=0.0,
            max_position_pct=pos_pct,
            max_candles_hold=cfg.max_candles_hold,
            execution_basis=basis,
            limit_order_expiry_candles=cfg.limit_order_expiry_candles,
        )
    )


def replay_signal(signal_row: sqlite3.Row, future_df: pd.DataFrame, cfg: ReplayConfig) -> dict[str, Any]:
    validated_at = datetime.now(timezone.utc).isoformat()
    signal = _row_to_signal(signal_row, cfg)
    basis = signal["execution_basis"]
    created_at = _parse_ts(signal_row["created_at"])
    entry_market = _normalize_num(signal_row["entry_market"])
    entry_limit = _normalize_num(signal_row["entry_limit"])
    rr_market = _calculate_rr(
        signal_row["direction"],
        entry_market,
        signal["stop_loss"],
        signal["take_profit"],
    )
    rr_limit = _calculate_rr(
        signal_row["direction"],
        entry_limit,
        signal["stop_loss"],
        signal["take_profit"],
    )
    rr_ratio = rr_limit if basis == "limit" and rr_limit is not None else rr_market
    result = {
        "signal_id": signal_row["signal_id"],
        "created_at": signal_row["created_at"],
        "pair": signal_row["pair"],
        "strategy": signal_row["strategy"],
        "direction": signal_row["direction"],
        "execution_basis": basis,
        "entry_market": entry_market,
        "entry_limit": entry_limit,
        "stop_loss": signal["stop_loss"],
        "tp1_price": signal["tp1_price"],
        "take_profit": signal["take_profit"],
        "rr_ratio": rr_ratio,
        "rr_market": rr_market,
        "rr_limit": rr_limit,
        "entry_filled": 0,
        "fill_price": None,
        "fill_time": None,
        "candles_to_fill": None,
        "tp1_hit": 0,
        "tp1_hit_candles": None,
        "tp1_hit_minutes": None,
        "tp1_hit_time": None,
        "tp1_hit_price": None,
        "final_tp_hit": 0,
        "sl_hit": 0,
        "timeout_hit": 0,
        "exit_reason": None,
        "exit_type_detail": None,
        "exit_price": None,
        "exit_time": None,
        "candles_held": None,
        "pnl_pct": None,
        "pnl_net": None,
        "rr_achieved": None,
        "timeout_pnl_pct": None,
        "mfe_pct": None,
        "mae_pct": None,
        "mfe_mae_ratio": None,
        "validation_status": "pending",
        "config_id": cfg.config_id,
        "validated_at": validated_at,
    }

    if future_df.empty:
        result["validation_status"] = "no_data"
        return result

    bt = _build_backtester(signal_row, cfg, basis)

    if basis == "limit" and signal.get("entry_limit") is not None:
        trade = None
        fill_idx = None
        expiry_idx = min(len(future_df), cfg.limit_order_expiry_candles + cfg.max_candles_hold + 2)
        for idx in range(expiry_idx):
            row = future_df.iloc[idx]
            if float(row["low"]) <= signal["entry_limit"] <= float(row["high"]):
                trade = bt._build_trade(signal, signal["entry_limit"], cfg.initial_balance, idx, limit_fill=True)
                fill_idx = idx
                result["entry_filled"] = 1
                result["fill_price"] = signal["entry_limit"]
                result["fill_time"] = str(row["open_time"])
                result["candles_to_fill"] = idx
                break
        if trade is None:
            result["validation_status"] = "no_fill"
            result["exit_reason"] = "no_fill"
            result["exit_type_detail"] = "no_fill"
            return result
    else:
        fill_idx = 0
        trade = bt._build_trade(signal, signal["entry_market"], cfg.initial_balance, 0, limit_fill=False)
        result["entry_filled"] = 1
        result["fill_price"] = signal["entry_market"]
        result["fill_time"] = signal_row["created_at"]
        result["candles_to_fill"] = 0

    for idx in range(fill_idx, len(future_df)):
        row = future_df.iloc[idx]
        tp1_hit_before = trade["tp1_hit"]
        managed = bt._manage(trade, future_df, idx, row)
        if not tp1_hit_before and trade["tp1_hit"]:
            result["tp1_hit"] = 1
            result["tp1_hit_candles"] = idx - fill_idx
            result["tp1_hit_minutes"] = (idx - fill_idx) * 15
            result["tp1_hit_time"] = str(row["open_time"])
            result["tp1_hit_price"] = trade.get("tp1_price")
        if managed is None:
            continue

        exit_reason = managed["reason"]
        result["tp1_hit"] = int(trade["tp1_hit"])
        result["final_tp_hit"] = int(exit_reason in {"tp", "tp1_tp"})
        result["sl_hit"] = int(exit_reason in {"sl", "tp1_sl"})
        result["timeout_hit"] = int(exit_reason in {"timeout", "tp1_timeout"})
        result["exit_reason"] = exit_reason
        result["exit_type_detail"] = _exit_type_detail(exit_reason)
        result["exit_price"] = managed["exit_price"]
        result["exit_time"] = str(row["open_time"])
        result["candles_held"] = idx - fill_idx
        result["pnl_pct"] = managed["pnl_pct"]
        result["pnl_net"] = managed["pnl_net"]
        result["rr_achieved"] = managed["rr"]
        if result["timeout_hit"]:
            result["timeout_pnl_pct"] = managed["pnl_pct"]
        trade_path = future_df.iloc[fill_idx: idx + 1]
        mfe_pct, mae_pct = calculate_mfe_mae(trade_path, float(result["fill_price"]), signal_row["direction"])
        result["mfe_pct"] = mfe_pct
        result["mae_pct"] = mae_pct
        if mfe_pct is not None and mae_pct not in (None, 0):
            result["mfe_mae_ratio"] = mfe_pct / mae_pct
        result["validation_status"] = "validated"
        return result

    result["validation_status"] = "insufficient_future_data"
    if result["entry_filled"]:
        trade_path = future_df.iloc[fill_idx:]
        mfe_pct, mae_pct = calculate_mfe_mae(trade_path, float(result["fill_price"]), signal_row["direction"])
        result["mfe_pct"] = mfe_pct
        result["mae_pct"] = mae_pct
        if mfe_pct is not None and mae_pct not in (None, 0):
            result["mfe_mae_ratio"] = mfe_pct / mae_pct
    return result


def _result_summary(results: list[dict[str, Any]]) -> None:
    summary = summarize_results(results)
    print("=" * 64)
    print("SIGNAL REPLAY")
    print("=" * 64)
    print(f"Signals processed:        {summary['signals_processed']}")
    print(f"Validated:                {summary['validated']}")
    print(f"No fill:                  {summary['no_fill']}")
    print(f"No data:                  {summary['no_data']}")
    print(f"Insufficient candles:     {summary['insufficient_future_data']}")
    print(f"Full TP hits:             {summary['full_tp_hits']}")
    print(f"SL hits:                  {summary['sl_hits']}")
    print(f"Timeout hits:             {summary['timeout_hits']}")
    print(
        f"Avg achieved RR:          {summary['avg_rr_achieved']:.2f}"
        if summary["validated"]
        else "Avg achieved RR:          -"
    )


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    validated = [row for row in results if row["validation_status"] == "validated"]
    no_fill = sum(1 for row in results if row["validation_status"] == "no_fill")
    no_data = sum(1 for row in results if row["validation_status"] == "no_data")
    insufficient = sum(1 for row in results if row["validation_status"] == "insufficient_future_data")
    tp = sum(1 for row in validated if row["final_tp_hit"])
    sl = sum(1 for row in validated if row["sl_hit"])
    timeout = sum(1 for row in validated if row["timeout_hit"])
    tp1_hits = sum(1 for row in validated if row["tp1_hit"])
    avg_rr = (
        sum(float(row["rr_achieved"]) for row in validated if row["rr_achieved"] is not None) / len(validated)
        if validated else 0.0
    )
    expectancy = (
        sum(float(row["pnl_pct"]) for row in validated if row["pnl_pct"] is not None) / len(validated)
        if validated else 0.0
    )
    profits = [float(row["pnl_pct"]) for row in validated if row["pnl_pct"] is not None and row["pnl_pct"] > 0]
    losses = [float(row["pnl_pct"]) for row in validated if row["pnl_pct"] is not None and row["pnl_pct"] < 0]
    profit_factor = (
        sum(profits) / abs(sum(losses))
        if losses else (float("inf") if profits else 0.0)
    )
    avg_mfe = (
        sum(float(row["mfe_pct"]) for row in validated if row["mfe_pct"] is not None) / len([row for row in validated if row["mfe_pct"] is not None])
        if any(row["mfe_pct"] is not None for row in validated) else 0.0
    )
    avg_mae = (
        sum(float(row["mae_pct"]) for row in validated if row["mae_pct"] is not None) / len([row for row in validated if row["mae_pct"] is not None])
        if any(row["mae_pct"] is not None for row in validated) else 0.0
    )
    timeout_pnls = sorted(float(row["timeout_pnl_pct"]) for row in validated if row["timeout_pnl_pct"] is not None)
    if timeout_pnls:
        mid = len(timeout_pnls) // 2
        timeout_median = timeout_pnls[mid] if len(timeout_pnls) % 2 == 1 else (timeout_pnls[mid - 1] + timeout_pnls[mid]) / 2
    else:
        timeout_median = None
    config = validated[0]["config_id"] if validated else (results[0]["config_id"] if results else "default")
    return {
        "config_id": config,
        "signals_processed": total,
        "validated": len(validated),
        "no_fill": no_fill,
        "no_data": no_data,
        "insufficient_future_data": insufficient,
        "full_tp_hits": tp,
        "tp1_hits": tp1_hits,
        "sl_hits": sl,
        "timeout_hits": timeout,
        "avg_rr_achieved": avg_rr,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "sl_rate": (sl / len(validated)) if validated else 0.0,
        "timeout_rate": (timeout / len(validated)) if validated else 0.0,
        "full_tp_rate": (tp / len(validated)) if validated else 0.0,
        "tp1_hit_rate": (tp1_hits / len(validated)) if validated else 0.0,
        "avg_mfe_pct": avg_mfe,
        "avg_mae_pct": avg_mae,
        "mfe_mae_ratio": (avg_mfe / avg_mae) if avg_mae else 0.0,
        "timeout_pnl_median": timeout_median,
    }


async def fetch_candles_between(
    client: BinanceFuturesClient,
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor <= end_ms:
        batch = await client.get_klines(
            symbol=symbol,
            interval="15m",
            limit=1500,
            start_time=cursor,
            end_time=end_ms,
        )
        if not batch:
            break
        rows.extend(batch)
        last_open = int(batch[-1][0])
        next_cursor = last_open + INTERVAL_MS_15M
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1500:
            break

    if not rows:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

    deduped = {int(row[0]): row for row in rows}
    df = pd.DataFrame([deduped[k] for k in sorted(deduped)], columns=KLINE_COLS)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["open_time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _signals_time_bounds(rows: list[sqlite3.Row], cfg: ReplayConfig) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = min(_parse_ts(row["created_at"]) for row in rows)
    end = max(_parse_ts(row["created_at"]) for row in rows)
    end += timedelta(minutes=15 * (cfg.limit_order_expiry_candles + cfg.max_candles_hold + 2))
    return start, end


def write_results_csv(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)


def save_results_to_db(conn: sqlite3.Connection, results: list[dict[str, Any]]) -> None:
    ensure_results_table(conn)
    update_columns = [col for col in RESULT_COLUMNS if col not in {"signal_id", "config_id"}]
    conn.executemany(
        f"""
        INSERT INTO signal_replay_results (
            {", ".join(RESULT_COLUMNS)}
        ) VALUES (
            {", ".join(':' + col for col in RESULT_COLUMNS)}
        )
        ON CONFLICT(signal_id, config_id) DO UPDATE SET
            {", ".join(f"{col}=excluded.{col}" for col in update_columns)}
        """,
        results,
    )
    conn.commit()


async def run_signal_replay(
    *,
    db_path: str = str(DEFAULT_DB_PATH),
    limit: int | None = None,
    signal_id: str | None = None,
    pair: str | None = None,
    out: str | None = None,
    initial_balance: float = 10_000.0,
    position_pct: float = 0.10,
    max_candles_hold: int = 20,
    limit_expiry: int = 2,
    default_basis: str = "limit",
    tp_model: str = "liquidity",
    tp_max_pct: float | None = None,
    sl_mult: float = 0.5,
    tp1_mult: float = 2.0,
    reduced_rr_mult: float = 3.0,
    config_id: str | None = None,
    store_db: bool = True,
) -> dict[str, Any]:
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"DB not found: {db_file}")

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        signal_rows = fetch_signals(
            conn,
            limit=limit,
            signal_id=signal_id,
            pair=pair,
        )
        if not signal_rows:
            raise ValueError("No signals found for replay")

        cfg = ReplayConfig(
            initial_balance=initial_balance,
            default_position_pct=position_pct,
            max_candles_hold=max_candles_hold,
            limit_order_expiry_candles=limit_expiry,
            default_execution_basis=default_basis,
            tp_model=tp_model,
            tp_max_pct=tp_max_pct,
            sl_atr_multiplier=sl_mult,
            tp1_multiplier=tp1_mult,
            reduced_rr_multiple=reduced_rr_mult,
            config_id=config_id or _config_hash({
                "timeout": max_candles_hold,
                "tp_model": tp_model,
                "tp_max_pct": tp_max_pct,
                "sl_mult": sl_mult,
                "tp1_mult": tp1_mult,
                "reduced_rr_mult": reduced_rr_mult,
            }),
        )

        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in signal_rows:
            grouped.setdefault(row["pair"], []).append(row)

        results: list[dict[str, Any]] = []
        client = BinanceFuturesClient(settings.base_url)
        try:
            for replay_pair, rows in grouped.items():
                start_ts, end_ts = _signals_time_bounds(rows, cfg)
                candles = await fetch_candles_between(
                    client,
                    replay_pair,
                    int(start_ts.timestamp() * 1000),
                    int(end_ts.timestamp() * 1000),
                )
                for row in rows:
                    created_at = _parse_ts(row["created_at"])
                    future_df = candles[candles["open_time"] > created_at].reset_index(drop=True)
                    results.append(replay_signal(row, future_df, cfg))
        finally:
            await client.close()

        if store_db:
            save_results_to_db(conn, results)
    finally:
        conn.close()

    summary = summarize_results(results)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(out) if out else DEFAULT_OUTPUT_DIR / f"signal_replay_{timestamp}.csv"
    write_results_csv(results, out_path)
    return {
        "summary": summary,
        "results": results,
        "csv_path": str(out_path),
        "db_path": str(db_file),
        "config": {
            "config_id": cfg.config_id,
            "timeout_candles": cfg.max_candles_hold,
            "tp_model": cfg.tp_model,
            "tp_max_pct": cfg.tp_max_pct,
            "sl_mult": cfg.sl_atr_multiplier,
            "tp1_mult": cfg.tp1_multiplier,
            "reduced_rr_mult": cfg.reduced_rr_multiple,
        },
    }


async def main() -> int:
    args = parse_args()
    replay = await run_signal_replay(
        db_path=args.db,
        limit=args.limit,
        signal_id=args.signal_id,
        pair=args.pair,
        out=args.out,
        initial_balance=args.initial_balance,
        position_pct=args.position_pct,
        max_candles_hold=args.max_candles_hold,
        limit_expiry=args.limit_expiry,
        default_basis=args.default_basis,
        tp_model=args.tp_model,
        tp_max_pct=args.tp_max_pct,
        sl_mult=args.sl_mult,
        tp1_mult=args.tp1_mult,
        reduced_rr_mult=args.reduced_rr_mult,
    )
    results = replay["results"]
    _result_summary(results)
    print(f"\nCSV saved: {replay['csv_path']}")
    print(f"DB table updated: {args.db} -> signal_replay_results")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
