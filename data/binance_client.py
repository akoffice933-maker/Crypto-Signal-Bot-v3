import asyncio
import logging
import time
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

# Candle column names for easy DataFrame construction
KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_vol", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore"
]


class BinanceFuturesClient:
    """
    Async Binance Futures REST client.
    Handles rate limits, exponential backoff, and session lifecycle.
    """

    def __init__(self, base_url: str = "https://fapi.binance.com"):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._weight_used: int = 0
        self._weight_reset_at: float = time.time() + 60
        self._WEIGHT_LIMIT: int = 1200

    # ── Session ───────────────────────────────────────────────

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ── Core request ──────────────────────────────────────────

    async def _get(self, endpoint: str, params: Dict = None,
                   weight: int = 1) -> any:
        now = time.time()
        if now > self._weight_reset_at:
            self._weight_used = 0
            self._weight_reset_at = now + 60
        if self._weight_used + weight > self._WEIGHT_LIMIT:
            wait = self._weight_reset_at - now
            logger.warning(f"Rate limit: waiting {wait:.1f}s")
            await asyncio.sleep(wait)

        url = f"{self.base_url}{endpoint}"
        session = await self._sess()

        for attempt in range(4):
            try:
                async with session.get(url, params=params) as r:
                    self._weight_used += weight
                    if r.status == 429:
                        delay = int(r.headers.get("Retry-After", 60))
                        logger.warning(f"429 — sleeping {delay}s")
                        await asyncio.sleep(delay)
                        continue
                    r.raise_for_status()
                    return await r.json()
            except aiohttp.ClientError as e:
                if attempt < 3:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise RuntimeError(f"Binance request failed: {e}") from e

    # ── Klines ────────────────────────────────────────────────

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        """Raw kline list — convert to DataFrame in caller."""
        params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1500)}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return await self._get("/fapi/v1/klines", params, weight=5)

    async def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        total_limit: int,
    ) -> List[List]:
        """Fetch more than 1500 candles by paging backwards with endTime."""
        if total_limit <= 0:
            return []
        interval_ms = _INTERVAL_MS.get(interval)
        if interval_ms is None:
            raise ValueError(f"Unsupported interval for historical klines: {interval}")

        collected: List[List] = []
        end_time: Optional[int] = None
        remaining = total_limit

        while remaining > 0:
            batch_limit = min(remaining, 1500)
            batch = await self.get_klines(
                symbol=symbol,
                interval=interval,
                limit=batch_limit,
                end_time=end_time,
            )
            if not batch:
                break

            collected = batch + collected
            remaining -= len(batch)

            if len(batch) < batch_limit:
                break

            first_open_time = int(batch[0][0])
            end_time = first_open_time - 1

            # Back off a little for large historical pulls.
            await asyncio.sleep(0.05)

        # Deduplicate by open_time and keep the most recent candles.
        deduped = {int(row[0]): row for row in collected}
        rows = [deduped[k] for k in sorted(deduped.keys())]
        return rows[-total_limit:]

    # ── Open Interest ─────────────────────────────────────────

    async def get_open_interest(self, symbol: str) -> Dict:
        return await self._get(
            "/fapi/v1/openInterest", {"symbol": symbol}, weight=1
        )

    # ── Funding rate ──────────────────────────────────────────

    async def get_premium_index(self, symbol: str) -> Dict:
        """Returns markPrice, indexPrice, lastFundingRate, nextFundingTime."""
        return await self._get(
            "/fapi/v1/premiumIndex", {"symbol": symbol}, weight=1
        )

    async def get_ticker_price(self, symbol: str) -> Dict:
        """Get current price for a symbol."""
        return await self._get(
            "/fapi/v1/ticker/price", {"symbol": symbol}, weight=1
        )

    # ── Ping ──────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            await self._get("/fapi/v1/ping", weight=1)
            return True
        except Exception:
            return False
