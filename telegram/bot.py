import asyncio
from contextlib import suppress
import logging
import time
from collections import deque
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, Message
from aiogram.utils.backoff import BackoffConfig

from config.settings import settings
from telegram.formatter import format_signal

logger = logging.getLogger(__name__)


class TransientTelegramPollingFilter(logging.Filter):
    _TRANSIENT_MESSAGES = (
        "Failed to fetch updates - TelegramNetworkError: HTTP Client says - Request timeout error",
        "Failed to fetch updates - TelegramNetworkError: HTTP Client says - ServerDisconnectedError: Server disconnected",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "aiogram.dispatcher":
            return True
        message = record.getMessage()
        return not any(marker in message for marker in self._TRANSIENT_MESSAGES)


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
        self._replay_task: asyncio.Task | None = None

    async def start(self):
        if not settings.telegram_token:
            logger.warning("No Telegram token — notifications disabled")
            return
        self._bot = self._build_bot()
        self._dispatcher = Dispatcher()
        self._router = Router()
        self._register_handlers()
        self._dispatcher.include_router(self._router)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="telegram_notifier_worker")
        self._polling_task = asyncio.create_task(
            self._dispatcher.start_polling(
                self._bot,
                polling_timeout=settings.telegram_polling_timeout_seconds,
                backoff_config=self._build_polling_backoff(),
            ),
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
        if self._replay_task:
            self._replay_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._replay_task
            self._replay_task = None
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

    def _build_bot(self) -> Bot:
        session = AiohttpSession(timeout=settings.telegram_request_timeout_seconds)
        return Bot(token=settings.telegram_token, session=session)

    def _build_polling_backoff(self) -> BackoffConfig:
        # Keep reconnects resilient to short Telegram/API network spikes.
        return BackoffConfig(min_delay=1.0, max_delay=15.0, factor=1.5, jitter=0.1)

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

        @self._router.message(Command("active"))
        async def active_handler(message: Message):
            """Показать активные сигналы."""
            try:
                from database.db import Database
                db = Database(settings.db_path)
                await db.connect()
                signals = await db.get_active_signals(limit=10)
                await db.close()

                if not signals:
                    await message.answer("Нет активных сигналов 🫡")
                    return

                lines = ["**🔴 Active Signals:**\n"]
                for s in signals:
                    emoji = "🟢" if s["direction"] == "LONG" else "🔴"
                    pnl_text = "— "  # Можно добавить расчёт PnL
                    lines.append(
                        f"{emoji} `{s['pair']}` `{s['direction']}` — `{s['strategy']}`\n"
                        f"   Entry: `{s['entry_market']:.2f}` | TP: `{s['take_profit']:.2f}`\n"
                        f"   PnL: `{pnl_text}`\n"
                    )
                await message.answer("\n".join(lines), parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Active command error: {e}")
                await message.answer("Error fetching active signals.")


        @self._router.message(Command("pairs"))
        async def pairs_handler(message: Message):
            """Показать список пар и статистику."""
            try:
                from database.db import Database
                db = Database(settings.db_path)
                await db.connect()
                stats = await db.get_pair_stats()
                await db.close()

                if not stats:
                    await message.answer("Нет данных по парам.")
                    return

                lines = ["**📊 Trading Pairs:**\n"]
                for s in stats:
                    total = s["total"] or 0
                    tp = s["tp_hits"] or 0
                    sl = s["sl_hits"] or 0
                    winrate = ((tp / (tp + sl)) * 100) if (tp + sl) > 0 else 0
                    lines.append(
                        f"`{s['pair']}`\n"
                        f"   Signals: `{total}` | Winrate: `{winrate:.1f}%`\n"
                        f"   Avg Conf: `{s['avg_confidence']:.1f}%`\n"
                    )
                await message.answer("\n".join(lines), parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Pairs command error: {e}")
                await message.answer("Error fetching pairs stats.")

        @self._router.message(Command("export"))
        async def export_handler(message: Message):
            """Экспорт сигналов в CSV."""
            try:
                from database.db import Database
                import csv
                import io
                from pathlib import Path

                db = Database(settings.db_path)
                await db.connect()
                signals = await db.get_signals_for_telegram_export(limit=100)
                await db.close()

                if not signals:
                    await message.answer("Нет сигналов для экспорта.")
                    return

                # Создаём CSV в памяти
                output = io.StringIO()
                fieldnames = ['signal_id', 'created_at', 'pair', 'strategy', 'direction',
                             'entry_market', 'stop_loss', 'take_profit', 'rr_ratio',
                             'confidence_score', 'status']
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                for s in signals:
                    writer.writerow({
                        'signal_id': s['signal_id'], 'created_at': s['created_at'],
                        'pair': s['pair'], 'strategy': s['strategy'],
                        'direction': s['direction'], 'entry_market': s['entry_market'],
                        'stop_loss': s['stop_loss'], 'take_profit': s['take_profit'],
                        'rr_ratio': s['rr_ratio'], 'confidence_score': s['confidence_score'],
                        'status': s['status']
                    })

                # Сохраняем файл
                Path("results").mkdir(exist_ok=True)
                filepath = Path("results") / "telegram_export.csv"
                with open(filepath, "w", encoding="utf-8", newline="") as f:
                    f.write(output.getvalue())

                await message.answer_document(
                    document=str(filepath),
                    caption=f"📊 Exported {len(rows)} signals"
                )
            except Exception as e:
                logger.error(f"Export command error: {e}")
                await message.answer(f"Export failed: {e}")

        @self._router.message(Command("help"))
        async def help_handler(message: Message):
            await message.answer(self._build_help_text(), parse_mode="Markdown")

        @self._router.message(Command("replay"))
        async def replay_handler(message: Message):
            if self._replay_task and not self._replay_task.done():
                await message.answer("Replay уже выполняется. Дождись завершения текущего прогона.")
                return

            try:
                limit = self._parse_replay_limit(message.text)
            except ValueError as e:
                await message.answer(str(e))
                return

            await message.answer(
                f"Запускаю replay последних `{limit}` сигналов. Это может занять до пары минут.",
                parse_mode="Markdown",
            )
            self._replay_task = asyncio.create_task(
                self._run_signal_replay(message.chat.id, limit),
                name="telegram_signal_replay",
            )

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
            BotCommand(command="status", description="📊 Статус бота"),
            BotCommand(command="active", description="🔴 Активные сигналы"),
            BotCommand(command="pairs", description="📈 Статистика по парам"),
            BotCommand(command="signals", description="📉 Последние сигналы"),
            BotCommand(command="stats", description="📊 Статистика 24h"),
            BotCommand(command="export", description="📥 Экспорт в CSV"),
            BotCommand(command="replay", description="🧪 Replay сигналов"),
            BotCommand(command="join", description="📢 Канал с сигналами"),
            BotCommand(command="help", description="❓ Помощь"),
        ])

    def _build_start_text(self) -> str:
        mode = "testnet" if settings.testnet else "live"
        pairs = ", ".join(settings.symbols)
        channel_link = getattr(settings, 'telegram_channel_link', None)

        join_text = ""
        if channel_link:
            join_text = f"\n📢 **Наш канал:** [{channel_link}]({channel_link})\n"

        return (
            "🤖 **Crypto Signal Bot v3.4**\n\n"
            f"Mode: `{mode}`\n"
            f"Pairs: `{pairs}`\n"
            f"Chat ID: `{settings.telegram_chat_id or 'not configured'}`\n"
            f"{join_text}"
            "**📋 Commands:**\n"
            "/status - Статус бота\n"
            "/active - Активные сигналы 🔴\n"
            "/pairs - Статистика по парам 📈\n"
            "/signals - Последние 5 сигналов\n"
            "/stats - Статистика 24h 📊\n"
            "/export - Экспорт в CSV 📥\n"
            "/replay [limit] - Replay сигналов\n"
            "/help - Помощь\n"
            "/join - Канал с сигналами"
        )

    def _build_status_text(self) -> str:
        queue_size = self._queue.qsize()
        running = "yes" if self._running else "no"
        pairs = ", ".join(settings.symbols)
        return (
            "**Notifier Status**\n\n"
            f"Running: `{running}`\n"
            f"Queue size: `{queue_size}`\n"
            f"Mode: `{'testnet' if settings.testnet else 'live'}`\n"
            f"Pairs: `{pairs}`"
        )

    async def _build_signals_text(self) -> str:
        """Get last 5 signals from database."""
        try:
            from database.db import Database
            db = Database(settings.db_path)
            await db.connect()
            signals = await db.get_recent_signals(limit=5)
            await db.close()
            
            if not signals:
                return "No signals yet.\n\nStart the bot and wait for analysis cycles."
            
            lines = ["**Recent Signals:**\n"]
            for s in signals:
                emoji = "🟢" if s["direction"] == "LONG" else "🔴"
                lines.append(
                    f"{emoji} `{s['direction']}` `{s['strategy']}`\n"
                    f"   Entry: `{s['entry_market']:.2f}` | TP: `{s['take_profit']:.2f}` | RR: `{s['rr_ratio']:.2f}`\n"
                    f"   Conf: `{s['confidence_score']}%` | Status: `{s['status']}`\n"
                    f"   Time: `{s['created_at']}`\n"
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

    def _parse_replay_limit(self, text: str | None) -> int:
        default_limit = 20
        if not text:
            return default_limit
        parts = text.strip().split()
        if len(parts) == 1:
            return default_limit
        try:
            limit = int(parts[1])
        except ValueError as e:
            raise ValueError("Usage: /replay or /replay 20") from e
        if not 1 <= limit <= 200:
            raise ValueError("Replay limit must be between 1 and 200.")
        return limit

    def _build_public_download_url(self, filename: str) -> str | None:
        if not settings.public_base_url or not settings.download_token:
            return None
        return (
            f"{settings.public_base_url}/downloads/{Path(filename).name}"
            f"?token={settings.download_token}"
        )

    async def _run_signal_replay(self, chat_id: int, limit: int) -> None:
        if not self._bot:
            return

        try:
            from scripts.signal_replay import run_signal_replay

            replay = await run_signal_replay(
                db_path=settings.db_path,
                limit=limit,
                out=str(Path("results") / "signal_replay_latest.csv"),
                default_basis=settings.execution_basis,
                position_pct=settings.max_position_pct,
            )
            summary = replay["summary"]
            download_url = self._build_public_download_url(replay["csv_path"])
            text = (
                "**Signal Replay Completed**\n\n"
                f"Signals processed: `{summary['signals_processed']}`\n"
                f"Validated: `{summary['validated']}`\n"
                f"No fill: `{summary['no_fill']}`\n"
                f"No data: `{summary['no_data']}`\n"
                f"Insufficient candles: `{summary['insufficient_future_data']}`\n"
                f"Full TP hits: `{summary['full_tp_hits']}`\n"
                f"SL hits: `{summary['sl_hits']}`\n"
                f"Timeout hits: `{summary['timeout_hits']}`\n"
                f"Avg achieved RR: `{summary['avg_rr_achieved']:.2f}`"
            )
            if download_url:
                text += f"\n\n[Download CSV]({download_url})"
            else:
                text += f"\n\nCSV: `{replay['csv_path']}`"
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Replay command error: {e}")
            await self._bot.send_message(
                chat_id=chat_id,
                text=f"Replay failed: `{e}`",
                parse_mode="Markdown",
            )
        finally:
            self._replay_task = None

    def _build_help_text(self) -> str:
        pairs = ", ".join(settings.symbols)
        return (
            "**🤖 Crypto Signal Bot v3.4 — Help**\n\n"
            "**📋 Commands:**\n"
            "/start — Запустить бота 🚀\n"
            "/status — Статус бота 📊\n"
            "/active — Активные сигналы 🔴\n"
            "/pairs — Статистика по парам 📈\n"
            "/signals — Последние 5 сигналов 📉\n"
            "/stats — Статистика за 24 часа 📊\n"
            "/export — Экспорт в CSV 📥\n"
            "/replay [limit] — Replay live signals 🧪\n"
            "/help — Эта справка ❓\n"
            "/join — Канал с сигналами 📢\n\n"
            "**🎯 Стратегии:**\n"
            "• Liquidity Sweep Reversal\n"
            "• Volatility Breakout\n\n"
            "**📊 Trading Pairs:**\n"
            f"`{pairs}`\n\n"
            "**⚙️ Настройки:**\n"
            f"Mode: `{'testnet' if settings.testnet else 'live'}`\n"
            f"Confidence: ≥ 65%\n"
            f"Min RR: 2.0\n\n"
            "**💡 Советы:**\n"
            "• Используйте /active для отслеживания открытых сигналов\n"
            "• /pairs покажет статистику по каждой паре\n"
            "• /export выгрузит последние 100 сигналов в CSV"
        )
