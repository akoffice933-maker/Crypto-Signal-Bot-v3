from pathlib import Path

from fastapi.responses import FileResponse


_DASHBOARD_PATH = Path(__file__).parent / "static" / "dashboard.html"


async def dashboard():
    return FileResponse(_DASHBOARD_PATH)
