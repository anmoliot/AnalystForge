"""Federal Reserve Economic Data (FRED) adapter.

Uses the public CSV download endpoint so macro ingestion works without an API
key. Missing observations are published by FRED as ``.``; they are preserved as
``None`` so charts show real gaps instead of interpolated values.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from analystforge.providers.base import MacroProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import MacroPoint, MacroSeries, MacroSeriesSpec

_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_CACHE_TTL_SECONDS = 6 * 3600.0


class FredProvider(MacroProvider):
    name = "fred"

    def __init__(
        self,
        *,
        user_agent: str,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = ProviderHttpClient(
            self.name,
            user_agent=user_agent,
            cache=cache,
            timeout_seconds=timeout_seconds,
            min_interval_seconds=0.5,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_series(self, spec: MacroSeriesSpec, start: date, end: date) -> MacroSeries:
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")
        text = await self._client.get_text(
            _URL,
            params={
                "id": spec.code,
                "cosd": start.isoformat(),
                "coed": end.isoformat(),
            },
            ttl_seconds=_CACHE_TTL_SECONDS,
        )
        return self._parse(spec, text)

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
