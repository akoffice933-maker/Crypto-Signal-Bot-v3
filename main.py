"""
Crypto Signal Bot v3 — Main Entry Point
"""

import argparse
import asyncio
import logging
import signal
import sys
import io
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import ConfigurationError, settings
from data.binance_client import BinanceFuturesClient
from data.orderflow_ws import OrderFlowWebSocket
from database.db import Database
from engine.pipeline import run_pipeline
from engine.sweep_trigger_5m import SweepTrigger5m
from engine.trade_manager import TradeManager
from telegram.bot import TelegramNotifier, TransientTelegramPollingFilter


def _configure_console_encoding():
    """Reconfigure console streams to UTF-8 on Windows (Python 3.7+)."""
    if sys.platform != "win32":
        return
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ── Console encoding (must be before logging.basicConfig) ────
_configure_console_encoding()

# ── Logging setup ─────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
    ],
)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(TransientTelegramPollingFilter())
logger = logging.getLogger(__name__)

# ── Globals ───────────────────────────────────────────────────
db:        Database           = None
client:    BinanceFuturesClient = None
ws:        OrderFlowWebSocket   = None
notifier:  TelegramNotifier     = None
sweep_trigger: SweepTrigger5m   = None
trade_manager: TradeManager     = None
scheduler: AsyncIOScheduler     = None
api_task:   asyncio.Task        = None
api_server = None
_dry_run:  bool                 = False
_shutdown_started: bool         = False
_stop_event: asyncio.Event      = None
_last_shutdown_signal: str      = ""


async def analysis_cycle():
    """Called by scheduler every 15 minutes."""
    logger.info("── Analysis cycle start ──────────────────")
    logger.info(f"  🔍 [DIAG] Cycle at UTC hour {datetime.now(timezone.utc).hour}")
    try:
        sig = await run_pipeline(
            client=client,
            db=db,
            ws=ws,
            notifier=notifier if not _dry_run else None,
            sweep_trigger=sweep_trigger,
        )
        if sig:
            logger.info(
                f"Signal: {sig['direction']} {sig['strategy']} "
                f"entry={sig['entry_market']} conf={sig['confidence_score']}"
            )
            # If signal has ATR, open a trade via trade_manager
            if trade_manager and 'atr_pct' in sig:
                try:
                    trade = await trade_manager.open_trade(
                        signal=sig,
                        sweep_trigger=sweep_trigger,
                    )
                    if trade:
                        logger.info(f"Trade opened: {trade.id}")
                except Exception as e:
                    logger.error(f"Failed to open trade: {e}", exc_info=True)
        else:
            logger.info(f"  ℹ️ [DIAG] No signal returned from pipeline this cycle")
        
        # Tick trade manager to check price levels
        if trade_manager and client:
            await trade_manager.tick_all(client)
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)


async def init():
    global db, client, ws, notifier, sweep_trigger, trade_manager

    logger.info("Initialising components...")

    db = Database(settings.db_path)
    await db.connect()
    logger.info("DB connected")

    client = BinanceFuturesClient(settings.base_url)
    logger.info("Binance client created")

    ws = OrderFlowWebSocket(symbol=settings.symbol.lower())
    logger.info("WebSocket client created")

    if _dry_run:
        notifier = None
        logger.info("DRY RUN — Telegram notifier disabled")
    else:
        notifier = TelegramNotifier()
        await notifier.start()
        logger.info("Telegram notifier started")

    # Sweep trigger for 5M real-time detection
    sweep_trigger = SweepTrigger5m(symbols=settings.symbols)
    await sweep_trigger.start()
    logger.info("SweepTrigger5m started")

    # Trade manager for tracking positions
    trade_manager = TradeManager(notifier=notifier, expiry_hours=4)
    logger.info("TradeManager initialized")
    
    # Link trade_manager to notifier for Telegram commands
    if notifier:
        notifier.trade_manager = trade_manager

    logger.info("All components ready")


def apply_cli_overrides(*, testnet: bool):
    """Apply CLI runtime flags to mutable settings before clients are created."""
    if testnet:
        settings.testnet = True


def current_mode_label() -> str:
    return "testnet" if settings.testnet else "live"


def validate_runtime_config(*, dry_run: bool):
    settings.validate_runtime(dry_run=dry_run)


def request_shutdown(sig_name: str = ""):
    """Signal the main loop to exit and perform a single graceful shutdown."""
    global _last_shutdown_signal
    if sig_name:
        _last_shutdown_signal = sig_name
    if _stop_event and not _stop_event.is_set():
        logger.info(f"Shutdown requested ({sig_name})")
        _stop_event.set()


async def _await_shutdown_step(
    name: str,
    awaitable,
    timeout: float = 5.0,
):
    """Await a shutdown step with a timeout so systemd is not blocked indefinitely."""
    try:
        await asyncio.wait_for(awaitable, timeout=timeout)
        logger.info(f"{name} stopped")
    except asyncio.TimeoutError:
        logger.warning(f"{name} shutdown timed out after {timeout:.1f}s")
    except Exception as e:
        logger.warning(f"{name} shutdown error: {e}")


async def shutdown(sig_name: str = ""):
    global _shutdown_started, _last_shutdown_signal
    resolved_sig_name = sig_name or _last_shutdown_signal
    if _shutdown_started:
        logger.info(
            f"Shutdown already in progress ({resolved_sig_name or 'repeat call'})"
        )
        return
    _shutdown_started = True
    logger.info(f"Shutting down ({resolved_sig_name})...")
    if api_server:
        api_server.should_exit = True
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        except SchedulerNotRunningError:
            logger.debug("Scheduler already stopped")
    if ws:
        await _await_shutdown_step("WebSocket client", ws.stop())
    if notifier:
        await _await_shutdown_step("Telegram notifier", notifier.stop())
    if sweep_trigger:
        await _await_shutdown_step("SweepTrigger5m", sweep_trigger.stop())
    if trade_manager:
        # trade_manager doesn't have a stop method, just log
        logger.info("TradeManager cleaned up")
    if client:
        await _await_shutdown_step("Binance client", client.close())
    if db:
        await _await_shutdown_step("Database", db.close())
    logger.info("Shutdown complete")


async def main():
    global scheduler, _dry_run, api_task, _stop_event

    parser = argparse.ArgumentParser(description="Crypto Signal Bot v3")
    parser.add_argument("--testnet",   action="store_true")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Run pipeline but skip Telegram")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    logging.getLogger().setLevel(args.log_level)
    apply_cli_overrides(testnet=args.testnet)
    _dry_run = args.dry_run
    validate_runtime_config(dry_run=_dry_run)
    if _dry_run:
        logger.info("DRY RUN mode — Telegram disabled")

    await init()
    _stop_event = asyncio.Event()

    # OS signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig, lambda s=sig: request_shutdown(s.name)
            )
        except NotImplementedError:
            logger.debug("Signal handlers are not supported in this environment")

    # WebSocket in background
    ws_task = asyncio.create_task(ws.start())
    api_task = asyncio.create_task(_start_api())

    # Scheduler: analysis at :03/:18/:33/:48 UTC
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        analysis_cycle,
        trigger=CronTrigger(minute="*/15", second=3),
        id="analysis",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info("Bot running. Ctrl+C to stop.")

    if notifier and not _dry_run:
        await notifier.send_text(
            f"Bot started — BTCUSDT Futures ({current_mode_label()})"
        )

    # Run one cycle immediately on startup
    await analysis_cycle()

    try:
        await _stop_event.wait()
    finally:
        await shutdown()
        ws_task.cancel()
        tasks = [ws_task]
        if api_task:
            tasks.append(api_task)
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Background task shutdown timed out; cancelling remaining tasks")
            for task in tasks:
                task.cancel()
            with suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)


# ── FastAPI health server (optional) ──────────────────────────
async def _start_api():
    """Run FastAPI on :8000 alongside the bot."""
    global api_server
    port = 8001  # Changed to 8001 to avoid conflict with run_web_local.py
    logger.info(f"Starting API server on port {port}...")
    try:
        import uvicorn
        from web.app import app
        from web.dependencies import set_db as _set_db
        _set_db(db)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        api_server = uvicorn.Server(config)
        logger.info(f"API server starting on port {port}...")
        await api_server.serve()
    except ImportError:
        logger.info("uvicorn/fastapi not installed — /health endpoint disabled")
    except Exception as e:
        logger.error(f"API server error: {e}", exc_info=True)
    finally:
        api_server = None
        logger.info("API server stopped")


if __name__ == "__main__":
    try:
        _configure_console_encoding()
        asyncio.run(main())
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        raise
