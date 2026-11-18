"""Record the outcome after the request session has finished its transaction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from analystforge.api.logging import get_logger
from analystforge.api.metrics import AUDIT_FAILURES
from analystforge.api.models.core import AuditLog

logger = get_logger("audit")


async def record_mutation(request: Request, status: int) -> None:
    state = request.state
    route = request.scope.get("route")
    tags = getattr(route, "tags", [])
    entity_type = getattr(state, "entity_type", None) or (tags[0] if tags else "request")
    entity_id = getattr(state, "entity_id", None)
    if entity_id is None:
        for name, value in reversed(request.path_params.items()):
            if name == "id" or name.endswith("_id"):
                try:
                    entity_id = str(uuid.UUID(str(value)))
                except ValueError:
                    continue
                break
    action = getattr(state, "audit_action", None) or getattr(route, "name", request.method)
    async with request.app.state.db.session() as session:
        session.add(
            AuditLog(
                actor_id=getattr(state, "actor_id", None),
                tenant_id=getattr(state, "tenant_id", None),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=getattr(state, "request_id", None),
                status_code=status,
                created_at=datetime.now(UTC),
            )
        )


class AuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            request = Request(scope)
            try:
                await record_mutation(request, status)
            except Exception as exc:
                AUDIT_FAILURES.inc()
                logger.error(
                    "audit.write_failed",
                    request_id=getattr(request.state, "request_id", None),
                    reason=type(exc).__name__,
                )
