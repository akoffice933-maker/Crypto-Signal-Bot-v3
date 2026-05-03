import asyncio
import sys, os
import time
import logging
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import settings
from database.db import Database
from telegram.bot import TelegramNotifier, TransientTelegramPollingFilter
from telegram.formatter import format_signal
from web.services.signal_exports import render_signals_csv


@contextmanager
def _temp_db():
    tmp_root = Path(__file__).resolve().parent / "_tmp_notifier"
    tmp_dir = tmp_root / uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db = Database(str(tmp_dir / "signals.db"))
    try:
        asyncio.run(db.connect())
        yield db
    finally:
        asyncio.run(db.close())
        if tmp_dir.exists():
            rmtree(tmp_dir, ignore_errors=True)


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


def test_telegram_build_bot_uses_configured_request_timeout():
    original_token = settings.telegram_token
    original_request_timeout = settings.telegram_request_timeout_seconds
    try:
        settings.telegram_token = "123456:ABCDEF"
        settings.telegram_request_timeout_seconds = 75
        notifier = TelegramNotifier()
        bot = notifier._build_bot()
        assert bot.session.timeout == 75
        print("OK Telegram bot session uses configured request timeout")
        asyncio.run(bot.session.close())
    finally:
        settings.telegram_token = original_token
        settings.telegram_request_timeout_seconds = original_request_timeout


def test_telegram_polling_backoff_is_stretched_for_network_spikes():
    notifier = TelegramNotifier()
    backoff = notifier._build_polling_backoff()
    assert backoff.min_delay == 1.0
    assert backoff.max_delay == 15.0
    assert round(backoff.factor, 1) == 1.5
    print("OK Telegram polling backoff is configured for transient network failures")


def test_transient_telegram_polling_filter_drops_known_reconnect_noise():
    filt = TransientTelegramPollingFilter()
    dropped = logging.LogRecord(
        name="aiogram.dispatcher",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Failed to fetch updates - TelegramNetworkError: HTTP Client says - ServerDisconnectedError: Server disconnected",
        args=(),
        exc_info=None,
    )
    kept = logging.LogRecord(
        name="aiogram.dispatcher",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Failed to fetch updates - TelegramNetworkError: HTTP Client says - Bad Gateway",
        args=(),
        exc_info=None,
    )
    assert filt.filter(dropped) is False
    assert filt.filter(kept) is True
    print("OK transient Telegram polling disconnects are filtered from logs")


def test_telegram_start_text_contains_mode_and_chat_id():
    original_testnet = settings.testnet
    original_chat_id = settings.telegram_chat_id
    try:
        settings.testnet = True
        settings.telegram_chat_id = "2017851817"
        notifier = TelegramNotifier()
        text = notifier._build_start_text()
        assert "Crypto Signal Bot" in text
        assert "Mode: `testnet`" in text
        assert "Chat ID: `2017851817`" in text
        assert "/status" in text
        assert "/replay" in text
        print("✅ Telegram /start text exposes mode and chat id")
    finally:
        settings.testnet = original_testnet
        settings.telegram_chat_id = original_chat_id


def test_telegram_replay_limit_parser_and_help_text():
    notifier = TelegramNotifier()
    assert notifier._parse_replay_limit("/replay") == 20
    assert notifier._parse_replay_limit("/replay 50") == 50
    try:
        notifier._parse_replay_limit("/replay nope")
        raise AssertionError("Expected ValueError for invalid replay argument")
    except ValueError:
        pass

    help_text = notifier._build_help_text()
    assert "/replay [limit]" in help_text
    print("✅ Telegram /replay command is exposed and parses limits")


def test_telegram_builds_public_download_url_for_replay():
    original_public_base_url = settings.public_base_url
    original_download_token = settings.download_token
    try:
        settings.public_base_url = "http://148.222.186.16:8001"
        settings.download_token = "secret123"
        notifier = TelegramNotifier()
        assert (
            notifier._build_public_download_url("results/signal_replay_latest.csv")
            == "http://148.222.186.16:8001/downloads/signal_replay_latest.csv?token=secret123"
        )
        print("✅ Telegram replay download URL is built from PUBLIC_BASE_URL")
    finally:
        settings.public_base_url = original_public_base_url
        settings.download_token = original_download_token


def test_format_signal_renders_quiet_volatility_label():
    text = format_signal(
        {
            "signal_id": "abc12345",
            "pair": "BTCUSDT",
            "strategy": "sweep_reversal",
            "direction": "SHORT",
            "entry_market": 71695.10,
            "entry_limit": 71645.30,
            "stop_loss": 72003.83,
            "tp1_price": 70928.24,
            "tp1_rr": 2.0,
            "tp1_size_pct": 0.5,
            "final_tp_size_pct": 0.5,
            "take_profit": 70357.42,
            "rr_ratio": 4.3,
            "execution_basis": "limit",
            "confidence_score": 75,
            "market_state": "ranging",
            "volatility_regime": "quiet",
            "target_liquidity_tf": "1d",
            "target_liquidity_type": "equal_lows",
            "confidence_breakdown": "[]",
        }
    )
    assert "Volatility:   Quiet" in text
    assert "TP1:           70928.24 (50% @ 2.0R)" in text
    assert "Take Profit:   70357.42 (50%)" in text
    assert "RR:            4.3 (limit)" in text
    print("OK Telegram formatter shows Quiet volatility")


def test_format_signal_falls_back_to_raw_volatility_value():
    text = format_signal(
        {
            "signal_id": "abc12345",
            "pair": "BTCUSDT",
            "strategy": "breakout",
            "direction": "LONG",
            "entry_market": 70000.0,
            "stop_loss": 69500.0,
            "tp1_price": None,
            "tp1_rr": None,
            "tp1_size_pct": None,
            "final_tp_size_pct": 1.0,
            "take_profit": 70900.0,
            "rr_ratio": 1.8,
            "execution_basis": "market",
            "confidence_score": 68,
            "market_state": "trending",
            "volatility_regime": "experimental_mode",
            "confidence_breakdown": "[]",
        }
    )
    assert "Volatility:   experimental_mode" in text
    assert "RR:            1.8 (market)" in text
    print("OK Telegram formatter preserves unknown volatility labels")


def test_build_signals_text_wraps_strategy_in_backticks():
    original_db_path = settings.db_path
    try:
        with _temp_db() as db:
            settings.db_path = str(db.db_path)
            asyncio.run(
                db.save_signal(
                    {
                        "signal_id": "sig_md_1",
                        "pair": "BTCUSDT",
                        "strategy": "sweep_reversal",
                        "direction": "SHORT",
                        "session": "ny",
                        "entry_market": 71692.90,
                        "entry_limit": 71645.30,
                        "stop_loss": 72003.83,
                        "tp1_price": 70928.24,
                        "tp1_rr": 2.0,
                        "tp1_size_pct": 0.5,
                        "final_tp_size_pct": 0.5,
                        "take_profit": 70357.42,
                        "rr_ratio": 3.59,
                        "rr_market": 4.29,
                        "rr_limit": 3.59,
                        "execution_basis": "limit",
                        "position_size_pct": None,
                        "confidence_score": 75,
                        "confidence_breakdown": "[]",
                        "market_state": "ranging",
                        "volatility_regime": "quiet",
                        "adx_value": 19.0,
                        "atr_pct": 0.003,
                        "target_liquidity_price": 70357.42,
                        "target_liquidity_tf": "1d",
                        "target_liquidity_type": "equal_lows",
                        "distance_to_target_pct": 0.018,
                        "cvd_divergence": None,
                        "oi_change_pct": 0.2,
                        "liquidation_cascade": False,
                        "funding_rate": 0.0001,
                        "squeeze_active": False,
                    }
                )
            )
            notifier = TelegramNotifier()
            text = asyncio.run(notifier._build_signals_text())
            assert "`sweep_reversal`" in text
            print("OK /signals text wraps strategy names safely for Markdown")
    finally:
        settings.db_path = original_db_path


def test_save_signal_normalizes_boolean_fields_for_sqlite():
    with _temp_db() as db:
        asyncio.run(
            db.save_signal(
                {
                    "signal_id": "sig_bool_1",
                    "pair": "BTCUSDT",
                    "strategy": "sweep_reversal",
                    "direction": "LONG",
                    "session": "asian",
                    "entry_market": 70000.0,
                    "entry_limit": 69950.0,
                    "stop_loss": 69750.0,
                    "tp1_price": 70450.0,
                    "tp1_rr": 2.0,
                    "tp1_size_pct": 0.5,
                    "final_tp_size_pct": 0.5,
                    "take_profit": 71000.0,
                    "rr_ratio": 3.0,
                    "rr_market": 3.2,
                    "rr_limit": 3.0,
                    "execution_basis": "limit",
                    "position_size_pct": None,
                    "confidence_score": 80,
                    "confidence_breakdown": [{"factor": "test", "delta": 10}],
                    "market_state": "trending",
                    "volatility_regime": "quiet",
                    "adx_value": 40.0,
                    "atr_pct": 0.004,
                    "target_liquidity_price": 71000.0,
                    "target_liquidity_tf": "1d",
                    "target_liquidity_type": "equal_highs",
                    "distance_to_target_pct": 0.02,
                    "cvd_divergence": None,
                    "oi_change_pct": 0.1,
                    "liquidation_cascade": False,
                    "funding_rate": 0.0,
                    "squeeze_active": True,
                }
            )
        )
        rows = asyncio.run(
            db._fetch(
                "SELECT liquidation_cascade, squeeze_active, confidence_breakdown FROM signals WHERE signal_id=?",
                ("sig_bool_1",),
            )
        )
        assert rows
        liquidation_cascade, squeeze_active, confidence_breakdown = rows[0]
        assert liquidation_cascade == 0
        assert squeeze_active == 1
        assert confidence_breakdown.startswith("[")
        print("OK save_signal normalizes booleans and breakdown for SQLite")


def test_save_signal_defaults_missing_boolean_fields_to_zero():
    with _temp_db() as db:
        asyncio.run(
            db.save_signal(
                {
                    "signal_id": "sig_bool_2",
                    "pair": "BTCUSDT",
                    "strategy": "sweep_reversal",
                    "direction": "SHORT",
                    "session": "ny",
                    "entry_market": 70000.0,
                    "entry_limit": 70020.0,
                    "stop_loss": 70200.0,
                    "tp1_price": None,
                    "tp1_rr": None,
                    "tp1_size_pct": None,
                    "final_tp_size_pct": 1.0,
                    "take_profit": 69000.0,
                    "rr_ratio": 5.0,
                    "rr_market": 5.2,
                    "rr_limit": 5.0,
                    "execution_basis": "limit",
                    "position_size_pct": None,
                    "confidence_score": 70,
                    "confidence_breakdown": "[]",
                    "market_state": "trending",
                    "volatility_regime": "quiet",
                    "adx_value": 35.0,
                    "atr_pct": 0.004,
                    "target_liquidity_price": 69000.0,
                    "target_liquidity_tf": "1d",
                    "target_liquidity_type": "equal_lows",
                    "distance_to_target_pct": 0.02,
                    "cvd_divergence": None,
                    "oi_change_pct": 0.0,
                    "funding_rate": 0.0,
                }
            )
        )
        rows = asyncio.run(
            db._fetch(
                "SELECT liquidation_cascade, squeeze_active FROM signals WHERE signal_id=?",
                ("sig_bool_2",),
            )
        )
        assert rows
        liquidation_cascade, squeeze_active = rows[0]
        assert liquidation_cascade == 0
        assert squeeze_active == 0
        print("OK save_signal defaults missing boolean fields to zero")
