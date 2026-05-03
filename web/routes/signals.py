"""
Signals API and HTML page.
"""

from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, FileResponse

from database.db import Database
from web.dependencies import get_db
from web.services.signal_exports import render_signals_csv, sync_signals_to_google_sheets

router = APIRouter(prefix="/signals", tags=["signals"])

_SIGNALS_PAGE = Path(__file__).parent.parent / "static" / "signals.html"


@router.get("/")
async def signals_page():
    """Serve the signals HTML page."""
    if not _SIGNALS_PAGE.exists():
        return {"error": "Signals page not found"}
    return FileResponse(_SIGNALS_PAGE)


@router.get("/api")
async def list_signals(
    limit: int = Query(default=20, le=100),
    direction: Optional[str] = None,
    strategy: Optional[str] = None,
    pair: Optional[str] = None,
    db: Database = Depends(get_db),
):
    q = "SELECT id,created_at,direction,strategy,session,entry_market," \
        "entry_limit,stop_loss,tp1_price,take_profit,rr_ratio,rr_market,rr_limit,execution_basis,confidence_score," \
        "market_state,volatility_regime,target_liquidity_price," \
        "target_liquidity_tf,target_liquidity_type,cvd_divergence," \
        "funding_rate,squeeze_active,status,pair FROM signals WHERE 1=1"
    params = []
    if direction:
        q += " AND direction=?"; params.append(direction.upper())
    if strategy:
        q += " AND strategy=?"; params.append(strategy)
    if pair:
        q += " AND pair=?"; params.append(pair.upper())
    q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)

    cols = ["id","created_at","direction","strategy","session","entry_market",
            "entry_limit","stop_loss","tp1_price","take_profit","rr_ratio","rr_market","rr_limit","execution_basis","confidence_score",
            "market_state","volatility_regime","target_liquidity_price",
            "target_liquidity_tf","target_liquidity_type","cvd_divergence",
            "funding_rate","squeeze_active","status","pair"]
    rows = await db._fetch(q, tuple(params))
    return [dict(zip(cols, r)) for r in (rows or [])]


@router.get("/stats")
async def stats(
    pair: Optional[str] = None,
    db: Database = Depends(get_db),
):
    params = []
    pair_filter = ""
    if pair:
        pair_filter = " WHERE pair=?"
        params.append(pair.upper())
    
    row = await db._fetch_one(f"""
        SELECT COUNT(*),
               SUM(CASE WHEN direction='LONG' THEN 1 ELSE 0 END),
               SUM(CASE WHEN direction='SHORT' THEN 1 ELSE 0 END),
               AVG(confidence_score), AVG(rr_ratio),
               SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status='sl_hit' THEN 1 ELSE 0 END)
        FROM signals {pair_filter} WHERE created_at > datetime('now','-30 days')
    """, tuple(params))
    if not row or not row[0]:
        return {"message": "No signals in last 30 days"}
    total, longs, shorts, avg_conf, avg_rr, tp, sl = row
    closed = (tp or 0) + (sl or 0)
    return {
        "period": "last_30_days",
        "pair": pair.upper() if pair else "all",
        "total": total, "longs": longs, "shorts": shorts,
        "avg_confidence": round(avg_conf or 0, 1),
        "avg_rr": round(avg_rr or 0, 2),
        "tp_hits": tp or 0, "sl_hits": sl or 0,
        "winrate_pct": round((tp or 0) / closed * 100, 1) if closed else None,
    }


@router.get("/stats/by-pair")
async def stats_by_pair(db: Database = Depends(get_db)):
    """Get statistics breakdown by trading pair."""
    rows = await db._fetch("""
        SELECT 
            pair,
            COUNT(*) as total,
            SUM(CASE WHEN direction='LONG' THEN 1 ELSE 0 END) as longs,
            SUM(CASE WHEN direction='SHORT' THEN 1 ELSE 0 END) as shorts,
            AVG(confidence_score) as avg_confidence,
            AVG(rr_ratio) as avg_rr,
            SUM(CASE WHEN status='tp_hit' THEN 1 ELSE 0 END) as tp_hits,
            SUM(CASE WHEN status='sl_hit' THEN 1 ELSE 0 END) as sl_hits,
            SUM(CASE WHEN created_at > datetime('now','-24 hours') THEN 1 ELSE 0 END) as signals_24h
        FROM signals
        WHERE created_at > datetime('now','-7 days')
        GROUP BY pair
        ORDER BY total DESC
    """)
    
    result = {}
    for row in rows or []:
        pair, total, longs, shorts, avg_conf, avg_rr, tp, sl, signals_24h = row
        closed = (tp or 0) + (sl or 0)
        result[pair] = {
            "total": total or 0,
            "longs": longs or 0,
            "shorts": shorts or 0,
            "avg_confidence": round(avg_conf or 0, 1),
            "avg_rr": round(avg_rr or 0, 2),
            "tp_hits": tp or 0,
            "sl_hits": sl or 0,
            "winrate_pct": round((tp or 0) / closed * 100, 1) if closed else None,
            "signals_24h": signals_24h or 0,
        }
    return result


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
    pair: Optional[str] = None,
    db: Database = Depends(get_db),
):
    rows = await db.get_signals_for_export(limit=limit, direction=direction, strategy=strategy, pair=pair)
    csv_payload = render_signals_csv(rows)
    return PlainTextResponse(
        content=csv_payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="signals_export{f"_{pair.upper()}" if pair else ""}.csv"'},
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
