"""Small, typed HTTP client for the public AnalystForge API."""

from __future__ import annotations

from typing import Any

import httpx


class AnalystForgeError(Exception):
    def __init__(self, status_code: int, code: str, message: str, request_id: str | None = None):
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id


class AnalystForgeClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        headers = {"User-Agent": "analystforge-py/0.1.0"}
        if api_key:
            headers["X-API-Key"] = api_key
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AnalystForgeClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                err = response.json().get("error", {})
            except ValueError:
                err = {}
            raise AnalystForgeError(
                response.status_code,
                err.get("code", "http_error"),
                err.get("message", response.text[:500]),
                err.get("request_id"),
            )
        if response.status_code == 204:
            return None
        return response.json()

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health")

    def meta(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/meta")
