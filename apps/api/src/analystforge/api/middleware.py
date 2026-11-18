"""Request ID propagation, security headers, access logging and metrics."""

from __future__ import annotations

import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from analystforge.api.logging import bind_request_context, clear_request_context, get_logger
from analystforge.api.metrics import HTTP_DURATION, HTTP_REQUESTS

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
logger = get_logger("http")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _route_label(request: Request) -> str:
    """Full path template, including the prefix FastAPI strips on included routers.

    Prometheus labels must not contain raw ids: every matched path parameter is
    replaced by its template name, and unmatched requests collapse to a sentinel
    so scanners cannot explode label cardinality.
    """
    route = request.scope.get("route")
    if route is None:
        return "<unmatched>"
    path = request.url.path
    for name, value in request.path_params.items():
        if value:
            path = path.replace(f"/{value}", "/{" + name + "}")
    return path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID, binds log context and records request metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        bind_request_context(request_id=request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = _route_label(request)
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route).observe(elapsed)
            logger.info(
                "request.completed",
                method=request.method,
                route=route,
                status=status_code,
                duration_ms=round(elapsed * 1000, 2),
                client=request.client.host if request.client else None,
            )
            clear_request_context()


class ResponseHeadersMiddleware(BaseHTTPMiddleware):
    """Adds request ID and security headers to every response, including errors."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex
        response.headers["X-Request-ID"] = request_id
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
