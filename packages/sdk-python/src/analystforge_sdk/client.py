"""Typed HTTP client for the public AnalystForge API (Phase 10)."""

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

    # Core metadata & health
    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health")

    def meta(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/meta")

    # Equities & Financials
    def get_company(self, ticker: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/companies/{ticker}")

    def get_prices(self, ticker: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.request("GET", f"/api/v1/companies/{ticker}/prices", params=params)

    # Screener
    def run_screener(self, criteria: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/v1/screener/run", json=criteria)

    # Macro & FX
    def get_yield_curve(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/macro/yield-curve")

    def get_fx_rates(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/v1/macro/fx")

    # Backtesting
    def run_backtest(
        self,
        ticker: str,
        strategy: str = "SMA_CROSSOVER",
        start_date: str = "2024-01-01",
        end_date: str = "2024-11-01",
        initial_capital: float = 100_000.0,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "strategy_name": strategy,
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "parameters": parameters or {},
        }
        return self.request("POST", "/api/v1/backtest/run", json=payload)

    # Grounded Research & RAG
    def query_research(self, query: str, ticker: str | None = None) -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/v1/research/query",
            json={"query": query, "ticker": ticker},
        )

    # Reporting
    def generate_report(
        self,
        title: str,
        report_type: str = "TEARSHEET",
        ticker: str | None = None,
        format: str = "MARKDOWN",
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "report_type": report_type,
            "ticker": ticker,
            "format": format,
            "parameters": parameters or {},
        }
        return self.request("POST", "/api/v1/reports/generate", json=payload)

    def list_reports(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/v1/reports")

    def download_report(self, report_id: str, format: str | None = None) -> bytes:
        params: dict[str, Any] = {}
        if format:
            params["format"] = format
        response = self._client.get(f"/api/v1/reports/{report_id}/download", params=params)
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
        return response.content

    def email_report(self, report_id: str, recipient_email: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/v1/reports/{report_id}/email",
            json={"recipient_email": recipient_email},
        )

    # Valuation & Portfolio
    def get_valuation(self, ticker: str, wacc: float = 0.09, terminal_growth: float = 0.025) -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/v1/valuation/dcf",
            json={"ticker": ticker, "wacc": wacc, "terminal_growth_rate": terminal_growth},
        )

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/portfolios/{portfolio_id}")

    # News & Filings
    def get_filings(self, ticker: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/v1/filings", params={"ticker": ticker})

    def get_news(self, ticker: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/v1/news", params={"ticker": ticker})

    def integrations_meta(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/meta/integrations")

