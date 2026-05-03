"""
Active Signals Monitor — отслеживает активные сигналы и отправляет уведомления
о достижении TP1, TP2, SL.

Запускается как отдельный сервис параллельно с основным ботом.

Usage:
    python scripts/active_signals_monitor.py
    python scripts/active_signals_monitor.py --interval 60  # проверять каждые 60 сек
"""

import aiohttp
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
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
        self.check_interval: int = 60  # секунды
        self.last_check: Dict[str, str] = {}  # last triggered levels per signal
        self.telegram_token: str = settings.telegram_token
        self.chat_id: str = settings.telegram_chat_id

    async def start(self):
        """Инициализация компонентов."""
        logger.info("🔍 Starting Active Signals Monitor...")

        self.db = Database(settings.db_path)
        await self.db.connect()
        logger.info("✓ Database connected")

        self.client = BinanceFuturesClient(settings.base_url)
        logger.info("✓ Binance client created")

        logger.info("✅ Active Signals Monitor ready")

    async def stop(self):
        """Остановка компонентов."""
        logger.info("Stopping Active Signals Monitor...")

        if self.client:
            await self.client.close()
        if self.db:
            await self.db.close()

        logger.info("✅ Active Signals Monitor stopped")

    async def get_active_signals(self) -> List[Dict]:
        """Получить активные сигналы из БД."""
        rows = await self.db._fetch("""
            SELECT signal_id, pair, strategy, direction, entry_market,
                   tp1_price, take_profit, stop_loss, tp1_size_pct, final_tp_size_pct,
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
                "final_tp_size_pct": float(row[9]) if row[9] else None,
                "status": row[10],
                "created_at": row[11],
            })

        return signals

    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Получить текущую цену с Binance."""
        try:
            ticker = await self.client.get_ticker_price(symbol)
            return float(ticker.get("price", 0))
        except Exception as e:
            logger.debug(f"Failed to get price for {symbol}: {e}")
            return None

    def check_price_levels(self, signal: Dict, current_price: float) -> List[str]:
        """
        Проверить достигла ли цена каких-либо уровней.
        Возвращает список достигнутых уровней.
        """
        triggered = []
        direction = signal["direction"]
        signal_id = signal["signal_id"]
        already_triggered = self.last_check.get(signal_id, "")

        # Проверка SL
        if signal["sl_price"]:
            if direction == "LONG" and current_price <= signal["sl_price"]:
                if "sl" not in already_triggered:
                    triggered.append("sl")
            elif direction == "SHORT" and current_price >= signal["sl_price"]:
                if "sl" not in already_triggered:
                    triggered.append("sl")

        # Проверка TP1
        if signal["tp1_price"]:
            if direction == "LONG" and current_price >= signal["tp1_price"]:
                if "tp1" not in already_triggered:
                    triggered.append("tp1")
            elif direction == "SHORT" and current_price <= signal["tp1_price"]:
                if "tp1" not in already_triggered:
                    triggered.append("tp1")

        # Проверка TP2 (полный TP)
        if signal["tp2_price"]:
            if direction == "LONG" and current_price >= signal["tp2_price"]:
                if "tp2" not in already_triggered:
                    triggered.append("tp2")
            elif direction == "SHORT" and current_price <= signal["tp2_price"]:
                if "tp2" not in already_triggered:
                    triggered.append("tp2")

        return triggered

    def calculate_pnl(self, signal: Dict, current_price: float) -> float:
        """Рассчитать текущий PnL в процентах."""
        entry = signal["entry_price"]
        direction = signal["direction"]

        if direction == "LONG":
            pnl = (current_price - entry) / entry * 100
        else:  # SHORT
            pnl = (entry - current_price) / entry * 100

        return pnl

    async def send_telegram_message(self, message: str):
        """Отправить сообщение в Telegram через Bot API."""
        if not self.telegram_token or not self.chat_id:
            logger.warning("Telegram not configured")
            return

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

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
        """Отправить уведомление в Telegram."""
        pnl = self.calculate_pnl(signal, current_price)
        pnl_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"

        # Форматирование сообщения
        level_emoji = {
            "tp1": "🎯",
            "tp2": "🎉",
            "sl": "🛑",
        }.get(level, "📍")

        level_name = {
            "tp1": "TP1 (Partial)",
            "tp2": "TP2 (Full)",
            "sl": "Stop Loss",
        }.get(level, level)

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
        """Обновить статус сигнала в БД."""
        if level == "sl":
            await self.db._execute("""
                UPDATE signals
                SET status = 'sl_hit',
                    result_pnl_pct = (
                        CASE
                            WHEN direction = 'LONG' THEN (price - entry_market) / entry_market * 100
                            ELSE (entry_market - price) / entry_market * 100
                        END
                    ),
                    closed_at = CURRENT_TIMESTAMP
                WHERE signal_id = ?
            """, (price, signal_id))

        elif level == "tp2":
            await self.db._execute("""
                UPDATE signals
                SET status = 'tp_hit',
                    result_pnl_pct = (
                        CASE
                            WHEN direction = 'LONG' THEN (price - entry_market) / entry_market * 100
                            ELSE (entry_market - price) / entry_market * 100
                        END
                    ),
                    closed_at = CURRENT_TIMESTAMP
                WHERE signal_id = ?
            """, (price, signal_id))

        elif level == "tp1":
            # TP1 — частичное закрытие, статус не меняем
            logger.info(f"TP1 hit for {signal_id}, partial close")

        logger.info(f"Updated signal {signal_id} status: {level}")

    async def check_signals(self):
        """Проверить все активные сигналы."""
        signals = await self.get_active_signals()

        if not signals:
            logger.debug("No active signals")
            return

        logger.info(f"Checking {len(signals)} active signals...")

        for signal in signals:
            # Получить текущую цену
            current_price = await self.get_current_price(signal["pair"])
            if not current_price:
                continue

            # Проверить уровни
            triggered = self.check_price_levels(signal, current_price)

            for level in triggered:
                # Отправить уведомление
                await self.send_notification(signal, level, current_price)

                # Обновить статус в БД
                await self.update_signal_status(signal["signal_id"], level, current_price)

                # Запомнить что уровень достигнут
                key = signal["signal_id"]
                if key not in self.last_check:
                    self.last_check[key] = ""
                self.last_check[key] += f"{level},"

    async def run_monitoring(self):
        """Основной цикл мониторинга."""
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

    # Настройка логирования
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
