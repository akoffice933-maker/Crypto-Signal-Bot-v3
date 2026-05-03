"""
Trade manager for tracking signal‑based positions, calculating SL/TP,
and sending Telegram alerts when levels are reached.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class TradeLevels:
    """Price levels for a tracked trade."""
    entry: float
    sl: float
    tp1: float
    tp2: float


@dataclass
class ManagedTrade:
    """A trade being tracked by the manager."""
    symbol: str
    direction: Direction
    strategy: str
    levels: TradeLevels
    opened_at: datetime
    expires_at: datetime
    tp1_triggered: bool = False
    tp2_triggered: bool = False
    sl_triggered: bool = False
    expired: bool = False

    def to_telegram_open(self) -> str:
        """Format opening message for Telegram."""
        emoji = "🟢" if self.direction == Direction.LONG else "🔴"
        return (
            f"{emoji} *ТРЕЙД ОТКРЫТ*\n"
            f"*{self.symbol}* {self.strategy}\n"
            f"Направление: {self.direction.value}\n"
            f"Вход: `{self.levels.entry}`\n"
            f"SL: `{self.levels.sl}`\n"
            f"TP1: `{self.levels.tp1}`\n"
            f"TP2: `{self.levels.tp2}`\n"
            f"Истекает: {self.expires_at.strftime('%H:%M UTC')}"
        )

    def to_telegram_update(self, level_hit: str) -> str:
        """Format update message for Telegram."""
        emoji = "✅" if "TP" in level_hit else "❌"
        return (
            f"{emoji} *ТРЕЙД ОБНОВЛЁН*\n"
            f"*{self.symbol}* {self.strategy}\n"
            f"Достигнут уровень: {level_hit}\n"
            f"Вход: `{self.levels.entry}`\n"
            f"Текущий статус: "
            f"TP1 {'✅' if self.tp1_triggered else '⏳'}, "
            f"TP2 {'✅' if self.tp2_triggered else '⏳'}, "
            f"SL {'✅' if self.sl_triggered else '⏳'}"
        )


class TradeManager:
    """
    In‑memory trade tracker.
    """
    def __init__(self, notifier=None, expiry_hours: int = 4):
        self.notifier = notifier
        self.expiry_hours = expiry_hours
        self.active_trades: Dict[str, ManagedTrade] = {}  # key: symbol
        self.closed_trades: List[ManagedTrade] = []
        self.stats = {
            "total": 0,
            "wins_full": 0,
            "wins_partial": 0,
            "losses": 0,
            "expired": 0,
        }

    def open_trade(self, signal: Dict, current_atr: float) -> Optional[ManagedTrade]:
        """
        Create a tracked trade from a signal dictionary.
        Expects signal to contain:
          - symbol, direction, strategy, entry_market, swept_level, confidence_score, atr
        """
        symbol = signal.get("symbol")
        if not symbol:
            logger.error("Signal missing symbol, cannot open trade")
            return None
        if symbol in self.active_trades:
            logger.warning(f"Trade for {symbol} already active, skipping")
            return None

        direction = Direction(signal["direction"].upper())
        entry = signal.get("entry_market")
        if entry is None:
            logger.error("Signal missing entry_market")
            return None

        # Calculate SL/TP based on ATR (simplified)
        atr = current_atr
        if direction == Direction.LONG:
            sl = entry - atr * 1.5
            tp1 = entry + atr * 1.0
            tp2 = entry + atr * 2.0
        else:
            sl = entry + atr * 1.5
            tp1 = entry - atr * 1.0
            tp2 = entry - atr * 2.0

        levels = TradeLevels(entry=entry, sl=sl, tp1=tp1, tp2=tp2)
        opened_at = datetime.now(timezone.utc)
        expires_at = opened_at + timedelta(hours=self.expiry_hours)

        trade = ManagedTrade(
            symbol=symbol,
            direction=direction,
            strategy=signal.get("strategy", "unknown"),
            levels=levels,
            opened_at=opened_at,
            expires_at=expires_at,
        )
        self.active_trades[symbol] = trade
        self.stats["total"] += 1
        logger.info(f"Trade opened for {symbol} {direction.value} entry={entry}")
        return trade

    async def tick(self, symbol: str, high: float, low: float, close: float):
        """
        Check price levels for a symbol and trigger updates.
        Should be called periodically (e.g., every 5 minutes).
        """
        trade = self.active_trades.get(symbol)
        if not trade:
            return

        # Check expiration
        now = datetime.now(timezone.utc)
        if now >= trade.expires_at and not trade.expired:
            trade.expired = True
            self._close_trade(trade, "EXPIRED")
            if self.notifier:
                await self.notifier.send_text(
                    f"⏰ *ТРЕЙД ИСТЁК*\n*{trade.symbol}* {trade.strategy}\n"
                    f"Время истекло, позиция закрыта."
                )
            return

        # Check SL/TP
        if trade.direction == Direction.LONG:
            if low <= trade.levels.sl and not trade.sl_triggered:
                trade.sl_triggered = True
                self._close_trade(trade, "SL")
                if self.notifier:
                    await self.notifier.send_text(trade.to_telegram_update("SL"))
            elif high >= trade.levels.tp2 and not trade.tp2_triggered:
                trade.tp2_triggered = True
                self._close_trade(trade, "TP2")
                if self.notifier:
                    await self.notifier.send_text(trade.to_telegram_update("TP2"))
            elif high >= trade.levels.tp1 and not trade.tp1_triggered:
                trade.tp1_triggered = True
                if self.notifier:
                    await self.notifier.send_text(trade.to_telegram_update("TP1"))
        else:  # SHORT
            if high >= trade.levels.sl and not trade.sl_triggered:
                trade.sl_triggered = True
                self._close_trade(trade, "SL")
                if self.notifier:
                    await self.notifier.send_text(trade.to_telegram_update("SL"))
            elif low <= trade.levels.tp2 and not trade.tp2_triggered:
                trade.tp2_triggered = True
                self._close_trade(trade, "TP2")
                if self.notifier:
                    await self.notifier.send_text(trade.to_telegram_update("TP2"))
            elif low <= trade.levels.tp1 and not trade.tp1_triggered:
                trade.tp1_triggered = True
                if self.notifier:
                    await self.notifier.send_text(trade.to_telegram_update("TP1"))

    def _close_trade(self, trade: ManagedTrade, reason: str):
        """Move trade from active to closed and update stats."""
        del self.active_trades[trade.symbol]
        self.closed_trades.append(trade)
        if reason == "TP2":
            self.stats["wins_full"] += 1
        elif reason == "TP1":
            self.stats["wins_partial"] += 1
        elif reason == "SL":
            self.stats["losses"] += 1
        elif reason == "EXPIRED":
            self.stats["expired"] += 1
        logger.info(f"Trade closed for {trade.symbol} reason={reason}")

    async def tick_all(self, client) -> None:
        """
        Fetch current prices for all active trades and check SL/TP.
        client must have a get_ticker_price(symbol) method returning dict with 'price'.
        """
        if not self.active_trades:
            return
        
        # Fetch prices for all symbols
        for symbol, trade in list(self.active_trades.items()):
            try:
                ticker = await client.get_ticker_price(symbol)
                price = float(ticker.get("price", 0))
                if price <= 0:
                    logger.warning(f"Invalid price for {symbol}: {price}")
                    continue
                # Use same price for high/low/close (simplified)
                high = price
                low = price
                close = price
                await self.tick(symbol, high, low, close)
            except Exception as e:
                logger.warning(f"Failed to get price for {symbol}: {e}")

    def get_active_trades(self) -> List[ManagedTrade]:
        """Return list of currently active trades."""
        return list(self.active_trades.values())

    def get_stats(self) -> Dict:
        """Return aggregated statistics."""
        total = self.stats["total"]
        wins = self.stats["wins_full"] + self.stats["wins_partial"]
        win_rate_pct = (wins / total * 100) if total > 0 else 0.0
        avg_rr = 2.0  # placeholder, real calculation would need PnL
        return {
            **self.stats,
            "win_rate_pct": round(win_rate_pct, 1),
            "avg_rr": avg_rr,
        }