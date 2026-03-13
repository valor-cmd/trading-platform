import os
import secrets
import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_security_scheme = HTTPBearer(auto_error=False)

_API_SECRET = os.environ.get("API_SECRET_KEY", "")
_AUTH_ENABLED = bool(_API_SECRET)

PUBLIC_PATHS = {
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_scheme),
):
    if not _AUTH_ENABLED:
        return True

    path = request.url.path
    if path in PUBLIC_PATHS:
        return True

    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = credentials.credentials
    if not _constant_time_compare(token, _API_SECRET):
        logger.warning(f"Invalid auth attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=403, detail="Invalid credentials")

    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.now(timezone.utc).timestamp()

        if client_ip not in self._requests:
            self._requests[client_ip] = []

        self._requests[client_ip] = [
            ts for ts in self._requests[client_ip]
            if now - ts < self._window
        ]

        if len(self._requests[client_ip]) >= self._max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
            )

        self._requests[client_ip].append(now)
        return await call_next(request)


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def sanitize_key_for_log(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "..." + key[-4:]
