"""
Crypto Signal Bot v3 — Main Entry Point
"""

import argparse
import asyncio
import logging
import signal
import sys
import io
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import ConfigurationError, settings
from data.binance_client import BinanceFuturesClient
from data.orderflow_ws import OrderFlowWebSocket
from database.db import Database
from engine.pipeline import run_pipeline
from telegram.bot import TelegramNotifier

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
logger = logging.getLogger(__name__)

# ── Globals ───────────────────────────────────────────────────
db:        Database           = None
client:    BinanceFuturesClient = None
ws:        OrderFlowWebSocket   = None
notifier:  TelegramNotifier     = None
scheduler: AsyncIOScheduler     = None
api_task:   asyncio.Task        = None
api_server = None
_dry_run:  bool                 = False


def _configure_console_encoding():
    """Only wrap console streams for direct script runs on Windows."""
    if sys.platform != "win32":
        return
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "buffer"):
            continue
        setattr(
            sys,
            name,
            io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"),
        )


async def analysis_cycle():
    """Called by scheduler every 15 minutes."""
    logger.info("── Analysis cycle start ──────────────────")
    try:
        sig = await run_pipeline(
            client=client,
            db=db,
            ws=ws,
            notifier=notifier if not _dry_run else None,
        )
        if sig:
            logger.info(
                f"Signal: {sig['direction']} {sig['strategy']} "
                f"entry={sig['entry_market']} conf={sig['confidence_score']}"
            )
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)


async def init():
    global db, client, ws, notifier

    logger.info("Initialising components...")

    db = Database(settings.db_path)
    await db.connect()
    logger.info("DB connected")

    client = BinanceFuturesClient(settings.base_url)
    logger.info("Binance client created")

    ws = OrderFlowWebSocket(symbol=settings.symbol.lower())
    logger.info("WebSocket client created")

    notifier = TelegramNotifier()
    await notifier.start()
    logger.info("Telegram notifier started")

    logger.info("All components ready")


def apply_cli_overrides(*, testnet: bool):
    """Apply CLI runtime flags to mutable settings before clients are created."""
    if testnet:
        settings.testnet = True


def current_mode_label() -> str:
    return "testnet" if settings.testnet else "live"


def validate_runtime_config(*, dry_run: bool):
    settings.validate_runtime(dry_run=dry_run)


async def shutdown(sig_name: str = ""):
    logger.info(f"Shutting down ({sig_name})...")
    if api_server:
        api_server.should_exit = True
    if scheduler:
        scheduler.shutdown(wait=False)
    if ws:
        await ws.stop()
    if notifier:
        await notifier.stop()
    if client:
        await client.close()
    if db:
        await db.close()
    logger.info("Shutdown complete")


async def main():
    global scheduler, _dry_run, api_task

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

    # OS signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(shutdown(s.name))
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
        await asyncio.Event().wait()
    finally:
        await shutdown()
        ws_task.cancel()
        tasks = [ws_task]
        if api_task:
            tasks.append(api_task)
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
