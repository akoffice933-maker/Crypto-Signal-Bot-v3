#!/usr/bin/env python3
"""
Signals DB report.

Reads SQLite signals.db, prints a compact summary, and writes a CSV report
with human-readable signal fields including TP1 / final TP / RR columns.

Usage:
    python scripts/signals_report.py
    python scripts/signals_report.py --db data/signals.db --limit 500
    python scripts/signals_report.py --status sent
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data/signals.db")
DEFAULT_OUTPUT_DIR = Path("results")

REPORT_COLUMNS = [
    "created_at",
    "signal_id",
    "pair",
    "strategy",
    "direction",
    "session",
    "entry_market",
    "entry_limit",
    "stop_loss",
    "tp1_price",
    "tp1_plan",
    "take_profit",
    "final_tp_size_pct",
    "rr_ratio",
    "rr_market",
    "rr_limit",
    "execution_basis",
    "confidence_score",
    "market_state",
    "volatility_regime",
    "target_liquidity_price",
    "target_liquidity_tf",
    "target_liquidity_type",
    "squeeze_active",
    "liquidation_cascade",
    "status",
    "result_pnl_pct",
    "closed_at",
]

DB_SELECT_COLUMNS = [
    "created_at",
    "signal_id",
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
    "take_profit",
    "final_tp_size_pct",
    "rr_ratio",
    "rr_market",
    "rr_limit",
    "execution_basis",
    "confidence_score",
    "market_state",
    "volatility_regime",
    "target_liquidity_price",
    "target_liquidity_tf",
    "target_liquidity_type",
    "squeeze_active",
    "liquidation_cascade",
    "status",
    "result_pnl_pct",
    "closed_at",
]


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def _fmt_pct_ratio(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.0f}%"


def _normalize_bool(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bytes):
        return 1 if value not in (b"\x00", b"", bytes([0])) else 0
    return int(bool(value))


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def fetch_signals(conn: sqlite3.Connection, limit: int | None, status: str | None) -> list[sqlite3.Row]:
    existing = _table_columns(conn, "signals")
    select_expr = []
    for col in DB_SELECT_COLUMNS:
        if col in existing:
            select_expr.append(col)
        else:
            select_expr.append(f"NULL AS {col}")

    query = f"""
        SELECT
            {", ".join(select_expr)}
        FROM signals
        WHERE 1=1
    """
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def build_report_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    report_rows: list[dict[str, Any]] = []
    for row in rows:
        tp1_price = _float_or_none(row["tp1_price"])
        tp1_rr = _float_or_none(row["tp1_rr"])
        tp1_size_pct = _float_or_none(row["tp1_size_pct"])
        report_rows.append(
            {
                "created_at": row["created_at"],
                "signal_id": row["signal_id"],
                "pair": row["pair"],
                "strategy": row["strategy"],
                "direction": row["direction"],
                "session": row["session"],
                "entry_market": _fmt_num(row["entry_market"]),
                "entry_limit": _fmt_num(row["entry_limit"]),
                "stop_loss": _fmt_num(row["stop_loss"]),
                "tp1_price": _fmt_num(tp1_price),
                "tp1_plan": (
                    f"{int(round(tp1_size_pct * 100))}% @ {tp1_rr:.1f}R"
                    if tp1_price is not None and tp1_size_pct is not None and tp1_rr is not None
                    else ""
                ),
                "take_profit": _fmt_num(row["take_profit"]),
                "final_tp_size_pct": _fmt_pct_ratio(row["final_tp_size_pct"]),
                "rr_ratio": _fmt_num(row["rr_ratio"]),
                "rr_market": _fmt_num(row["rr_market"]),
                "rr_limit": _fmt_num(row["rr_limit"]),
                "execution_basis": row["execution_basis"] or "",
                "confidence_score": row["confidence_score"],
                "market_state": row["market_state"] or "",
                "volatility_regime": row["volatility_regime"] or "",
                "target_liquidity_price": _fmt_num(row["target_liquidity_price"]),
                "target_liquidity_tf": row["target_liquidity_tf"] or "",
                "target_liquidity_type": row["target_liquidity_type"] or "",
                "squeeze_active": _normalize_bool(row["squeeze_active"]),
                "liquidation_cascade": _normalize_bool(row["liquidation_cascade"]),
                "status": row["status"] or "",
                "result_pnl_pct": _fmt_num(row["result_pnl_pct"]),
                "closed_at": row["closed_at"] or "",
            }
        )
    return report_rows


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[sqlite3.Row]) -> None:
    total = len(rows)
    statuses = Counter((row["status"] or "unknown") for row in rows)
    closed = [row for row in rows if row["status"] in {"tp_hit", "sl_hit", "expired"}]
    win_closed = sum(1 for row in rows if row["status"] == "tp_hit")
    tp1_planned = sum(1 for row in rows if row["tp1_price"] is not None)

    rr_values = [float(row["rr_ratio"]) for row in rows if row["rr_ratio"] is not None]
    conf_values = [int(row["confidence_score"]) for row in rows if row["confidence_score"] is not None]

    print("=" * 64)
    print("SIGNALS REPORT")
    print("=" * 64)
    print(f"Total signals:           {total}")
    print(f"TP1 planned:             {tp1_planned}")
    print(f"Avg RR used:             {sum(rr_values) / len(rr_values):.2f}" if rr_values else "Avg RR used:             -")
    print(f"Avg confidence:          {sum(conf_values) / len(conf_values):.1f}" if conf_values else "Avg confidence:          -")
    if closed:
        print(f"Closed signals:          {len(closed)}")
        print(f"Closed winrate:          {win_closed / len(closed) * 100:.1f}%")
    else:
        print("Closed signals:          0")
        print("Closed winrate:          -")
    print("Status breakdown:")
    for status, count in sorted(statuses.items()):
        print(f"  - {status}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CSV report from signals.db")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite DB")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows")
    parser.add_argument("--status", default=None, help="Filter by signal status")
    parser.add_argument("--out", default=None, help="Output CSV path")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = fetch_signals(conn, limit=args.limit, status=args.status)
    finally:
        conn.close()

    print_summary(rows)

    report_rows = build_report_rows(rows)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.out) if args.out else DEFAULT_OUTPUT_DIR / f"signals_report_{timestamp}.csv"
    write_csv(report_rows, output_path)
    print(f"\nCSV saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
