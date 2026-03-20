"""
Liquidity level validator.
Compares levels stored in DB against levels detected on fresh candles.
Reports match-rate — useful after 4+ hours of forward testing.

Usage:
    python scripts/validate_levels.py
    python scripts/validate_levels.py --hours 4 --min-strength 3
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import settings
from data.binance_client import BinanceFuturesClient, KLINE_COLS
from database.db import Database
from engine.liquidity_map import detect_levels


async def validate(hours: int = 4, min_strength: float = 3.0) -> dict:
    db = Database(settings.db_path)
    await db.connect()

    client = BinanceFuturesClient(settings.base_url)

    # Load DB levels
    db_rows = await db._fetch(
        "SELECT timeframe, pool_type, price FROM liquidity_pools "
        "WHERE is_active=1 AND strength>=? ORDER BY strength DESC",
        (min_strength,)
    )
    db_levels = [{"tf": r[0], "type": r[1], "price": r[2]} for r in (db_rows or [])]

    # Fetch fresh candles
    raw_1d = await client.get_klines(settings.symbol, "1d", limit=90)
    raw_4h = await client.get_klines(settings.symbol, "4h", limit=100)

    def parse(raw):
        df = pd.DataFrame(raw, columns=KLINE_COLS)
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = df[c].astype(float)
        return df

    df_1d = parse(raw_1d)
    df_4h = parse(raw_4h)
    current_price = float(df_1d["close"].iloc[-1])

    detected_1d = detect_levels(df_1d, "1d", current_price, min_touches=3)
    detected_4h = detect_levels(df_4h, "4h", current_price, min_touches=3)
    detected     = detected_1d + detected_4h
    det_prices   = [lv.price for lv in detected]

    # Match: within 0.3%
    tol = 0.003
    matches = 0
    for db_lv in db_levels:
        if any(abs(db_lv["price"] - dp) / db_lv["price"] <= tol for dp in det_prices):
            matches += 1

    match_rate = matches / len(db_levels) * 100 if db_levels else 100.0

    # Missed: detected but not in DB
    db_prices = [lv["price"] for lv in db_levels]
    missed = [dp for dp in det_prices
              if not any(abs(dp - dbp) / max(dp, 1) <= tol for dbp in db_prices)]
    extra  = [dbp for dbp in db_prices
              if not any(abs(dbp - dp) / max(dbp, 1) <= tol for dp in det_prices)]

    await db.close()
    await client.close()

    return {
        "match_rate":       round(match_rate, 1),
        "db_levels":        len(db_levels),
        "detected_levels":  len(detected),
        "matches":          matches,
        "missed_from_db":   missed[:10],
        "extra_in_db":      extra[:10],
        "current_price":    current_price,
        "timestamp":        datetime.now().isoformat(),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours",       type=int,   default=4)
    parser.add_argument("--min-strength",type=float, default=3.0)
    args = parser.parse_args()

    print(f"🔍 Validating levels (min_strength={args.min_strength})...")
    r = await validate(args.hours, args.min_strength)

    print(f"\n📊 Results  (price={r['current_price']:.2f})")
    print(f"   Match rate:       {r['match_rate']:.1f}%")
    print(f"   DB levels:        {r['db_levels']}")
    print(f"   Detected fresh:   {r['detected_levels']}")
    print(f"   Matches:          {r['matches']}")

    if r["missed_from_db"]:
        print(f"\n⚠️  In fresh detect, not in DB: {[round(p,2) for p in r['missed_from_db'][:5]]}")
    if r["extra_in_db"]:
        print(f"ℹ️  In DB, not in fresh detect: {[round(p,2) for p in r['extra_in_db'][:5]]}")

    if r["match_rate"] >= 75:
        print("\n✅ Quality: GOOD")
    elif r["match_rate"] >= 55:
        print("\n🟡 Quality: ACCEPTABLE — consider tuning min_strength")
    else:
        print("\n🔴 Quality: NEEDS TUNING")
        print("   • Too many DB levels? ↑ min_strength")
        print("   • Missing levels?    ↓ min_strength or ↑ lookback")


if __name__ == "__main__":
    asyncio.run(main())
