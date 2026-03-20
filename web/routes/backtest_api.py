import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backtest"])

# Global state for backtest results
_backtest_results = None
_backtest_running = False


async def _run_backtest_task():
    """Run backtest in background."""
    global _backtest_results, _backtest_running
    
    try:
        _backtest_running = True
        logger.info("Starting backtest...")
        
        # Import backtester
        from backtesting.backtester import Backtester, BTConfig
        from data.binance_client import BinanceFuturesClient
        from engine.candle_loader import load_candles
        from config.settings import settings
        
        # Load candles - use testnet for backtesting to avoid 451 errors
        base_url = "https://testnet.binancefuture.com" if settings.testnet else "https://fapi.binance.com"
        logger.info(f"Using Binance API: {base_url}")
        
        client = BinanceFuturesClient(base_url)
        candles = await load_candles(client, "BTCUSDT", ["15m"])
        
        # Run backtest
        bt = Backtester(BTConfig(
            initial_balance=10000.0,
            fee_pct=0.0004,
            slippage_pct=0.0008,
            max_position_pct=0.10,
            min_rr=2.0,
            confidence_min=65,
        ))
        
        results = bt.run(candles["15m"])
        
        _backtest_results = {
            "status": "completed",
            "metrics": results,
            "message": f"Backtest completed with {results.get('total_trades', 0)} trades",
        }
        
        logger.info(f"Backtest completed: {results}")
        
    except Exception as e:
        logger.error(f"Backtest error: {e}", exc_info=True)
        _backtest_results = {
            "status": "error",
            "error": str(e),
        }
    finally:
        _backtest_running = False


@router.post("/backtest/run")
async def run_backtest(background_tasks: BackgroundTasks):
    """Start a backtest run in the background."""
    global _backtest_running
    
    if _backtest_running:
        raise HTTPException(status_code=400, detail="Backtest already running")
    
    background_tasks.add_task(_run_backtest_task)
    
    return {
        "status": "started",
        "message": "Backtest started in background",
    }


@router.get("/backtest/results")
async def get_backtest_results():
    """Get the latest backtest results."""
    global _backtest_results, _backtest_running
    
    if _backtest_running:
        return {
            "status": "running",
            "message": "Backtest in progress...",
        }
    
    if _backtest_results is None:
        return {
            "error": "No results yet",
            "message": "Run a backtest first",
        }
    
    if _backtest_results.get("status") == "error":
        return {
            "error": _backtest_results.get("error"),
        }
    
    metrics = _backtest_results.get("metrics", {})
    trades = metrics.get("trades", [])
    
    return {
        "status": "completed",
        "total_trades": metrics.get("total_trades", 0),
        "total_return_pct": metrics.get("total_return_pct", 0),
        "profit_factor": metrics.get("profit_factor", 0),
        "winrate_pct": metrics.get("winrate_pct", 0),
        "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
        "avg_rr": metrics.get("avg_rr", 0),
        "exits": metrics.get("exits", {}),
        "trades": trades[-50:] if trades else [],  # Last 50 trades
    }


@router.get("/backtest/status")
async def backtest_status():
    """Get current backtest status."""
    global _backtest_running
    
    return {
        "running": _backtest_running,
        "has_results": _backtest_results is not None,
    }
