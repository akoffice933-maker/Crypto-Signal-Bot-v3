import asyncio
import sys, os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import settings
from telegram.bot import TelegramNotifier
from web.services.signal_exports import render_signals_csv


def test_render_signals_csv_contains_headers_and_rows():
    csv_text = render_signals_csv([
        {
            "signal_id": "abc123",
            "created_at": "2026-03-17T22:00:00Z",
            "pair": "BTCUSDT",
            "strategy": "sweep_reversal",
            "direction": "LONG",
            "session": "london",
            "entry_market": 60000,
            "stop_loss": 59750,
            "take_profit": 60600,
            "rr_ratio": 2.0,
            "confidence_score": 82,
            "status": "sent",
        }
    ])
    assert "signal_id,created_at,pair,strategy,direction,session" in csv_text
    assert "abc123" in csv_text
    print("✅ CSV renderer outputs header and signal row")


def test_telegram_rate_limit_guard_waits_between_messages():
    original_interval = settings.telegram_min_interval_seconds
    original_max = settings.telegram_max_messages_per_minute
    notifier = TelegramNotifier()
    waits = []

    async def fake_sleep(delay):
        waits.append(round(delay, 2))

    import telegram.bot as telegram_bot_module

    original_sleep = telegram_bot_module.asyncio.sleep
    try:
        settings.telegram_min_interval_seconds = 1.5
        settings.telegram_max_messages_per_minute = 20
        notifier._last_send_at = time.monotonic()
        telegram_bot_module.asyncio.sleep = fake_sleep
        asyncio.run(notifier._throttle())
        assert waits and waits[0] > 0
        print("✅ Telegram min-interval guard inserts a wait")
    finally:
        settings.telegram_min_interval_seconds = original_interval
        settings.telegram_max_messages_per_minute = original_max
        telegram_bot_module.asyncio.sleep = original_sleep


def test_telegram_start_text_contains_mode_and_chat_id():
    original_testnet = settings.testnet
    original_chat_id = settings.telegram_chat_id
    try:
        settings.testnet = True
        settings.telegram_chat_id = "2017851817"
        notifier = TelegramNotifier()
        text = notifier._build_start_text()
        assert "Bot is online." in text
        assert "Mode: `testnet`" in text
        assert "Signals chat: `2017851817`" in text
        assert "/status - show notifier status" in text
        print("✅ Telegram /start text exposes mode and chat id")
    finally:
        settings.testnet = original_testnet
        settings.telegram_chat_id = original_chat_id
