from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import os
import logging

logger = logging.getLogger(__name__)

API_KEY = os.getenv('API_KEY', None)
DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'

# Public endpoints that don't require auth
PUBLIC_PATHS = ['/health', '/docs', '/openapi.json', '/', '/metrics', '/favicon.ico']


async def auth_middleware(request: Request, call_next):
    # Skip auth for public endpoints
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    if request.url.path.startswith('/downloads/'):
        return await call_next(request)
    
    # Skip auth for WebSocket connections
    if request.url.path.startswith('/ws'):
        return await call_next(request)
    
    # DEV_MODE: Skip auth for local development (MUST NOT be used in production!)
    if DEV_MODE:
        logger.debug("DEV_MODE: Auth skipped")
        return await call_next(request)
    
    # Production: API_KEY MUST be set
    if not API_KEY:
        logger.error("🚨 API_KEY not set! Rejecting request! Set API_KEY in .env or use DEV_MODE=true for local dev")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "API_KEY not configured. Set API_KEY in .env or use DEV_MODE=true for local development."}
        )
    
    # Check API key
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != API_KEY:
        logger.warning(f"❌ Invalid API key from {request.client.host if request.client else 'unknown'}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid API key"}
        )
    
    return await call_next(request)
