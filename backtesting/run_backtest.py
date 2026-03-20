"""
Backtest runner for bot_final.

Usage:
    python backtesting/run_backtest.py                  # synthetic data
    python backtesting/run_backtest.py --real           # real Binance data
    python backtesting/run_backtest.py --real --candles 8640  # ~3 months
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtesting.backtester import BTConfig, Backtester
from config.settings import settings


def make_synthetic(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Realistic OHLC: separate open/close, non-zero bodies."""
    np.random.seed(seed)
    closes = 64000 * np.cumprod(1 + np.random.normal(0, 0.002, n))
    opens  = np.concatenate([[closes[0]], closes[:-1]])
    opens  = opens * (1 + np.random.normal(0, 0.0005, n))
    highs  = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.001, n)))
    lows   = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.001, n)))
    return pd.DataFrame({
        "open_time": pd.date_range(start="2024-01-01", periods=n, freq="15min"),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": np.random.exponential(1000, n),
    })


async def fetch_real(symbol: str, candles: int) -> pd.DataFrame:
    from data.binance_client import BinanceFuturesClient, KLINE_COLS
    client = BinanceFuturesClient(settings.base_url)
    raw    = await client.get_klines(symbol, "15m", limit=candles)
    await client.close()
    df = pd.DataFrame(raw, columns=KLINE_COLS)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


def print_results(label: str, r: dict):
    print(f"\n{'='*52}")
    print(f"  {label}")
    print(f"{'='*52}")
    if "error" in r:
        print(f"  ❌ {r['error']}")
        return
    print(f"  Return:        {r['total_return_pct']:+.2f}%")
    print(f"  Profit Factor: {r['profit_factor']:.2f}")
    print(f"  Win Rate:      {r['winrate_pct']:.1f}%")
    print(f"  Max Drawdown:  {r['max_drawdown_pct']:.2f}%")
    print(f"  Trades:        {r['total_trades']}  "
          f"(W:{r['winning_trades']} L:{r['losing_trades']})")
    print(f"  Avg R/R:       {r['avg_rr']:.2f}")
    print(f"  Exit reasons:  {r['exits']}")
    pf = r["profit_factor"]
    n  = r["total_trades"]
    print()
    if n < 15:
        print(f"  ⚠️  Only {n} trades — not statistically significant")
    elif pf >= 1.5:
        print("  ✅ PF ≥ 1.5 — ready for testnet")
    elif pf >= 1.2:
        print("  🟡 PF ≥ 1.2 — marginal, tune parameters")
    else:
        print("  🔴 PF < 1.2 — strategy needs refinement")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real",    action="store_true")
    parser.add_argument("--candles", type=int, default=2000)
    parser.add_argument("--symbol",  default="BTCUSDT")
    args = parser.parse_args()

    if args.real:
        print(f"Fetching {args.candles} × 15m candles for {args.symbol}...")
        df = await fetch_real(args.symbol, args.candles)
    else:
        print(f"Using synthetic candles (n={args.candles})")
        df = make_synthetic(args.candles)

    cfg = BTConfig(
        initial_balance=10_000,
        fee_pct=0.0004,
        slippage_pct=0.0008,
        max_position_pct=0.10,
        min_rr=settings.min_rr,
        confidence_min=settings.confidence_threshold,
        max_candles_hold=20,
    )

    bt      = Backtester(cfg)
    results = bt.run(df)
    print_results(f"{args.symbol} — Sweep Reversal", results)

    os.makedirs("results", exist_ok=True)
    fname = f"results/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Saved to {fname}")


if __name__ == "__main__":
    asyncio.run(main())
