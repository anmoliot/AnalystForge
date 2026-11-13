"""Stooq daily CSV adapter (unofficial fallback).

Stooq serves adjusted-for-splits daily OHLCV CSV without a key. It does not
provide an adjusted close or corporate-action events, and it may present a
JavaScript challenge to non-browser clients; when that happens the adapter
raises a data error and the router fails over. It is therefore a fallback
rather than the default.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from analystforge.providers.base import PricesProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import Bar, PriceSeries

_URL = "https://stooq.com/q/d/l/"
_CACHE_TTL_SECONDS = 3600.0


class StooqProvider(PricesProvider):
    name = "stooq"

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
            min_interval_seconds=1.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        if not symbol.strip():
            raise ProviderDataError(self.name, "empty symbol")
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")
        text = await self._client.get_text(
            _URL,
            params={
                "s": symbol,
                "i": "d",
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
            },
            ttl_seconds=_CACHE_TTL_SECONDS,
        )
        return self._parse(symbol, text)

    def _parse(self, symbol: str, text: str) -> PriceSeries:
        if not text.lstrip().startswith("Date,"):
            raise ProviderDataError(
                self.name,
                "response is not a Stooq CSV (the site may be presenting a browser challenge)",
            )
        reader = csv.DictReader(io.StringIO(text))
        bars: list[Bar] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(str(row["Date"]).strip())
                open_ = Decimal(str(row["Open"]).strip())
                high = Decimal(str(row["High"]).strip())
                low = Decimal(str(row["Low"]).strip())
                close = Decimal(str(row["Close"]).strip())
                raw_volume = str(row.get("Volume") or "").strip()
                volume = int(float(raw_volume)) if raw_volume else None
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                raise ProviderDataError(
                    self.name, f"malformed CSV row {line_number} for {symbol}"
                ) from exc
            bars.append(
                Bar(
                    day=day,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    adjusted_close=None,
                    volume=volume,
                )
            )
        if not bars:
            raise ProviderDataError(self.name, f"no bars for {symbol}")
        bars.sort(key=lambda bar: bar.day)
        return PriceSeries(symbol=symbol, bars=bars)
