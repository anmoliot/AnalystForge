"""Twelve Data daily OHLCV price adapter.

Requires an API key (TWELVE_DATA_API_KEY). Supported as an official secondary
price source when configured, providing high-coverage US and international equities data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from analystforge.providers.base import PricesProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import (
    ProviderDataError,
    ProviderError,
    ProviderNotConfiguredError,
)
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import Bar, PriceSeries

_BASE_URL = "https://api.twelvedata.com/time_series"
_CACHE_TTL_SECONDS = 900.0


class TwelveDataPricesProvider(PricesProvider):
    name = "twelvedata"

    def __init__(
        self,
        *,
        user_agent: str,
        api_key: str | None = None,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key.strip() if api_key else None
        self._client = ProviderHttpClient(
            self.name,
            user_agent=user_agent,
            cache=cache,
            timeout_seconds=timeout_seconds,
            min_interval_seconds=0.8,
        )

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        if not self.is_configured():
            raise ProviderNotConfiguredError(
                self.name, "Twelve Data API key is not configured (TWELVE_DATA_API_KEY)"
            )
        clean_symbol = symbol.strip()
        if not clean_symbol:
            raise ProviderDataError(self.name, "empty symbol")
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")

        params = {
            "symbol": clean_symbol,
            "interval": "1day",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "outputsize": "5000",
            "apikey": self._api_key,
        }

        payload = await self._client.get_json(
            _BASE_URL,
            params=params,
            ttl_seconds=_CACHE_TTL_SECONDS,
        )
        return self._parse(clean_symbol, payload)

    def _parse(self, symbol: str, payload: Any) -> PriceSeries:
        if not isinstance(payload, dict):
            raise ProviderDataError(self.name, "response is not a valid JSON dictionary")

        # Twelve Data returns status="error" or HTTP 429
        status = payload.get("status")
        if status == "error":
            code = payload.get("code")
            msg = payload.get("message", "Unknown Twelve Data error")
            retryable = code == 429
            raise ProviderError(
                self.name, f"Twelve Data error ({code}): {msg}", retryable=retryable
            )

        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise ProviderDataError(self.name, f"no time series values returned for {symbol}")

        meta = payload.get("meta") or {}
        currency = meta.get("currency")
        exchange = meta.get("exchange")

        bars: list[Bar] = []
        for row in values:
            try:
                datetime_str = str(row.get("datetime", "")).strip()
                day = date.fromisoformat(datetime_str.split(" ")[0])
                open_ = Decimal(str(row.get("open", "0")).strip())
                high = Decimal(str(row.get("high", "0")).strip())
                low = Decimal(str(row.get("low", "0")).strip())
                close = Decimal(str(row.get("close", "0")).strip())
                vol_str = str(row.get("volume", "")).strip()
                vol = int(vol_str) if vol_str and vol_str != "0" else None
            except (InvalidOperation, ValueError):
                continue

            bars.append(
                Bar(
                    day=day,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=vol,
                )
            )

        bars.sort(key=lambda b: b.day)
        return PriceSeries(symbol=symbol, bars=bars, currency=currency, exchange=exchange)
