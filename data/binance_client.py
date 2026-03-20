import asyncio
import logging
import time
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

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

    async def get_klines(self, symbol: str, interval: str,
                         limit: int = 200) -> List[List]:
        """Raw kline list — convert to DataFrame in caller."""
        return await self._get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
            weight=5
        )

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

    # ── Ping ──────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            await self._get("/fapi/v1/ping", weight=1)
            return True
        except Exception:
            return False
