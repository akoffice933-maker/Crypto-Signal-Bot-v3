"""
Replay results viewer — displays parameter sweep comparison results.
"""

import csv
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from database.db import Database
from web.dependencies import get_db

router = APIRouter(prefix="/replay", tags=["replay"])

_RESULTS_DIR = Path("results")


def _round_or_none(value, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


@router.get("/")
async def replay_page():
    """Serve the replay results HTML page."""
    html_path = Path(__file__).parent.parent / "static" / "replay.html"
    if not html_path.exists():
        return {"error": "Replay page not found"}
    return FileResponse(html_path)


@router.get("/comparison")
async def replay_comparison(
    pair: Optional[str] = None,
    limit: int = Query(default=50, le=500),
):
    """
    Get replay comparison results from CSV files.
    Returns the most recent replay_comparison_*.csv file.
    """
    if not _RESULTS_DIR.exists():
        return []
    
    # Find the most recent comparison file
    files = sorted(_RESULTS_DIR.glob("replay_comparison_*.csv"), reverse=True)
    if not files:
        return []
    
    latest_file = files[0]
    results = []
    
    with open(latest_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            if pair and row.get("experiment") != pair:
                continue
            
            # Convert numeric fields
            for key in ["expectancy", "profit_factor", "sl_rate", "timeout_rate", 
                       "full_tp_rate", "tp1_hit_rate", "avg_mfe_pct", "avg_mae_pct", 
                       "mfe_mae_ratio", "timeout_pnl_median"]:
                try:
                    val = row.get(key, "")
                    row[key] = float(val) if val and val not in ("", "inf") else None
                except (ValueError, TypeError):
                    row[key] = None
            
            for key in ["signals_processed", "validated", "timeout_candles"]:
                try:
                    val = row.get(key, "")
                    row[key] = int(val) if val else None
                except (ValueError, TypeError):
                    row[key] = None
            
            results.append(row)
    
    return results


@router.get("/summary")
async def replay_summary(db: Database = Depends(get_db)):
    """Get replay results summary from database."""
    rows = await db._fetch("""
        SELECT 
            config_id,
            COUNT(*) as signals_count,
            AVG(CASE WHEN validation_status = 'validated' THEN 1 ELSE 0 END) * 100 as validation_rate,
            AVG(CASE WHEN validation_status = 'validated' THEN pnl_pct ELSE NULL END) as avg_pnl,
            AVG(mfe_pct) as avg_mfe,
            AVG(mae_pct) as avg_mae,
            AVG(mfe_mae_ratio) as avg_mfe_mae_ratio,
            SUM(CASE WHEN exit_type_detail = 'sl' THEN 1 ELSE 0 END) as sl_count,
            SUM(CASE WHEN exit_type_detail IN ('tp2', 'partial_tp1_tp2') THEN 1 ELSE 0 END) as tp_count,
            SUM(CASE WHEN exit_type_detail LIKE '%timeout%' THEN 1 ELSE 0 END) as timeout_count
        FROM signal_replay_results
        GROUP BY config_id
        ORDER BY signals_count DESC
        LIMIT 20
    """)
    
    results = []
    for row in rows or []:
        (config_id, signals_count, validation_rate, avg_pnl, 
         avg_mfe, avg_mae, avg_mfe_mae_ratio, sl_count, tp_count, timeout_count) = row
        
        results.append({
            "config_id": config_id,
            "signals_count": signals_count or 0,
            "validation_rate": round(validation_rate or 0, 1),
            "avg_pnl": round(avg_pnl or 0, 4) if avg_pnl else None,
            "avg_mfe": round(avg_mfe or 0, 4) if avg_mfe else None,
            "avg_mae": round(avg_mae or 0, 4) if avg_mae else None,
            "avg_mfe_mae_ratio": round(avg_mfe_mae_ratio or 0, 2) if avg_mfe_mae_ratio else None,
            "sl_count": sl_count or 0,
            "tp_count": tp_count or 0,
            "timeout_count": timeout_count or 0,
        })
    
    return results


@router.get("/signals")
async def replay_signals(
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_db),
):
    """List recent replayed signal IDs with config counts."""
    rows = await db._fetch(
        """
        SELECT
            signal_id,
            MAX(created_at) AS created_at,
            MAX(pair) AS pair,
            MAX(strategy) AS strategy,
            MAX(direction) AS direction,
            COUNT(*) AS rows_count,
            COUNT(DISTINCT config_id) AS config_count
        FROM signal_replay_results
        GROUP BY signal_id
        ORDER BY MAX(validated_at) DESC
        LIMIT ?
        """,
        (limit,),
    )

    results = []
    for row in rows or []:
        signal_id, created_at, pair, strategy, direction, rows_count, config_count = row
        results.append(
            {
                "signal_id": signal_id,
                "created_at": created_at,
                "pair": pair,
                "strategy": strategy,
                "direction": direction,
                "rows_count": rows_count or 0,
                "config_count": config_count or 0,
            }
        )
    return results


@router.get("/signal/{signal_id}")
async def replay_signal_detail(signal_id: str, db: Database = Depends(get_db)):
    """Return all replay rows for one signal_id across config_id values."""
    rows = await db._fetch(
        """
        SELECT
            signal_id,
            created_at,
            pair,
            strategy,
            direction,
            config_id,
            execution_basis,
            entry_market,
            entry_limit,
            fill_price,
            stop_loss,
            tp1_price,
            take_profit,
            rr_ratio,
            rr_achieved,
            pnl_pct,
            validation_status,
            exit_reason,
            exit_type_detail,
            tp1_hit,
            final_tp_hit,
            sl_hit,
            timeout_hit,
            mfe_pct,
            mae_pct,
            mfe_mae_ratio
        FROM signal_replay_results
        WHERE signal_id = ?
        ORDER BY config_id
        """,
        (signal_id,),
    )

    if not rows:
        return {"signal_id": signal_id, "rows": []}

    results = []
    for row in rows:
        (
            signal_id_value,
            created_at,
            pair,
            strategy,
            direction,
            config_id,
            execution_basis,
            entry_market,
            entry_limit,
            fill_price,
            stop_loss,
            tp1_price,
            take_profit,
            rr_ratio,
            rr_achieved,
            pnl_pct,
            validation_status,
            exit_reason,
            exit_type_detail,
            tp1_hit,
            final_tp_hit,
            sl_hit,
            timeout_hit,
            mfe_pct,
            mae_pct,
            mfe_mae_ratio,
        ) = row
        results.append(
            {
                "signal_id": signal_id_value,
                "created_at": created_at,
                "pair": pair,
                "strategy": strategy,
                "direction": direction,
                "config_id": config_id,
                "execution_basis": execution_basis,
                "entry_market": _round_or_none(entry_market, 2),
                "entry_limit": _round_or_none(entry_limit, 2),
                "fill_price": _round_or_none(fill_price, 2),
                "stop_loss": _round_or_none(stop_loss, 2),
                "tp1_price": _round_or_none(tp1_price, 2),
                "take_profit": _round_or_none(take_profit, 2),
                "rr_ratio": _round_or_none(rr_ratio, 2),
                "rr_achieved": _round_or_none(rr_achieved, 2),
                "pnl_pct": _round_or_none(pnl_pct, 4),
                "validation_status": validation_status,
                "exit_reason": exit_reason,
                "exit_type_detail": exit_type_detail,
                "tp1_hit": int(tp1_hit or 0),
                "final_tp_hit": int(final_tp_hit or 0),
                "sl_hit": int(sl_hit or 0),
                "timeout_hit": int(timeout_hit or 0),
                "mfe_pct": _round_or_none(mfe_pct, 4),
                "mae_pct": _round_or_none(mae_pct, 4),
                "mfe_mae_ratio": _round_or_none(mfe_mae_ratio, 2),
            }
        )

    return {"signal_id": signal_id, "rows": results}


@router.get("/export")
async def export_replay():
    """Export replay comparison as CSV."""
    files = sorted(_RESULTS_DIR.glob("replay_comparison_*.csv"), reverse=True)
    if not files:
        return {"error": "No replay comparison files found"}
    
    return FileResponse(
        files[0],
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=replay_comparison.csv"}
    )
