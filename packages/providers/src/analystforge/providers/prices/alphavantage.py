"""Alpha Vantage daily OHLCV price adapter.

Requires an API key (ALPHA_VANTAGE_API_KEY). Supported as an official secondary
price source when configured, providing historical daily OHLCV and split/dividend adjustments.
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
from analystforge.providers.models import Bar, CorporateAction, PriceSeries

_BASE_URL = "https://www.alphavantage.co/query"
_CACHE_TTL_SECONDS = 900.0


class AlphaVantagePricesProvider(PricesProvider):
    name = "alphavantage"

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
            min_interval_seconds=1.2,  # Free tier pace limiter (5 requests/min)
        )

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        if not self.is_configured():
            raise ProviderNotConfiguredError(
                self.name, "Alpha Vantage API key is not configured (ALPHA_VANTAGE_API_KEY)"
            )
        clean_symbol = symbol.strip()
        if not clean_symbol:
            raise ProviderDataError(self.name, "empty symbol")
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")

        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": clean_symbol,
            "outputsize": "full",
            "apikey": self._api_key,
            "datatype": "json",
        }

        payload = await self._client.get_json(
            _BASE_URL,
            params=params,
            ttl_seconds=_CACHE_TTL_SECONDS,
        )
        return self._parse(clean_symbol, payload, start, end)

    def _parse(
        self, symbol: str, payload: Any, start: date, end: date
    ) -> PriceSeries:
        if not isinstance(payload, dict):
            raise ProviderDataError(self.name, "response is not a valid JSON dictionary")

        # Check for rate-limiting notices or API warnings
        if "Note" in payload:
            raise ProviderError(
                self.name, f"Alpha Vantage rate limit reached: {payload['Note']}", retryable=True
            )
        if "Information" in payload and "Time Series (Daily)" not in payload:
            raise ProviderError(
                self.name, f"Alpha Vantage info: {payload['Information']}", retryable=True
            )
        if "Error Message" in payload:
            raise ProviderDataError(self.name, f"Alpha Vantage error: {payload['Error Message']}")

        series_dict = payload.get("Time Series (Daily)")
        if not isinstance(series_dict, dict) or not series_dict:
            raise ProviderDataError(self.name, f"no daily price series found for {symbol}")

        bars: list[Bar] = []
        actions: list[CorporateAction] = []

        for date_str, daily_data in series_dict.items():
            try:
                day = date.fromisoformat(date_str)
            except ValueError:
                continue

            if not (start <= day <= end):
                continue

            try:
                open_ = Decimal(str(daily_data.get("1. open", "0")).strip())
                high = Decimal(str(daily_data.get("2. high", "0")).strip())
                low = Decimal(str(daily_data.get("3. low", "0")).strip())
                close = Decimal(str(daily_data.get("4. close", "0")).strip())
                adj_val = daily_data.get("5. adjusted close")
                adj_close = Decimal(str(adj_val).strip()) if adj_val is not None else None
                vol_str = str(daily_data.get("6. volume", "")).strip()
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
                    adjusted_close=adj_close,
                    volume=vol,
                )
            )

            # Check for dividend or split actions
            div_val = daily_data.get("7. dividend amount")
            if div_val:
                try:
                    div_amount = Decimal(str(div_val).strip())
                    if div_amount > Decimal("0"):
                        actions.append(
                            CorporateAction(
                                action_type="dividend",
                                ex_date=day,
                                amount=div_amount,
                            )
                        )
                except InvalidOperation:
                    pass

            split_val = daily_data.get("8. split coefficient")
            if split_val:
                try:
                    split_coef = Decimal(str(split_val).strip())
                    if split_coef != Decimal("1.0") and split_coef > Decimal("0"):
                        actions.append(
                            CorporateAction(
                                action_type="split",
                                ex_date=day,
                                ratio=split_coef,
                            )
                        )
                except InvalidOperation:
                    pass

        bars.sort(key=lambda b: b.day)
        return PriceSeries(symbol=symbol, bars=bars, actions=actions)
