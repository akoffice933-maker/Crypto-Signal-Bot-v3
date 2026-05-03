import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from web.assets import FAVICON_ICO
from web.middleware import auth_middleware
from web.routes.health import router as health_router
from web.routes.logs import router as logs_router
from web.routes.metrics import router as metrics_router
from web.routes.signals import router as signals_router
from web.routes.ui import router as ui_router
from web.routes.settings import router as settings_router
from web.routes.settings_api import router as settings_api_router
from web.routes.backtest import router as backtest_router
from web.routes.backtest_api import router as backtest_api_router
from web.routes.downloads import router as downloads_router
from web.routes.replay import router as replay_router
from web.routes.active_signals import router as active_signals_router
from web.routes.market_data import router as market_data_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Crypto Signal Bot v3",
    version="3.0.0",
    lifespan=lifespan,
)

# Auth middleware
@app.middleware("http")
async def auth(request: Request, call_next):
    return await auth_middleware(request, call_next)

# CORS configuration
cors_origins_str = os.getenv("CORS_ORIGINS", "").strip()
if cors_origins_str:
    allow_origins = [origin.strip() for origin in cors_origins_str.split(",")]
else:
    # Default safe origins for local development
    allow_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(logs_router)
app.include_router(metrics_router)
app.include_router(signals_router)
app.include_router(ui_router)
app.include_router(settings_router)
app.include_router(settings_api_router, prefix="/signals")
app.include_router(backtest_router)
app.include_router(backtest_api_router)
app.include_router(downloads_router)
app.include_router(replay_router)
app.include_router(active_signals_router)
app.include_router(market_data_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard", status_code=307)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=FAVICON_ICO, media_type="image/x-icon")


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools_manifest():
    return JSONResponse(content={})
