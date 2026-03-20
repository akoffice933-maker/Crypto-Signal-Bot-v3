"""
Centralised candle loading.
Converts raw Binance kline lists into typed DataFrames.
Handles the lookback requirements per timeframe:
    1D  → 90 candles (≈ 90 days)
    4H  → 540 candles (≈ 90 days)
    1H  → 168 candles (7 days)
    15m → 200 candles (~2 days, enough for indicators)
"""

import logging
from typing import Dict

import pandas as pd

from data.binance_client import BinanceFuturesClient, KLINE_COLS

logger = logging.getLogger(__name__)

# How many candles to fetch per timeframe
LIMITS: Dict[str, int] = {
    "1d":  90,
    "4h":  540,
    "1h":  168,
    "15m": 200,
}


def _parse(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=KLINE_COLS)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.reset_index(drop=True)


async def load_candles(
    client: BinanceFuturesClient,
    symbol: str,
    timeframes: list[str],
) -> Dict[str, pd.DataFrame]:
    """
    Fetch and parse candles for multiple timeframes in parallel.
    Returns {timeframe: DataFrame}.
    """
    import asyncio

    async def fetch_one(tf: str) -> tuple[str, pd.DataFrame]:
        limit = LIMITS.get(tf, 200)
        raw   = await client.get_klines(symbol, tf, limit=limit)
        return tf, _parse(raw)

    results = await asyncio.gather(*[fetch_one(tf) for tf in timeframes])
    dfs = dict(results)
    for tf, df in dfs.items():
        logger.debug(f"Loaded {len(df)} {tf} candles for {symbol}")
    return dfs
