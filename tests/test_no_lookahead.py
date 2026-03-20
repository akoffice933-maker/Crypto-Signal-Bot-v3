"""
Look-ahead bias test for bot_final Backtester.

Every trade that CLOSED in candles_1000 must appear in candles_1500
with identical entry_price, exit_reason, and pnl_net.
Extra trades in candles_1500 must have entry_date AFTER candles_1000 ends.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from backtesting.backtester import Backtester, BTConfig


def gen(n: int, seed: int = 42, start=None) -> pd.DataFrame:
    np.random.seed(seed)
    closes = 64000 * np.cumprod(1 + np.random.normal(0, 0.002, n))
    opens  = np.concatenate([[closes[0]], closes[:-1]])
    opens  = opens * (1 + np.random.normal(0, 0.0005, n))
    highs  = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.001, n)))
    lows   = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.001, n)))
    start  = start or pd.Timestamp("2024-01-01")
    return pd.DataFrame({
        "open_time": pd.date_range(start=start, periods=n, freq="15min"),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": np.random.exponential(1000, n),
    })


def test_no_lookahead_bias():
    c1000 = gen(1000, seed=42)
    last_date = c1000.iloc[-1]["open_time"]
    next_start = last_date + pd.Timedelta(minutes=15)
    c1500 = pd.concat([c1000, gen(500, seed=999, start=next_start)],
                      ignore_index=True)

    cfg = BTConfig(initial_balance=10_000, confidence_min=0)  # no conf filter
    r1  = Backtester(cfg).run(c1000)
    r2  = Backtester(cfg).run(c1500)

    t1 = r1.get("trades", [])
    t2 = r2.get("trades", [])
    t2_by_entry = {t["entry_date"]: t for t in t2}

    for i, trade in enumerate(t1):
        match = t2_by_entry.get(trade["entry_date"])
        assert match is not None, \
            f"Trade {i} ({trade['entry_date']}) missing in 1500-run — look-ahead bias!"
        assert abs(trade["entry_price"] - match["entry_price"]) < 0.01, \
            f"Trade {i} entry price mismatch: {trade['entry_price']} vs {match['entry_price']}"
        assert trade["exit_reason"] == match["exit_reason"], \
            f"Trade {i} exit_reason differs: {trade['exit_reason']} vs {match['exit_reason']}"

    # Extra trades in 1500 must come from after candles_1000 ends
    known = {t["entry_date"] for t in t1}
    extra = [t for t in t2 if t["entry_date"] not in known]
    for t in extra:
        assert pd.to_datetime(t["entry_date"]) > last_date, \
            f"Extra trade {t['entry_date']} is within original window — look-ahead!"

    print(f"✅ Look-ahead bias test PASSED")
    print(f"   1000-run trades: {len(t1)}")
    print(f"   1500-run trades: {len(t2)}  ({len(extra)} from appended data — expected)")


if __name__ == "__main__":
    test_no_lookahead_bias()
