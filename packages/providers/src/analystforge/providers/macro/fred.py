"""Federal Reserve Economic Data (FRED) adapter.

Supports both the official FRED JSON API (when FRED_API_KEY is configured) and the
public CSV download endpoint as a keyless fallback. Missing observations published as
``.'' are preserved as ``None`` so charts show real gaps rather than interpolated values.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from analystforge.providers.base import MacroProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import MacroPoint, MacroSeries, MacroSeriesSpec

_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_JSON_URL = "https://api.stlouisfed.org/fred/series/observations"
_CACHE_TTL_SECONDS = 6 * 3600.0


class FredProvider(MacroProvider):
    name = "fred"

    def __init__(
        self,
        *,
        user_agent: str,
        api_key: str | None = None,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("FRED_API_KEY") or None
        self._client = ProviderHttpClient(
            self.name,
            user_agent=user_agent,
            cache=cache,
            timeout_seconds=timeout_seconds,
            min_interval_seconds=0.5,
        )

    @property
    def api_key_configured(self) -> bool:
        return bool(self._api_key)

    def is_configured(self) -> bool:
        return True

    async def aclose(self) -> None:
        await self._client.aclose()

    async def check_reachability(self) -> tuple[bool, str | None]:
        """Verify reachability of the FRED service without exposing keys."""
        if not self._api_key:
            return False, "FRED API key not configured"
        try:
            data = await self._client.get_json(
                _JSON_URL,
                params={
                    "series_id": "DGS10",
                    "api_key": self._api_key,
                    "file_type": "json",
                    "limit": 1,
                },
                ttl_seconds=300,
            )
            if "observations" in data:
                return True, None
            return False, data.get("error_message", "Unexpected response structure from FRED API")
        except Exception as exc:
            logging.getLogger(__name__).warning("operation unavailable (%s)", type(exc).__name__)
            return False, str(exc)

    async def fetch_series(self, spec: MacroSeriesSpec, start: date, end: date) -> MacroSeries:
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")

        if self._api_key:
            try:
                data = await self._client.get_json(
                    _JSON_URL,
                    params={
                        "series_id": spec.code,
                        "api_key": self._api_key,
                        "file_type": "json",
                        "observation_start": start.isoformat(),
                        "observation_end": end.isoformat(),
                    },
                    ttl_seconds=_CACHE_TTL_SECONDS,
                )
                return self._parse_json(spec, data)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "operation unavailable (%s)", type(exc).__name__
                )
                # Graceful fallback to CSV endpoint if JSON endpoint fails
                pass

        text = await self._client.get_text(
            _CSV_URL,
            params={
                "id": spec.code,
                "cosd": start.isoformat(),
                "coed": end.isoformat(),
            },
            ttl_seconds=_CACHE_TTL_SECONDS,
        )
        return self._parse(spec, text)

    def _parse_json(self, spec: MacroSeriesSpec, data: dict[str, Any]) -> MacroSeries:
        observations = data.get("observations")
        if observations is None:
            raise ProviderDataError(
                self.name, f"response for {spec.code} missing observations list"
            )
        points: list[MacroPoint] = []
        for row in observations:
            raw_date = row.get("date")
            if not raw_date:
                continue
            try:
                day = date.fromisoformat(str(raw_date).strip())
            except ValueError as exc:
                raise ProviderDataError(
                    self.name, f"invalid date for {spec.code}: {raw_date}"
                ) from exc
            raw_val = row.get("value")
            if raw_val in {"", ".", None}:
                points.append(MacroPoint(day=day, value=None))
                continue
            try:
                value = Decimal(str(raw_val).strip())
            except InvalidOperation as exc:
                raise ProviderDataError(
                    self.name, f"invalid value for {spec.code}: {raw_val}"
                ) from exc
            points.append(MacroPoint(day=day, value=value))
        points.sort(key=lambda point: point.day)
        return MacroSeries(spec=spec, points=points)

    def _parse(self, spec: MacroSeriesSpec, text: str) -> MacroSeries:
        if not text.lstrip().startswith("observation_date"):
            raise ProviderDataError(
                self.name, f"response for {spec.code} is not a FRED CSV download"
            )
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if header is None or len(header) < 2:
            raise ProviderDataError(self.name, f"missing header for {spec.code}")
        points: list[MacroPoint] = []
        for row_number, row in enumerate(reader, start=2):
            if not row or not row[0].strip():
                continue
            try:
                day = date.fromisoformat(row[0].strip())
            except ValueError as exc:
                raise ProviderDataError(
                    self.name, f"invalid date on row {row_number} for {spec.code}"
                ) from exc
            raw = row[1].strip() if len(row) > 1 else ""
            if raw in {"", "."}:
                points.append(MacroPoint(day=day, value=None))
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise ProviderDataError(
                    self.name, f"invalid value on row {row_number} for {spec.code}"
                ) from exc
            points.append(MacroPoint(day=day, value=value))
        points.sort(key=lambda point: point.day)
        return MacroSeries(spec=spec, points=points)
