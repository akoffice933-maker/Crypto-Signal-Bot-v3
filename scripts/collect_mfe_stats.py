#!/usr/bin/env python3
"""
MFE/MAE Statistics Collector

Analyzes historical signals to calculate:
- Average MFE (Maximum Favorable Excursion) per pair
- Average MAE (Maximum Adverse Excursion) per pair
- Optimal TP1 distance based on MFE
- Optimal SL distance based on MAE

Usage:
    python scripts/collect_mfe_stats.py --limit 100
    python scripts/collect_mfe_stats.py --pair BTCUSDT
    python scripts/collect_mfe_stats.py --output results/mfe_stats.json
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import Database
from config.settings import settings


def calculate_mfe_mae(
    conn: sqlite3.Connection,
    signal_id: str,
    entry_price: float,
    direction: str,
    entry_time: str,
    exit_time: str,
    pair: str,
) -> tuple[float | None, float | None]:
    """
    Calculate MFE and MAE for a signal using 15m candles.
    """
    from data.binance_client import BinanceFuturesClient, KLINE_COLS
    import pandas as pd
    import asyncio

    # Fetch candles from entry to exit
    client = BinanceFuturesClient(settings.base_url)

    try:
        # Parse times
        entry_ts = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        exit_ts = datetime.fromisoformat(exit_time.replace("Z", "+00:00")) if exit_time else datetime.now(timezone.utc)

        # Add buffer
        start_ms = int(entry_ts.timestamp() * 1000)
        end_ms = int(exit_ts.timestamp() * 1000) + 900000  # +1 candle

        # Fetch candles
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            candles = loop.run_until_complete(
                fetch_candles(client, pair, start_ms, end_ms)
            )
        finally:
            loop.close()

        if candles.empty:
            return None, None

        # Calculate MFE/MAE
        if direction == "LONG":
            mfe = (float(candles["high"].max()) - entry_price) / entry_price * 100
            mae = (entry_price - float(candles["low"].min())) / entry_price * 100
        else:  # SHORT
            mfe = (entry_price - float(candles["low"].min())) / entry_price * 100
            mae = (float(candles["high"].max()) - entry_price) / entry_price * 100

        return mfe, mae

    except Exception as e:
        print(f"Error calculating MFE/MAE for {signal_id}: {e}")
        return None, None
    finally:
        asyncio.get_event_loop().close()


async def fetch_candles(client, symbol: str, start_ms: int, end_ms: int):
    """Fetch 15m candles from Binance."""
    import pandas as pd
    from data.binance_client import KLINE_COLS

    rows = []
    cursor = start_ms
    interval_ms = 900000  # 15m

    while cursor <= end_ms:
        batch = await client.get_klines(
            symbol=symbol.lower(),
            interval="15m",
            limit=100,
            start_time=cursor,
            end_time=end_ms,
        )
        if not batch:
            break
        rows.extend(batch)
        last_open = int(batch[-1][0])
        next_cursor = last_open + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 100:
            break

    if not rows:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

    deduped = {int(row[0]): row for row in rows}
    df = pd.DataFrame([deduped[k] for k in sorted(deduped)], columns=KLINE_COLS)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["open_time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def collect_statistics(
    db_path: str,
    limit: int = 100,
    pair: str | None = None,
) -> Dict[str, Any]:
    """
    Collect MFE/MAE statistics from historical signals.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch signals
    query = """
        SELECT signal_id, pair, direction, entry_market, created_at,
               tp1_price, take_profit, stop_loss, status
        FROM signals
        WHERE 1=1
    """
    params = []
    if pair:
        query += " AND pair = ?"
        params.append(pair.upper())
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    signals = conn.execute(query, params).fetchall()

    if not signals:
        print("No signals found")
        return {}

    print(f"Analyzing {len(signals)} signals...")

    # Collect stats per pair
    pair_stats: Dict[str, List[Dict]] = {}

    for i, sig in enumerate(signals):
        print(f"\rProcessing {i+1}/{len(signals)}...", end="", flush=True)

        pair = sig["pair"]
        if pair not in pair_stats:
            pair_stats[pair] = []

        # Calculate MFE/MAE
        mfe, mae = calculate_mfe_mae(
            conn=conn,
            signal_id=sig["signal_id"],
            entry_price=float(sig["entry_market"]),
            direction=sig["direction"],
            entry_time=sig["created_at"],
            exit_time=None,  # Use current time for open signals
            pair=pair,
        )

        if mfe is not None and mae is not None:
            pair_stats[pair].append({
                "signal_id": sig["signal_id"],
                "direction": sig["direction"],
                "mfe_pct": mfe,
                "mae_pct": mae,
                "mfe_mae_ratio": mfe / mae if mae > 0 else 0,
                "tp1_hit": mfe >= ((sig["tp1_price"] - sig["entry_market"]) / sig["entry_market"] * 100) if sig["tp1_price"] else None,
            })

    print("\n")

    conn.close()

    # Aggregate statistics
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_signals": len(signals),
        "pairs_analyzed": len(pair_stats),
        "pairs": {},
    }

    for pair, stats in pair_stats.items():
        if not stats:
            continue

        mfe_values = [s["mfe_pct"] for s in stats if s["mfe_pct"] is not None]
        mae_values = [s["mae_pct"] for s in stats if s["mae_pct"] is not None]
        ratio_values = [s["mfe_mae_ratio"] for s in stats if s["mfe_mae_ratio"] is not None]

        # Calculate percentiles for TP1 optimization
        mfe_sorted = sorted(mfe_values)
        p50_idx = int(len(mfe_sorted) * 0.5)
        p75_idx = int(len(mfe_sorted) * 0.75)
        p90_idx = int(len(mfe_sorted) * 0.90)

        results["pairs"][pair] = {
            "signals_count": len(stats),
            "avg_mfe_pct": sum(mfe_values) / len(mfe_values) if mfe_values else 0,
            "avg_mae_pct": sum(mae_values) / len(mae_values) if mae_values else 0,
            "avg_mfe_mae_ratio": sum(ratio_values) / len(ratio_values) if ratio_values else 0,
            "median_mfe_pct": mfe_sorted[p50_idx] if mfe_sorted else 0,
            "p75_mfe_pct": mfe_sorted[p75_idx] if mfe_sorted else 0,
            "p90_mfe_pct": mfe_sorted[p90_idx] if mfe_sorted else 0,
            "min_mfe_pct": min(mfe_values) if mfe_values else 0,
            "max_mfe_pct": max(mfe_values) if mfe_values else 0,
            # Recommendations
            "recommended_tp1_pct": mfe_sorted[p50_idx] * 0.8 if mfe_sorted else 0.7,  # 80% of median MFE
            "recommended_sl_pct": max(mae_values) * 1.2 if mae_values else 0.45,  # 120% of max MAE
            "recommended_tp2_pct": mfe_sorted[p75_idx] * 1.1 if mfe_sorted else 1.1,  # 110% of p75 MFE
        }

    # Overall recommendations
    all_mfe = [s["mfe_pct"] for stats in pair_stats.values() for s in stats if s["mfe_pct"] is not None]
    all_mae = [s["mae_pct"] for stats in pair_stats.values() for s in stats if s["mae_pct"] is not None]

    if all_mfe and all_mae:
        mfe_sorted = sorted(all_mfe)
        p50_idx = int(len(mfe_sorted) * 0.5)
        p75_idx = int(len(mfe_sorted) * 0.75)

        results["overall_recommendations"] = {
            "avg_mfe_pct": sum(all_mfe) / len(all_mfe),
            "avg_mae_pct": sum(all_mae) / len(all_mae),
            "median_mfe_pct": mfe_sorted[p50_idx],
            "p75_mfe_pct": mfe_sorted[p75_idx],
            # Final config recommendations
            "quiet_tp1_pct": mfe_sorted[p50_idx] * 0.8,  # 80% of median
            "quiet_tp_max_pct": mfe_sorted[p75_idx] * 1.1,  # 110% of p75
            "quiet_sl_atr_mult": 0.8,  # Based on MAE analysis
            "quiet_timeout_candles": 40,
        }

    return results


def print_recommendations(results: Dict[str, Any]):
    """Print configuration recommendations."""
    print("\n" + "="*70)
    print("MFE/MAE STATISTICS & RECOMMENDATIONS")
    print("="*70)

    print(f"\nTotal signals analyzed: {results['total_signals']}")
    print(f"Pairs analyzed: {results['pairs_analyzed']}")

    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│ PER-PAIR STATISTICS                                           │")
    print("├─────────────────────────────────────────────────────────────────┤")

    for pair, stats in results["pairs"].items():
        print(f"\n│ {pair:<8} ({stats['signals_count']} signals)")
        print(f"│   Avg MFE:      {stats['avg_mfe_pct']:.2f}%")
        print(f"│   Avg MAE:      {stats['avg_mae_pct']:.2f}%")
        print(f"│   MFE/MAE:      {stats['avg_mfe_mae_ratio']:.2f}")
        print(f"│   Median MFE:   {stats['median_mfe_pct']:.2f}%")
        print(f"│   P75 MFE:      {stats['p75_mfe_pct']:.2f}%")
        print(f"│   P90 MFE:      {stats['p90_mfe_pct']:.2f}%")
        print(f"│")
        print(f"│   → Recommended TP1:  {stats['recommended_tp1_pct']:.2f}%")
        print(f"│   → Recommended TP2:  {stats['recommended_tp2_pct']:.2f}%")
        print(f"│   → Recommended SL:   {stats['recommended_sl_pct']:.2f}%")

    if "overall_recommendations" in results:
        rec = results["overall_recommendations"]
        print("\n┌─────────────────────────────────────────────────────────────────┐")
        print("│ OVERALL RECOMMENDATIONS (config/settings.py)                  │")
        print("├─────────────────────────────────────────────────────────────────┤")
        print(f"│")
        print(f"│ # TP1: Fixed distance based on MFE (not SL-dependent)")
        print(f"│ quiet_tp1_pct = {rec['quiet_tp1_pct']:.4f}  # {rec['quiet_tp1_pct']*100:.2f}%")
        print(f"│ normal_tp1_pct = {rec['quiet_tp1_pct']*1.3:.4f}  # {rec['quiet_tp1_pct']*1.3*100:.2f}%")
        print(f"│")
        print(f"│ # TP2: Realistic target")
        print(f"│ quiet_tp_max_pct = {rec['quiet_tp_max_pct']:.4f}  # {rec['quiet_tp_max_pct']*100:.2f}%")
        print(f"│ normal_tp_max_pct = {rec['quiet_tp_max_pct']*1.3:.4f}  # {rec['quiet_tp_max_pct']*1.3*100:.2f}%")
        print(f"│")
        print(f"│ # SL: Wide enough to avoid noise")
        print(f"│ quiet_sl_atr_mult = {rec['quiet_sl_atr_mult']}  # 0.8×ATR")
        print(f"│ normal_sl_atr_mult = 0.6  # 0.6×ATR")
        print(f"│")
        print(f"│ # Timeout: More time for TP")
        print(f"│ quiet_timeout_candles = {rec['quiet_timeout_candles']}  # {rec['quiet_timeout_candles']//4} hours")
        print(f"│ normal_timeout_candles = 30  # 7.5 hours")
        print(f"│")
        print(f"└─────────────────────────────────────────────────────────────────┘")

    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(description="Collect MFE/MAE statistics")
    parser.add_argument("--db", default="data/signals.db", help="Database path")
    parser.add_argument("--limit", type=int, default=100, help="Limit signals")
    parser.add_argument("--pair", default=None, help="Filter by pair")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    results = collect_statistics(
        db_path=str(db_path),
        limit=args.limit,
        pair=args.pair,
    )

    if not results:
        print("No results to display")
        sys.exit(1)

    # Print recommendations
    print_recommendations(results)

    # Save to file
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
