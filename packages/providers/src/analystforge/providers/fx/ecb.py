"""European Central Bank euro reference rates adapter.

Downloads the published historical archive and extracts the requested quote
currencies. Rates are stored with EUR as the base; cross rates are derived by
the portfolio layer. Missing quotes (``N/A``) are skipped, not zero-filled.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation

from analystforge.providers.base import FxProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import FxRate

_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
_CACHE_TTL_SECONDS = 24 * 3600.0
_ARCHIVE_MEMBER = "eurofxref-hist.csv"


class EcbFxProvider(FxProvider):
    name = "ecb"

    def __init__(
        self,
        *,
        user_agent: str,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client = ProviderHttpClient(
            self.name,
            user_agent=user_agent,
            cache=cache,
            timeout_seconds=timeout_seconds,
            min_interval_seconds=1.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_rates(self, start: date, end: date, currencies: list[str]) -> list[FxRate]:
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")
        wanted = {currency.upper() for currency in currencies}
        if not wanted:
            raise ProviderDataError(self.name, "no currencies requested")
        payload = await self._client.get_bytes(_URL, ttl_seconds=_CACHE_TTL_SECONDS)
        return self._parse(payload, start, end, wanted)

    def _parse(self, payload: bytes, start: date, end: date, wanted: set[str]) -> list[FxRate]:
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if _ARCHIVE_MEMBER not in archive.namelist():
                    raise ProviderDataError(self.name, f"archive is missing {_ARCHIVE_MEMBER}")
                text = archive.read(_ARCHIVE_MEMBER).decode("utf-8")
        except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
            raise ProviderDataError(self.name, "invalid ECB archive") from exc
        reader = csv.DictReader(io.StringIO(text))
        rates: list[FxRate] = []
        for row_number, row in enumerate(reader, start=2):
            raw_date = (row.get("Date") or "").strip()
            if not raw_date:
                continue
            try:
                day = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ProviderDataError(self.name, f"invalid date on row {row_number}") from exc
            if day < start or day > end:
                continue
            for quote in sorted(wanted):
                raw = (row.get(quote) or "").strip()
                if raw in {"", "N/A"}:
                    continue
                try:
                    value = Decimal(raw)
                except InvalidOperation as exc:
                    raise ProviderDataError(
                        self.name, f"invalid {quote} rate on row {row_number}"
                    ) from exc
                rates.append(FxRate(day=day, base="EUR", quote=quote, rate=value))
        if not rates:
            raise ProviderDataError(self.name, "no ECB rates in the requested range")
        rates.sort(key=lambda rate: (rate.day, rate.quote))
        return rates
