from fastapi import APIRouter
from config.settings import settings as app_settings

router = APIRouter(tags=["settings"])


@router.get("/settings/data")
async def get_settings():
    """Get bot settings for the settings page."""
    return {
        "testnet": app_settings.testnet,
        "symbol": app_settings.symbol,
        "telegram_bot_configured": bool(app_settings.telegram_token),
        "db_path": app_settings.db_path,
        "confidence_threshold": app_settings.confidence_threshold,
        "min_rr": app_settings.min_rr,
        "account_balance": app_settings.account_balance,
        "log_level": app_settings.log_level,
        "analysis_interval_minutes": app_settings.analysis_interval_minutes,
    }
