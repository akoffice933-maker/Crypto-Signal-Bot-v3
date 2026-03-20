import csv
import io
from typing import Any, Dict, List

import aiohttp

from config.settings import settings


EXPORT_COLUMNS = [
    "signal_id", "created_at", "pair", "strategy", "direction", "session",
    "entry_market", "entry_limit", "stop_loss", "take_profit", "rr_ratio",
    "confidence_score", "market_state", "volatility_regime",
    "target_liquidity_price", "target_liquidity_tf", "target_liquidity_type",
    "cvd_divergence", "oi_change_pct", "liquidation_cascade", "funding_rate",
    "squeeze_active", "status", "result_pnl_pct", "closed_at",
]


def render_signals_csv(rows: List[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in EXPORT_COLUMNS})
    return buffer.getvalue()


async def sync_signals_to_google_sheets(
    rows: List[Dict[str, Any]],
    webhook_url: str | None = None,
) -> Dict[str, Any]:
    target = webhook_url or settings.google_sheets_webhook_url
    if not target:
        raise ValueError("Google Sheets webhook URL is not configured")

    payload = {
        "columns": EXPORT_COLUMNS,
        "rows": [{key: row.get(key) for key in EXPORT_COLUMNS} for row in rows],
    }
    timeout = aiohttp.ClientTimeout(total=settings.google_sheets_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(target, json=payload) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                remote_payload = await response.json()
            else:
                remote_payload = {"raw_response": await response.text()}
    return {
        "rows_sent": len(rows),
        "webhook_url": target,
        "remote_response": remote_payload,
    }
