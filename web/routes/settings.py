from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter(tags=["ui"])

_SETTINGS_PATH = Path(__file__).parent.parent / "static" / "settings.html"


@router.get("/settings")
async def settings_page():
    return FileResponse(_SETTINGS_PATH)
