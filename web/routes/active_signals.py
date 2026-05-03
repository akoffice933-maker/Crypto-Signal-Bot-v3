"""
Active signals with real-time PnL tracking.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from database.db import Database
from web.dependencies import get_db

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/active")
async def active_signals(
    pair: Optional[str] = None,
    db: Database = Depends(get_db),
):
    """
    Get active (open) signals with current PnL.
    Active = status IN ('sent', 'partial_tp1')
    """
    params = []
    pair_filter = ""
    if pair:
        pair_filter = " AND pair=?"
        params.append(pair.upper())
    
    rows = await db._fetch(f"""
        SELECT 
            signal_id, created_at, pair, strategy, direction,
            entry_market, entry_limit, stop_loss, take_profit,
            tp1_price, tp1_size_pct, final_tp_size_pct,
            rr_ratio, confidence_score, status,
            position_size_pct
        FROM signals
        WHERE status IN ('sent', 'partial_tp1')
        {pair_filter}
        ORDER BY created_at DESC
        LIMIT 20
    """, tuple(params))
    
    results = []
    for row in rows or []:
        (signal_id, created_at, pair, strategy, direction,
         entry_market, entry_limit, stop_loss, take_profit,
         tp1_price, tp1_size_pct, final_tp_size_pct,
         rr_ratio, confidence_score, status, position_size_pct) = row
        
        # Calculate current PnL (mock - in production fetch current price)
        # For now, return signal data with PnL placeholders
        results.append({
            "signal_id": signal_id,
            "created_at": created_at,
            "pair": pair,
            "strategy": strategy,
            "direction": direction,
            "entry_price": entry_market,
            "entry_limit": entry_limit,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "tp1_price": tp1_price,
            "tp1_size_pct": tp1_size_pct,
            "final_tp_size_pct": final_tp_size_pct,
            "rr_ratio": rr_ratio,
            "confidence_score": confidence_score,
            "status": status,
            "position_size_pct": position_size_pct,
            # PnL fields (updated by frontend with current price)
            "current_price": None,
            "pnl_pct": None,
            "pnl_usd": None,
            "progress_to_tp": None,
            "distance_to_sl": None,
        })
    
    return results


@router.get("/active/price")
async def get_current_price(symbol: str):
    """
    Get current price for a symbol from Binance.
    Used for real-time PnL calculation.
    """
    import aiohttp
    
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.ok:
                    data = await resp.json()
                    return {
                        "symbol": symbol,
                        "price": float(data["price"]),
                        "timestamp": data.get("time"),
                    }
                else:
                    return {"error": f"Failed to fetch price: {resp.status}"}
    except Exception as e:
        return {"error": str(e)}
