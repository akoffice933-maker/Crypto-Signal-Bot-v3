from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backtest"])

# Global state for backtest results
_backtest_results = None
_backtest_running = False
_backtest_status_message = ""
_backtest_active_config = None


def _model_to_dict(model: BaseModel) -> dict:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


class BacktestRunRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=1)
    candles: int = Field(default=8640, ge=500, le=50000)
    initial_balance: float = Field(default=10000.0, gt=0)
    max_position_pct: float = Field(default=0.10, gt=0, le=1.0)
    max_candles_hold: int = Field(default=20, ge=1, le=500)


async def _run_backtest_task(params: Optional[BacktestRunRequest] = None):
    """Run backtest in background."""
    global _backtest_results, _backtest_running, _backtest_status_message, _backtest_active_config

    params = params or BacktestRunRequest()
    client = None
    try:
        _backtest_running = True
        _backtest_status_message = f"Backtest started for {params.symbol} ({params.candles} candles)"
        _backtest_active_config = _model_to_dict(params)
        logger.info(
            "Starting backtest for %s with %s candles",
            params.symbol,
            params.candles,
        )
        
        # Import backtester
        from backtesting.backtester import Backtester, BTConfig
        from data.binance_client import BinanceFuturesClient, KLINE_COLS
        from config.settings import settings
        import pandas as pd
        
        # Load candles - use testnet for backtesting to avoid 451 errors
        base_url = "https://testnet.binancefuture.com" if settings.testnet else "https://fapi.binance.com"
        logger.info(f"Using Binance API: {base_url}")
        
        client = BinanceFuturesClient(base_url)
        import math

        candles_4h = max(60, int(math.ceil(params.candles / 16)) + 10)
        candles_1d = max(30, int(math.ceil(params.candles / 96)) + 5)

        raw_15m = await client.get_historical_klines(params.symbol, "15m", total_limit=params.candles)
        raw_4h = await client.get_historical_klines(params.symbol, "4h", total_limit=candles_4h)
        raw_1d = await client.get_historical_klines(params.symbol, "1d", total_limit=candles_1d)
        if not raw_15m:
            raise RuntimeError("No candles returned for backtest request")

        # Run backtest
        bt = Backtester(BTConfig(
            initial_balance=params.initial_balance,
            fee_pct=0.0004,
            slippage_pct=0.0008,
            max_position_pct=params.max_position_pct,
            min_rr=None,
            confidence_min=None,
            max_candles_hold=params.max_candles_hold,
            execution_basis=settings.execution_basis,
        ))

        def parse_rows(raw_rows):
            df = pd.DataFrame(raw_rows, columns=KLINE_COLS)
            for c in ("open", "high", "low", "close", "volume"):
                df[c] = df[c].astype(float)
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            return df

        results = bt.run({
            "15m": parse_rows(raw_15m),
            "4h": parse_rows(raw_4h),
            "1d": parse_rows(raw_1d),
        })
        
        _backtest_results = {
            "status": "completed",
            "metrics": results,
            "config": _model_to_dict(params),
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
        _backtest_status_message = ""
        _backtest_active_config = None
        if client and hasattr(client, '_session') and client._session and not client._session.closed:
            await client.close()
            logger.info("Backtest: Binance client session closed")


@router.post("/backtest/run")
async def run_backtest(background_tasks: BackgroundTasks, payload: Optional[BacktestRunRequest] = None):
    """Start a backtest run in the background."""
    global _backtest_running
    
    if _backtest_running:
        raise HTTPException(status_code=400, detail="Backtest already running")
    
    payload = payload or BacktestRunRequest()
    background_tasks.add_task(_run_backtest_task, payload)
    
    return {
        "status": "started",
        "message": f"Backtest started in background for {payload.symbol} ({payload.candles} candles)",
    }


@router.get("/backtest/results")
async def get_backtest_results():
    """Get the latest backtest results."""
    global _backtest_results, _backtest_running, _backtest_status_message, _backtest_active_config

    if _backtest_running and _backtest_results is None:
        return {
            "status": "running",
            "message": _backtest_status_message or "Backtest in progress...",
            "config": _backtest_active_config or {},
        }

    if _backtest_running:
        metrics = _backtest_results.get("metrics", {}) if _backtest_results else {}
        trades = metrics.get("trades", [])
        return {
            "status": "running",
            "message": _backtest_status_message or "Backtest in progress...",
            "config": _backtest_active_config or _backtest_results.get("config", {}),
            "total_trades": metrics.get("total_trades", 0),
            "total_return_pct": metrics.get("total_return_pct", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "winrate_pct": metrics.get("winrate_pct", 0),
            "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
            "avg_rr": metrics.get("avg_rr", 0),
            "tp1_hits": metrics.get("tp1_hits", 0),
            "full_tp_hits": metrics.get("full_tp_hits", 0),
            "sl_hits": metrics.get("sl_hits", 0),
            "timeout_hits": metrics.get("timeout_hits", 0),
            "exits": metrics.get("exits", {}),
            "trades": trades[-50:] if trades else [],
            "has_previous_results": bool(_backtest_results and _backtest_results.get("status") == "completed"),
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
        "config": _backtest_results.get("config", {}),
        "total_trades": metrics.get("total_trades", 0),
        "total_return_pct": metrics.get("total_return_pct", 0),
        "profit_factor": metrics.get("profit_factor", 0),
        "winrate_pct": metrics.get("winrate_pct", 0),
        "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
        "avg_rr": metrics.get("avg_rr", 0),
        "tp1_hits": metrics.get("tp1_hits", 0),
        "full_tp_hits": metrics.get("full_tp_hits", 0),
        "sl_hits": metrics.get("sl_hits", 0),
        "timeout_hits": metrics.get("timeout_hits", 0),
        "exits": metrics.get("exits", {}),
        "trades": trades[-50:] if trades else [],  # Last 50 trades
    }


@router.get("/backtest/status")
async def backtest_status():
    """Get current backtest status."""
    global _backtest_running, _backtest_results, _backtest_status_message, _backtest_active_config
    
    return {
        "running": _backtest_running,
        "has_results": _backtest_results is not None,
        "message": _backtest_status_message if _backtest_running else "",
        "config": _backtest_active_config or {},
    }
