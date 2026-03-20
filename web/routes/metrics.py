from fastapi import APIRouter, Depends, Response

from database.db import Database
from web.dependencies import get_db

router = APIRouter(tags=["metrics"])


def _prometheus_text(metrics: dict) -> str:
    lines = [
        "# HELP crypto_signal_signals_24h Number of signals generated in the last 24 hours.",
        "# TYPE crypto_signal_signals_24h gauge",
        f"crypto_signal_signals_24h {metrics['signals_24h']}",
        "# HELP crypto_signal_winrate_24h Winrate percentage for closed trades in the last 24 hours.",
        "# TYPE crypto_signal_winrate_24h gauge",
        f"crypto_signal_winrate_24h {metrics['winrate_24h']}",
        "# HELP crypto_signal_avg_drawdown_pct_24h Average drawdown percentage across losing trades in the last 24 hours.",
        "# TYPE crypto_signal_avg_drawdown_pct_24h gauge",
        f"crypto_signal_avg_drawdown_pct_24h {metrics['avg_drawdown_pct_24h']}",
    ]
    return "\n".join(lines) + "\n"


@router.get("/metrics")
async def metrics(db: Database = Depends(get_db)):
    snapshot = await db.get_metrics_24h()
    return Response(
        content=_prometheus_text(snapshot),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
