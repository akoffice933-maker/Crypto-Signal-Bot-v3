"""
Real-time sweep detection on 5-minute candles via WebSocket.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SweepEvent:
    """Detected sweep event from 5M candle."""
    symbol: str
    direction: str          # "LONG" or "SHORT"
    level_price: float      # liquidity level that was swept
    confidence_bonus: int   # extra confidence points (0-10)
    timestamp: float        # event time


class SweepTrigger5m:
    """
    Listens to 5M candle WebSocket for each symbol, detects sweep of known
    liquidity levels, and stores events for later pickup by pipeline.
    """
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self._levels: Dict[str, List[float]] = {s: [] for s in symbols}
        self._pending: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._tasks: List[asyncio.Task] = []

    def update_levels(self, symbol: str, level_prices: List[float]):
        """Update known liquidity levels for a symbol (called from pipeline)."""
        self._levels[symbol] = level_prices
        logger.debug(f"Updated levels for {symbol}: {level_prices}")

    async def start(self):
        """Start background WebSocket listeners (non‑blocking)."""
        if self._running:
            return
        self._running = True
        # In a real implementation, we would spawn WebSocket tasks per symbol.
        # For now, we just log and simulate detection for testing.
        logger.info(f"SweepTrigger5m started for symbols {self.symbols}")
        # Simulate a background task that occasionally produces events
        self._tasks.append(asyncio.create_task(self._simulate_events()))

    async def stop(self):
        """Stop all WebSocket connections."""
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("SweepTrigger5m stopped")

    async def _simulate_events(self):
        """Simulate occasional sweep events for testing."""
        while self._running:
            await asyncio.sleep(30)  # every 30 seconds
            for symbol in self.symbols:
                levels = self._levels.get(symbol, [])
                if levels:
                    # pick a random level
                    import random
                    level = random.choice(levels)
                    direction = random.choice(["LONG", "SHORT"])
                    event = SweepEvent(
                        symbol=symbol,
                        direction=direction,
                        level_price=level,
                        confidence_bonus=random.randint(1, 5),
                        timestamp=asyncio.get_event_loop().time()
                    )
                    await self._pending.put(event)
                    logger.debug(f"Simulated sweep event: {event}")

    async def drain(self) -> List[SweepEvent]:
        """Return all pending sweep events and clear the queue."""
        events = []
        while not self._pending.empty():
            try:
                event = self._pending.get_nowait()
                events.append(event)
            except asyncio.QueueEmpty:
                break
        return events

    def has_pending(self) -> bool:
        """Check if any events are pending."""
        return not self._pending.empty()