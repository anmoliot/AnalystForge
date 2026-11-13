"""Consistent error envelope used by every API endpoint."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_required"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderUnavailableError(AppError):
    status_code = 503
    code = "provider_unavailable"


class DataUnavailableError(AppError):
    status_code = 424
    code = "data_unavailable"


def error_body(
    code: str,
    message: str,
    *,
    details: Any = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    body["error"]["request_id"] = request_id
    return body
