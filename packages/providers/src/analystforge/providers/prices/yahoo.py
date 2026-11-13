"""Yahoo Finance chart adapter (unofficial, no API key).

The chart endpoint returns daily OHLCV, adjusted closes and split/dividend
events for one symbol. It is used as the default price source because it covers
US, UK and German listings without credentials. Yahoo does not publish a
stability SLA; the Stooq adapter is retained as a fallback and every response
is cached.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from analystforge.providers.base import PricesProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError, ProviderError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import Bar, CorporateAction, PriceSeries

_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
_PATH = "/v8/finance/chart/{symbol}"
_CACHE_TTL_SECONDS = 900.0


class YahooPricesProvider(PricesProvider):
    name = "yahoo"

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
            min_interval_seconds=0.4,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        if not symbol.strip():
            raise ProviderDataError(self.name, "empty symbol")
        if start > end:
            raise ProviderDataError(self.name, "start date is after end date")
        params = {
            "period1": _epoch(start),
            "period2": _epoch(end + timedelta(days=1)),
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
        last_error: ProviderError | None = None
        for host in _HOSTS:
            try:
                payload = await self._client.get_json(
                    host + _PATH.format(symbol=symbol),
                    params=params,
                    ttl_seconds=_CACHE_TTL_SECONDS,
                )
                return self._parse(symbol, payload)
            except ProviderError as exc:
                last_error = exc
                continue
        assert last_error is not None
        raise last_error

    def _parse(self, symbol: str, payload: Any) -> PriceSeries:
        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not isinstance(chart, dict):
            raise ProviderDataError(self.name, "response is missing the chart object")
        error = chart.get("error")
        if error:
            raise ProviderDataError(self.name, f"Yahoo error: {error}")
        results = chart.get("result")
        if not isinstance(results, list) or not results:
            raise ProviderDataError(self.name, f"no chart result for {symbol}")
        result = results[0]
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quotes = indicators.get("quote") or [{}]
        quote = quotes[0] if quotes else {}
        adjusted_block = (indicators.get("adjclose") or [{}])[0]
        adjusted = adjusted_block.get("adjclose") or []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        if not timestamps:
            raise ProviderDataError(self.name, f"no timestamps for {symbol}")

        by_day: dict[date, Bar] = {}
        for index, epoch in enumerate(timestamps):
            values = [_at(series, index) for series in (opens, highs, lows, closes)]
            if any(value is None for value in values):
                continue
            open_, high, low, close = (Decimal(str(value)) for value in values)
            adjusted_value = _at(adjusted, index)
            volume = _at(volumes, index)
            day = datetime.fromtimestamp(int(epoch), tz=UTC).date()
            by_day[day] = Bar(
                day=day,
                open=open_,
                high=high,
                low=low,
                close=close,
                adjusted_close=(
                    Decimal(str(adjusted_value)) if adjusted_value is not None else None
                ),
                volume=int(volume) if volume is not None else None,
            )
        if not by_day:
            raise ProviderDataError(self.name, f"no usable bars for {symbol}")
        bars = [by_day[key] for key in sorted(by_day)]
        return PriceSeries(
            symbol=str(meta.get("symbol") or symbol),
            bars=bars,
            currency=_optional_str(meta.get("currency")),
            exchange=_optional_str(meta.get("exchangeName")),
            timezone=_optional_str(meta.get("exchangeTimezoneName")),
            actions=_parse_actions(result.get("events") or {}, self.name),
        )


def _epoch(day: date) -> int:
    return int(datetime.combine(day, time.min, tzinfo=UTC).timestamp())


def _at(series: list[Any], index: int) -> Any:
    return series[index] if index < len(series) else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _parse_actions(events: dict[str, Any], provider: str) -> list[CorporateAction]:
    actions: list[CorporateAction] = []
    for _key, event in (events.get("splits") or {}).items():
        try:
            day = datetime.fromtimestamp(int(event["date"]), tz=UTC).date()
            numerator = Decimal(str(event["numerator"]))
            denominator = Decimal(str(event["denominator"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        if denominator == 0:
            continue
        actions.append(
            CorporateAction(
                action_type="split",
                ex_date=day,
                ratio=numerator / denominator,
            )
        )
    for _key, event in (events.get("dividends") or {}).items():
        try:
            day = datetime.fromtimestamp(int(event["date"]), tz=UTC).date()
            amount = Decimal(str(event["amount"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        actions.append(CorporateAction(action_type="dividend", ex_date=day, amount=amount))
    actions.sort(key=lambda action: (action.ex_date, action.action_type))
    return actions
