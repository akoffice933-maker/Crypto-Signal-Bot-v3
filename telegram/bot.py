import asyncio
from contextlib import suppress
import logging
import time
from collections import deque

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, Message

from config.settings import settings
from telegram.formatter import format_signal

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._router: Router | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._sent_at: deque[float] = deque()
        self._last_send_at: float = 0.0
        self._worker_task: asyncio.Task | None = None
        self._polling_task: asyncio.Task | None = None

    async def start(self):
        if not settings.telegram_token:
            logger.warning("No Telegram token — notifications disabled")
            return
        self._bot = Bot(token=settings.telegram_token)
        self._dispatcher = Dispatcher()
        self._router = Router()
        self._register_handlers()
        self._dispatcher.include_router(self._router)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="telegram_notifier_worker")
        self._polling_task = asyncio.create_task(
            self._dispatcher.start_polling(self._bot),
            name="telegram_notifier_polling",
        )
        await self._set_commands()
        logger.info("✓ Telegram notifier started")

    async def stop(self):
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._polling_task
            self._polling_task = None
        if self._worker_task:
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        if self._bot:
            await self._bot.session.close()
        self._dispatcher = None
        self._router = None

    async def send_signal(self, signal: dict):
        await self._queue.put(("signal", signal))

    async def send_text(self, text: str):
        await self._queue.put(("text", text))

    async def send_alert(self, text: str):
        await self._queue.put(("alert", text))

    async def _worker(self):
        while self._running:
            try:
                kind, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                if kind == "signal":
                    text = format_signal(payload)
                else:
                    text = payload
                await self._send(text)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Notifier worker error: {e}")

    async def _send(self, text: str, retries: int = 3):
        if not self._bot:
            return
        for attempt in range(retries):
            try:
                await self._throttle()
                await self._bot.send_message(
                    chat_id=settings.telegram_chat_id,
                    text=text,
                    parse_mode="Markdown",
                )
                now = time.monotonic()
                self._last_send_at = now
                self._sent_at.append(now)
                return
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to send after {retries} attempts: {e}")

    async def _throttle(self):
        now = time.monotonic()
        window_start = now - 60
        while self._sent_at and self._sent_at[0] < window_start:
            self._sent_at.popleft()

        min_interval = max(settings.telegram_min_interval_seconds, 0.0)
        if self._last_send_at:
            wait = min_interval - (now - self._last_send_at)
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()

        max_per_minute = max(settings.telegram_max_messages_per_minute, 1)
        while len(self._sent_at) >= max_per_minute:
            wait = 60 - (time.monotonic() - self._sent_at[0])
            if wait > 0:
                logger.warning(f"Telegram rate limit guard active, sleeping {wait:.1f}s")
                await asyncio.sleep(wait)
            now = time.monotonic()
            while self._sent_at and self._sent_at[0] < now - 60:
                self._sent_at.popleft()

    def _register_handlers(self):
        if not self._router:
            return

        @self._router.message(CommandStart())
        async def start_handler(message: Message):
            await message.answer(self._build_start_text(), parse_mode="Markdown")

        @self._router.message(Command("status"))
        async def status_handler(message: Message):
            await message.answer(self._build_status_text(), parse_mode="Markdown")

        @self._router.message(Command("signals"))
        async def signals_handler(message: Message):
            await message.answer(await self._build_signals_text(), parse_mode="Markdown")

        @self._router.message(Command("stats"))
        async def stats_handler(message: Message):
            await message.answer(await self._build_stats_text(), parse_mode="Markdown")

        @self._router.message(Command("help"))
        async def help_handler(message: Message):
            await message.answer(self._build_help_text(), parse_mode="Markdown")

        @self._router.message(Command("join"))
        async def join_handler(message: Message):
            """Пригласительная ссылка на канал."""
            channel_link = getattr(settings, 'telegram_channel_link', None)
            if channel_link:
                await message.answer(
                    f"📢 **Присоединяйтесь к нашему каналу!**\n\n"
                    f"Там публикуются все сигналы в реальном времени.\n\n"
                    f"🔗 **Ссылка:** [{channel_link}]({channel_link})\n\n"
                    f"Или нажмите: {channel_link}"
                )
            else:
                await message.answer("❌ Канал не настроен")

    async def _set_commands(self):
        if not self._bot:
            return
        await self._bot.set_my_commands([
            BotCommand(command="start", description="🚀 Запустить бота"),
            BotCommand(command="status", description="📊 Статус нотификера"),
            BotCommand(command="signals", description="📈 Последние сигналы"),
            BotCommand(command="stats", description="📉 Статистика 24h"),
            BotCommand(command="join", description="📢 Канал с сигналами"),
            BotCommand(command="help", description="❓ Помощь"),
        ])

    def _build_start_text(self) -> str:
        mode = "testnet" if settings.testnet else "live"
        channel_link = getattr(settings, 'telegram_channel_link', None)
        
        join_text = ""
        if channel_link:
            join_text = f"\n📢 **Наш канал:** [{channel_link}]({channel_link})\n"
        
        return (
            "🤖 **Bot is online**\n\n"
            f"Mode: `{mode}`\n"
            f"Symbol: `{settings.symbol}`\n"
            f"Signals chat: `{settings.telegram_chat_id or 'not configured'}`\n"
            f"{join_text}"
            "**Commands:**\n"
            "/status - show notifier status\n"
            "/signals - last 5 signals\n"
            "/stats - 24h statistics\n"
            "/help - bot help"
        )

    def _build_status_text(self) -> str:
        queue_size = self._queue.qsize()
        running = "yes" if self._running else "no"
        return (
            "Notifier status\n\n"
            f"Running: `{running}`\n"
            f"Queue size: `{queue_size}`\n"
            f"Mode: `{'testnet' if settings.testnet else 'live'}`"
        )

    async def _build_signals_text(self) -> str:
        """Get last 5 signals from database."""
        try:
            from database.db import Database
            db = Database(settings.db_path)
            await db.connect()
            rows = await db._fetch("""
                SELECT created_at, strategy, direction, entry_market, 
                       take_profit, rr_ratio, confidence_score, status
                FROM signals 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            await db.close()
            
            if not rows:
                return "No signals yet.\n\nStart the bot and wait for analysis cycles."
            
            lines = ["**Recent Signals:**\n"]
            for r in rows:
                emoji = "🟢" if r[2] == "LONG" else "🔴"
                lines.append(
                    f"{emoji} `{r[2]}` {r[1]}\n"
                    f"   Entry: `{r[3]:.2f}` | TP: `{r[4]:.2f}` | RR: `{r[5]:.2f}`\n"
                    f"   Conf: `{r[6]}%` | Status: `{r[7]}`\n"
                    f"   Time: `{r[0]}`\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Signals command error: {e}")
            return "Error fetching signals. Check logs."

    async def _build_stats_text(self) -> str:
        """Get 24h statistics from database."""
        try:
            from database.db import Database
            db = Database(settings.db_path)
            await db.connect()
            
            # Get metrics from health endpoint logic
            metrics = await db.get_metrics_24h()
            
            # Get additional stats
            row = await db._fetch_one("""
                SELECT 
                    COUNT(*),
                    SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status='sl_hit' THEN 1 ELSE 0 END),
                    AVG(confidence_score)
                FROM signals 
                WHERE created_at > datetime('now','-24 hours')
            """)
            await db.close()
            
            total = row[0] or 0
            tp = row[1] or 0
            sl = row[2] or 0
            avg_conf = row[3] or 0.0
            closed = tp + sl
            winrate = (tp / closed * 100) if closed > 0 else 0.0
            
            return (
                "**Statistics (24h)**\n\n"
                f"Signals: `{metrics['signals_24h']}`\n"
                f"Winrate: `{metrics['winrate_24h']:.1f}%`\n"
                f"Avg Confidence: `{avg_conf:.1f}%`\n"
                f"Avg Drawdown: `{metrics['avg_drawdown_pct_24h']:.2f}%`\n\n"
                f"TP Hits: `{tp}`\n"
                f"SL Hits: `{sl}`\n"
                f"Total Closed: `{closed}`"
            )
        except Exception as e:
            logger.error(f"Stats command error: {e}")
            return "Error fetching stats. Check logs."

    def _build_help_text(self) -> str:
        return (
            "**Crypto Signal Bot — Help**\n\n"
            "**Commands:**\n"
            "/start — Запустить бота\n"
            "/status — Статус нотификера\n"
            "/signals — Последние 5 сигналов\n"
            "/stats — Статистика за 24 часа\n"
            "/help — Эта справка\n\n"
            "**Режимы работы:**\n"
            "• `live` — реальная торговля\n"
            "• `testnet` — тестовая сеть Binance\n\n"
            "**Стратегии:**\n"
            "• Liquidity Sweep Reversal\n"
            "• Volatility Breakout\n\n"
            "**Настройки:**\n"
            f"Symbol: `{settings.symbol}`\n"
            f"Mode: `{'testnet' if settings.testnet else 'live'}`\n\n"
            "Bot sends signals when confidence ≥ 65%"
        )
