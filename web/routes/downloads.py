from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from config.settings import settings


router = APIRouter(tags=["downloads"])

_RESULTS_DIR = Path("results").resolve()


@router.get("/downloads/{filename}")
async def download_result_file(filename: str, token: str = Query(default="")):
    expected_token = settings.download_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="DOWNLOAD_TOKEN is not configured")
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid download token")

    safe_name = Path(filename).name
    file_path = (_RESULTS_DIR / safe_name).resolve()
    if file_path.parent != _RESULTS_DIR:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)
