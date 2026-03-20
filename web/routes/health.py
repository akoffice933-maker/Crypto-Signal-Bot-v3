from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from database.db import Database
from web.dependencies import get_db

router = APIRouter()


@router.get("/health")
async def health(db: Database = Depends(get_db)):
    checks = {}
    overall = "healthy"

    # DB
    try:
        t0 = datetime.now()
        await db._fetch_one("SELECT 1")
        ms = (datetime.now() - t0).total_seconds() * 1000
        checks["database"] = {"status": "ok", "latency_ms": round(ms, 1)}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}
        overall = "unhealthy"

    metrics_24h = await db.get_metrics_24h()

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": checks,
        "metrics": metrics_24h,
    }
