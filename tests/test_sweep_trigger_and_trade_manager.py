"""
Unit tests for sweep_trigger_5m and trade_manager integration.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta

from engine.sweep_trigger_5m import SweepTrigger5m, SweepEvent
from engine.trade_manager import TradeManager, Direction, ManagedTrade, TradeLevels


class TestSweepTrigger5m:
    """Test sweep detection trigger."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        trigger = SweepTrigger5m(symbols=["BTCUSDT", "ETHUSDT"])
        assert trigger.symbols == ["BTCUSDT", "ETHUSDT"]
        assert trigger._levels["BTCUSDT"] == []
        assert trigger._levels["ETHUSDT"] == []

    @pytest.mark.asyncio
    async def test_update_levels(self):
        trigger = SweepTrigger5m(symbols=["BTCUSDT"])
        trigger.update_levels("BTCUSDT", [50000.0, 51000.0])
        assert trigger._levels["BTCUSDT"] == [50000.0, 51000.0]

    @pytest.mark.asyncio
    async def test_start_stop(self):
        trigger = SweepTrigger5m(symbols=["BTCUSDT"])
        await trigger.start()
        assert trigger._running is True
        await trigger.stop()
        assert trigger._running is False

    @pytest.mark.asyncio
    async def test_drain_empty(self):
        trigger = SweepTrigger5m(symbols=["BTCUSDT"])
        events = await trigger.drain()
        assert events == []

    @pytest.mark.asyncio
    async def test_simulated_events(self):
        trigger = SweepTrigger5m(symbols=["BTCUSDT"])
        trigger.update_levels("BTCUSDT", [50000.0])
        await trigger.start()
        # Wait a bit for simulation to produce an event
        await asyncio.sleep(0.1)
        events = await trigger.drain()
        # Might be empty if simulation hasn't produced yet, but at least no error
        await trigger.stop()


class TestTradeManager:
    """Test trade tracking and level checking."""

    def test_trade_creation(self):
        mgr = TradeManager()
        signal = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "strategy": "sweep_reversal",
            "entry_market": 50000.0,
            "atr": 1000.0,
        }
        trade = mgr.open_trade(signal, current_atr=1000.0)
        assert trade is not None
        assert trade.symbol == "BTCUSDT"
        assert trade.direction == Direction.LONG
        assert trade.levels.entry == 50000.0
        assert trade.levels.sl == 50000.0 - 1000.0 * 1.5  # 48500.0
        assert trade.levels.tp1 == 50000.0 + 1000.0 * 1.0  # 51000.0
        assert trade.levels.tp2 == 50000.0 + 1000.0 * 2.0  # 52000.0
        assert trade in mgr.get_active_trades()

    def test_duplicate_symbol_blocked(self):
        mgr = TradeManager()
        signal = {"symbol": "BTCUSDT", "direction": "LONG", "entry_market": 50000.0, "atr": 1000.0}
        trade1 = mgr.open_trade(signal, current_atr=1000.0)
        assert trade1 is not None
        trade2 = mgr.open_trade(signal, current_atr=1000.0)
        assert trade2 is None  # duplicate blocked

    def test_short_trade_levels(self):
        mgr = TradeManager()
        signal = {
            "symbol": "BTCUSDT",
            "direction": "SHORT",
            "entry_market": 50000.0,
            "atr": 1000.0,
        }
        trade = mgr.open_trade(signal, current_atr=1000.0)
        assert trade.direction == Direction.SHORT
        assert trade.levels.sl == 50000.0 + 1000.0 * 1.5  # 51500.0
        assert trade.levels.tp1 == 50000.0 - 1000.0 * 1.0  # 49000.0
        assert trade.levels.tp2 == 50000.0 - 1000.0 * 2.0  # 48000.0

    @pytest.mark.asyncio
    async def test_tick_long_sl_hit(self):
        mgr = TradeManager()
        signal = {"symbol": "BTCUSDT", "direction": "LONG", "entry_market": 50000.0, "atr": 1000.0}
        trade = mgr.open_trade(signal, current_atr=1000.0)
        # SL is at 48500.0, low below SL
        await mgr.tick("BTCUSDT", high=49000.0, low=48400.0, close=48800.0)
        assert trade.sl_triggered is True
        assert "BTCUSDT" not in mgr.active_trades
        assert mgr.stats["losses"] == 1

    @pytest.mark.asyncio
    async def test_tick_long_tp1_hit(self):
        mgr = TradeManager()
        signal = {"symbol": "BTCUSDT", "direction": "LONG", "entry_market": 50000.0, "atr": 1000.0}
        trade = mgr.open_trade(signal, current_atr=1000.0)
        # TP1 is at 51000.0, high above TP1
        await mgr.tick("BTCUSDT", high=51100.0, low=50500.0, close=50900.0)
        assert trade.tp1_triggered is True
        assert trade.tp2_triggered is False
        assert trade.sl_triggered is False
        assert "BTCUSDT" in mgr.active_trades  # trade still active (TP2 not hit)

    @pytest.mark.asyncio
    async def test_tick_long_tp2_hit(self):
        mgr = TradeManager()
        signal = {"symbol": "BTCUSDT", "direction": "LONG", "entry_market": 50000.0, "atr": 1000.0}
        trade = mgr.open_trade(signal, current_atr=1000.0)
        # TP2 is at 52000.0, high above TP2
        await mgr.tick("BTCUSDT", high=52100.0, low=51500.0, close=51900.0)
        assert trade.tp2_triggered is True
        assert "BTCUSDT" not in mgr.active_trades
        assert mgr.stats["wins_full"] == 1

    @pytest.mark.asyncio
    async def test_expiration(self):
        mgr = TradeManager(expiry_hours=0.0001)  # expires in ~0.36 seconds
        signal = {"symbol": "BTCUSDT", "direction": "LONG", "entry_market": 50000.0, "atr": 1000.0}
        trade = mgr.open_trade(signal, current_atr=1000.0)
        # Wait a bit for expiration
        await asyncio.sleep(0.5)
        await mgr.tick("BTCUSDT", high=50500.0, low=49500.0, close=50200.0)
        assert trade.expired is True
        assert "BTCUSDT" not in mgr.active_trades
        assert mgr.stats["expired"] == 1

    def test_get_stats(self):
        mgr = TradeManager()
        # Open a few trades and close them
        signal = {"symbol": "BTCUSDT", "direction": "LONG", "entry_market": 50000.0, "atr": 1000.0}
        trade = mgr.open_trade(signal, current_atr=1000.0)
        mgr._close_trade(trade, "TP2")
        stats = mgr.get_stats()
        assert stats["total"] == 1
        assert stats["wins_full"] == 1
        assert stats["win_rate_pct"] == 100.0