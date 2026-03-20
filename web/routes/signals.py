from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from database.db import Database
from web.dependencies import get_db
from web.services.signal_exports import render_signals_csv, sync_signals_to_google_sheets

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/")
async def list_signals(
    limit: int = Query(default=20, le=100),
    direction: Optional[str] = None,
    strategy: Optional[str] = None,
    db: Database = Depends(get_db),
):
    q = "SELECT id,created_at,direction,strategy,session,entry_market," \
        "entry_limit,stop_loss,take_profit,rr_ratio,confidence_score," \
        "market_state,volatility_regime,target_liquidity_price," \
        "target_liquidity_tf,target_liquidity_type,cvd_divergence," \
        "funding_rate,squeeze_active,status FROM signals WHERE 1=1"
    params = []
    if direction:
        q += " AND direction=?"; params.append(direction.upper())
    if strategy:
        q += " AND strategy=?"; params.append(strategy)
    q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)

    cols = ["id","created_at","direction","strategy","session","entry_market",
            "entry_limit","stop_loss","take_profit","rr_ratio","confidence_score",
            "market_state","volatility_regime","target_liquidity_price",
            "target_liquidity_tf","target_liquidity_type","cvd_divergence",
            "funding_rate","squeeze_active","status"]
    rows = await db._fetch(q, tuple(params))
    return [dict(zip(cols, r)) for r in (rows or [])]


@router.get("/stats")
async def stats(db: Database = Depends(get_db)):
    row = await db._fetch_one("""
        SELECT COUNT(*),
               SUM(CASE WHEN direction='LONG' THEN 1 ELSE 0 END),
               SUM(CASE WHEN direction='SHORT' THEN 1 ELSE 0 END),
               AVG(confidence_score), AVG(rr_ratio),
               SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status='sl_hit' THEN 1 ELSE 0 END)
        FROM signals WHERE created_at > datetime('now','-30 days')
    """)
    if not row or not row[0]:
        return {"message": "No signals in last 30 days"}
    total, longs, shorts, avg_conf, avg_rr, tp, sl = row
    closed = (tp or 0) + (sl or 0)
    return {
        "period": "last_30_days",
        "total": total, "longs": longs, "shorts": shorts,
        "avg_confidence": round(avg_conf or 0, 1),
        "avg_rr": round(avg_rr or 0, 2),
        "tp_hits": tp or 0, "sl_hits": sl or 0,
        "winrate_pct": round((tp or 0) / closed * 100, 1) if closed else None,
    }


@router.get("/liquidity")
async def liquidity(
    min_strength: float = Query(default=3.0),
    current_price: Optional[float] = Query(default=None, gt=0),
    db: Database = Depends(get_db),
):
    rows = await db._fetch("""
        SELECT timeframe,pool_type,ROUND(price,2),touch_count,
               ROUND(strength,1),mitigated
        FROM liquidity_pools
        WHERE is_active=1 AND strength>=?
        ORDER BY strength DESC LIMIT 30
    """, (min_strength,))
    result = []
    for row in rows or []:
        item = dict(zip(
            ["timeframe", "pool_type", "price", "touch_count", "strength", "mitigated"],
            row,
        ))
        if current_price is None:
            item["distance_pct"] = None
        else:
            item["distance_pct"] = round(abs(item["price"] - current_price) / current_price * 100, 2)
        result.append(item)
    return result


@router.get("/export.csv")
async def export_csv(
    limit: int = Query(default=500, le=5000),
    direction: Optional[str] = None,
    strategy: Optional[str] = None,
    db: Database = Depends(get_db),
):
    rows = await db.get_signals_for_export(limit=limit, direction=direction, strategy=strategy)
    csv_payload = render_signals_csv(rows)
    return PlainTextResponse(
        content=csv_payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="signals_export.csv"'},
    )


@router.post("/export/google-sheets")
async def export_google_sheets(
    payload: Optional[dict] = Body(default=None),
    db: Database = Depends(get_db),
):
    payload = payload or {}
    limit = min(int(payload.get("limit", 500)), 5000)
    direction = payload.get("direction")
    strategy = payload.get("strategy")
    webhook_url = payload.get("webhook_url")
    rows = await db.get_signals_for_export(limit=limit, direction=direction, strategy=strategy)
    try:
        return await sync_signals_to_google_sheets(rows, webhook_url=webhook_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google Sheets sync failed: {e}") from e
