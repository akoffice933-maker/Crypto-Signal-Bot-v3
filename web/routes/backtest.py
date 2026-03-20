from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter(tags=["ui"])

_BACKTEST_PATH = Path(__file__).parent.parent / "static" / "backtest.html"


@router.get("/backtest")
async def backtest_page():
    return FileResponse(_BACKTEST_PATH)
