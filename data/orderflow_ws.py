"""
WebSocket client for Binance Futures aggTrade stream.

CVD = Cumulative Volume Delta = taker_buy_vol − taker_sell_vol
    m=False (maker=seller) → taker BOUGHT  → +delta
    m=True  (maker=buyer)  → taker SOLD    → -delta

CVD resets at the start of each session:
    Asian:  00:00 UTC
    London: 07:00 UTC   (overlap 07-08 → London CVD starts fresh)
    NY:     13:00 UTC
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import websockets

from config.settings import settings

logger = logging.getLogger(__name__)


def _current_session_key() -> tuple[str, str]:
    """
    Returns (session_name, bucket_key) for the current UTC moment.
    bucket_key = 'SESSION_YYYY-MM-DD' so CVD resets each calendar day per session.
    Priority: london > ny > asian (handles 07-08 overlap correctly).
    """
    now = datetime.now(timezone.utc)
    session = settings.get_session(now.hour)
    if session is None:
        # Between sessions — attribute to upcoming or last, using closest start
        session = "asian"   # fallback; trades between sessions are rare
    date_str = now.strftime("%Y-%m-%d")
    return session, f"{session}_{date_str}"


class OrderFlowWebSocket:
    """Real-time CVD accumulator with session-aware resets."""

    RECONNECT_DELAY = 10

    def __init__(self, symbol: str = "btcusdt"):
        self.symbol   = symbol.lower()
        self._running = False
        self._ws      = None
        self._connected = False

        # {bucket_key: cumulative_delta}  — resets when bucket_key changes
        self._cvd: dict[str, float] = defaultdict(float)
        self._last_price: float = 0.0
        self._trade_count: int  = 0

        # Price buffer: [(timestamp_ms, price)] for divergence calc
        self._price_buf: list[tuple[int, float]] = []

    @property
    def ws_url(self) -> str:
        return f"{settings.ws_base}/ws/{self.symbol}@aggTrade"

    # ── Lifecycle ─────────────────────────────────────────────

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                self._connected = False
                logger.error(f"WS error: {e} — reconnect in {self.RECONNECT_DELAY}s")
                await asyncio.sleep(self.RECONNECT_DELAY)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _connect(self):
        async with websockets.connect(
            self.ws_url, ping_interval=20, ping_timeout=10, max_size=10**6
        ) as ws:
            self._ws = ws
            self._connected = True
            logger.info(f"✓ WS connected: {self.ws_url}")
            async for msg in ws:
                if not self._running:
                    break
                try:
                    await self._on_trade(json.loads(msg))
                except (KeyError, ValueError):
                    pass

    # ── Trade processing ──────────────────────────────────────

    async def _on_trade(self, t: dict):
        price    = float(t["p"])
        qty      = float(t["q"])
        ts_ms    = int(t["T"])
        is_maker_buyer = t["m"]           # True → taker sold

        delta = -qty if is_maker_buyer else qty
        self._last_price = price

        session, bucket = _current_session_key()
        self._cvd[bucket] += delta

        # Keep rolling price buffer (last 60 trades)
        self._price_buf.append((ts_ms, price))
        if len(self._price_buf) > 60:
            self._price_buf.pop(0)

        self._trade_count += 1
        if self._trade_count % 500 == 0:
            self._cleanup_old_buckets()

    def _cleanup_old_buckets(self):
        """Keep only today's session buckets."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        to_del = [k for k in self._cvd if today not in k]
        for k in to_del:
            del self._cvd[k]
        if to_del:
            logger.debug(f"CVD cleanup: removed {len(to_del)} old buckets")

    # ── Public API ────────────────────────────────────────────

    def current_cvd(self) -> float:
        """CVD accumulated in the current session since its start."""
        _, bucket = _current_session_key()
        return self._cvd.get(bucket, 0.0)

    def cvd_divergence(self) -> Optional[str]:
        """
        Classical CVD divergence vs price over recent price buffer.
        Needs at least 20 price points.
        Returns 'bullish' | 'bearish' | None
        """
        buf = self._price_buf
        if len(buf) < 20:
            return None

        mid = len(buf) // 2
        early_price = sum(p for _, p in buf[:mid]) / mid
        late_price  = sum(p for _, p in buf[mid:]) / (len(buf) - mid)

        # Approximate CVD trend: use current vs half-session CVD
        # (full implementation would require binned history)
        cvd_now  = self.current_cvd()
        cvd_sign = 1 if cvd_now >= 0 else -1

        price_down = late_price < early_price * 0.9995
        price_up   = late_price > early_price * 1.0005

        if price_down and cvd_sign > 0:
            return "bullish"    # price LL, CVD HL
        if price_up and cvd_sign < 0:
            return "bearish"    # price HH, CVD LH
        return None

    @property
    def last_price(self) -> float:
        return self._last_price

    @property
    def is_connected(self) -> bool:
        return self._connected
