"""
Market data API for charts.
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from data.binance_client import BinanceFuturesClient
from config.settings import settings

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/candles")
async def get_candles(
    symbol: str = Query(..., description="Trading pair (e.g., BTCUSDT)"),
    interval: str = Query(default="15m", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(default=100, le=1000, description="Number of candles"),
):
    """
    Get OHLCV candles from Binance for chart display.
    Uses Lightweight Charts format.
    """
    client = BinanceFuturesClient(settings.base_url)
    
    try:
        klines = await client.get_klines(
            symbol=symbol.lower(),
            interval=interval,
            limit=limit,
        )
        
        if not klines:
            return []
        
        # Convert to Lightweight Charts format
        candles = []
        for k in klines:
            candles.append({
                "time": int(k[0]) // 1000,  # Unix timestamp in seconds
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        
        return candles
    finally:
        await client.close()


@router.get("/price")
async def get_price(symbol: str = Query(..., description="Trading pair")):
    """Get current price for a symbol."""
    import aiohttp
    
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.ok:
                    data = await resp.json()
                    return {
                        "symbol": data["symbol"],
                        "price": float(data["price"]),
                    }
                else:
                    raise HTTPException(status_code=resp.status, detail="Failed to fetch price")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/funding")
async def get_funding_rate(symbol: str = Query(..., description="Trading pair")):
    """Get current funding rate."""
    import aiohttp
    
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol.upper()}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.ok:
                    data = await resp.json()
                    return {
                        "symbol": data["symbol"],
                        "funding_rate": float(data.get("lastFundingRate", 0)),
                        "next_funding_time": data.get("nextFundingTime"),
                    }
                else:
                    raise HTTPException(status_code=resp.status, detail="Failed to fetch funding")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
