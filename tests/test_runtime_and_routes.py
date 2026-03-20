import asyncio
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import settings
from config.settings import ConfigurationError
from main import apply_cli_overrides, validate_runtime_config
from web.routes.signals import liquidity


class _FakeDB:
    async def _fetch(self, _query, _params):
        return [
            ("1d", "equal_highs", 61000.0, 3, 9.0, 0),
            ("4h", "equal_lows", 59000.0, 4, 4.0, 1),
        ]


def test_apply_cli_overrides_enables_testnet():
    original = settings.testnet
    try:
        settings.testnet = False
        apply_cli_overrides(testnet=True)
        assert settings.testnet is True
        print("✅ CLI override enables testnet mode")
    finally:
        settings.testnet = original


def test_validate_runtime_config_requires_telegram_token():
    original_token = settings.telegram_token
    original_chat_id = settings.telegram_chat_id
    try:
        settings.telegram_token = ""
        settings.telegram_chat_id = "123"
        try:
            validate_runtime_config(dry_run=False)
        except ConfigurationError as exc:
            assert "TELEGRAM_BOT_TOKEN required" in str(exc)
        else:
            raise AssertionError("ConfigurationError was not raised")
        print("✅ Runtime validation blocks startup without Telegram token")
    finally:
        settings.telegram_token = original_token
        settings.telegram_chat_id = original_chat_id


def test_liquidity_route_uses_current_price():
    rows = asyncio.run(liquidity(min_strength=3.0, current_price=60000.0, db=_FakeDB()))
    assert rows[0]["distance_pct"] == 1.67
    assert rows[1]["distance_pct"] == 1.67
    print("✅ Liquidity route computes distance from explicit current price")


def test_liquidity_route_without_current_price():
    rows = asyncio.run(liquidity(min_strength=3.0, current_price=None, db=_FakeDB()))
    assert rows[0]["distance_pct"] is None
    assert rows[1]["distance_pct"] is None
    print("✅ Liquidity route leaves distance empty without current price")
