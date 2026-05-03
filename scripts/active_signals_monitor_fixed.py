import aiohttp
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import settings
from database.db import Database
from data.binance_client import BinanceFuturesClient

logger = logging.getLogger(__name__)


class ActiveSignalsMonitor:
    def __init__(self):
        self.db: Optional[Database] = None
        self.client: Optional[BinanceFuturesClient] = None
        self.check_interval: int = 60
        self.last_check: Dict[str, str] = {}
        self.telegram_token: str = settings.telegram_token
        self.chat_id: str = settings.telegram_chat_id

    async def start(self):
        logger.info("🔍 Starting Active Signals Monitor...")
        self.db = Database(settings.db_path)
        await self.db.connect()
        logger.info("✓ Database connected")
        self.client = BinanceFuturesClient(settings.base_url)
        logger.info("✓ Binance client created")
        logger.info("✅ Active Signals Monitor ready")

    async def stop(self):
        logger.info("Stopping Active Signals Monitor...")
        if self.client:
            await self.client.close()
        if self.db:
            await self.db.close()
        logger.info("✅ Active Signals Monitor stopped")

    async def get_active_signals(self) -> List[Dict]:
        rows = await self.db._fetch("""
            SELECT signal_id, pair, strategy, direction, entry_market,
                   tp1_price, take_profit, stop_loss, tp1_size_pct,
                   status, created_at
            FROM signals
            WHERE status IN ('sent', 'partial_tp1')
            ORDER BY created_at DESC
        """)
        signals = []
        for row in rows:
            signals.append({
                "signal_id": row[0],
                "pair": row[1],
                "strategy": row[2],
                "direction": row[3],
                "entry_price": float(row[4]),
                "tp1_price": float(row[5]) if row[5] else None,
                "tp2_price": float(row[6]) if row[6] else None,
                "sl_price": float(row[7]) if row[7] else None,
                "tp1_size_pct": float(row[8]) if row[8] else None,
                "status": row[9],
                "created_at": row[10],
            })
        return signals

    async def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            ticker = await self.client.get_ticker_price(symbol)
            return float(ticker.get("price", 0))
        except Exception as e:
            logger.debug(f"Failed to get price for {symbol}: {e}")
            return None

    def check_price_levels(self, signal: Dict, current_price: float) -> List[str]:
        triggered = []
        direction = signal["direction"]
        signal_id = signal["signal_id"]
        already_triggered = self.last_check.get(signal_id, "")

        if signal["sl_price"]:
            if direction == "LONG" and current_price <= signal["sl_price"]:
                if "sl" not in already_triggered:
                    triggered.append("sl")
            elif direction == "SHORT" and current_price >= signal["sl_price"]:
                if "sl" not in already_triggered:
                    triggered.append("sl")

        if signal["tp1_price"]:
            if direction == "LONG" and current_price >= signal["tp1_price"]:
                if "tp1" not in already_triggered:
                    triggered.append("tp1")
            elif direction == "SHORT" and current_price <= signal["tp1_price"]:
                if "tp1" not in already_triggered:
                    triggered.append("tp1")

        if signal["tp2_price"]:
            if direction == "LONG" and current_price >= signal["tp2_price"]:
                if "tp2" not in already_triggered:
                    triggered.append("tp2")
            elif direction == "SHORT" and current_price <= signal["tp2_price"]:
                if "tp2" not in already_triggered:
                    triggered.append("tp2")

        return triggered

    def calculate_pnl(self, signal: Dict, current_price: float) -> float:
        entry = signal["entry_price"]
        direction = signal["direction"]
        if direction == "LONG":
            pnl = (current_price - entry) / entry * 100
        else:
            pnl = (entry - current_price) / entry * 100
        return pnl

    async def send_telegram_message(self, message: str):
        if not self.telegram_token or not self.chat_id:
            logger.warning("Telegram not configured")
            return
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        data = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info("Telegram message sent")
                    else:
                        logger.error(f"Telegram error: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_notification(self, signal: Dict, level: str, current_price: float):
        pnl = self.calculate_pnl(signal, current_price)
        pnl_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
        level_emoji = {"tp1": "🎯", "tp2": "🎉", "sl": "🛑"}.get(level, "📍")
        level_name = {"tp1": "TP1 (Partial)", "tp2": "TP2 (Full)", "sl": "Stop Loss"}.get(level, level)

        message = f"""
{level_emoji} **{signal['pair']} {signal['direction']} — {level_name}**

Entry:   ${signal['entry_price']:,.2f}
Current: ${current_price:,.2f}
PnL:     {pnl_emoji} **{pnl:+.2f}%**

Strategy: {signal['strategy']}
Signal:   `{signal['signal_id'][:8]}`
"""
        if level == "tp1" and signal["tp1_size_pct"]:
            message += f"\nClosed: {int(signal['tp1_size_pct'] * 100)}% position"

        await self.send_telegram_message(message.strip())
        logger.info(f"Sent notification: {signal['pair']} {signal['direction']} {level}")

    async def update_signal_status(self, signal_id: str, level: str, price: float):
        """Update signal status in database (simplified - no PnL calculation)."""
        if level == "sl":
            await self.db._exec(
                "UPDATE signals SET status = 'sl_hit', closed_at = CURRENT_TIMESTAMP WHERE signal_id = ?",
                (signal_id,)
            )
        elif level == "tp2":
            await self.db._exec(
                "UPDATE signals SET status = 'tp_hit', closed_at = CURRENT_TIMESTAMP WHERE signal_id = ?",
                (signal_id,)
            )
        elif level == "tp1":
            logger.info(f"TP1 hit for {signal_id}, partial close")
        logger.info(f"Updated signal {signal_id} status: {level}")

    async def check_signals(self):
        signals = await self.get_active_signals()
        if not signals:
            logger.debug("No active signals")
            return
        logger.info(f"Checking {len(signals)} active signals...")
        for signal in signals:
            current_price = await self.get_current_price(signal["pair"])
            if not current_price:
                continue
            triggered = self.check_price_levels(signal, current_price)
            for level in triggered:
                await self.send_notification(signal, level, current_price)
                await self.update_signal_status(signal["signal_id"], level, current_price)
                key = signal["signal_id"]
                if key not in self.last_check:
                    self.last_check[key] = ""
                self.last_check[key] += f"{level},"

    async def run_monitoring(self):
        logger.info(f"🔍 Starting monitoring loop (interval: {self.check_interval}s)")
        while True:
            try:
                await self.check_signals()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Active Signals Monitor")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/active_monitor.log", encoding='utf-8'),
        ],
    )

    monitor = ActiveSignalsMonitor()
    monitor.check_interval = args.interval

    try:
        await monitor.start()
        await monitor.run_monitoring()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await monitor.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
