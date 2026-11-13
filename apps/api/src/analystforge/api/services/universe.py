"""Curated instrument universe: loading, validation and idempotent seeding."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.market import (
    Exchange,
    Instrument,
    InstrumentProviderSymbol,
)

UNIVERSE_PACKAGE = "analystforge.api.data"
UNIVERSE_FILE = "universe.json"


class UniverseExchange(BaseModel):
    code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=1, max_length=120)
    mic: str | None = Field(default=None, max_length=16)
    country: str = Field(min_length=2, max_length=2)
    timezone: str
    currency: str = Field(min_length=3, max_length=8)


class UniverseInstrument(BaseModel):
    exchange: str
    ticker: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    asset_type: str = "equity"
    currency: str = Field(min_length=3, max_length=8)
    cik: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    symbols: dict[str, str]

    @model_validator(mode="after")
    def _check_symbols(self) -> UniverseInstrument:
        if not self.symbols:
            raise ValueError(f"{self.ticker}: at least one provider symbol is required")
        for provider, symbol in self.symbols.items():
            if not provider.strip() or not symbol.strip():
                raise ValueError(f"{self.ticker}: provider symbols must be non-empty")
        if self.cik is not None and (not self.cik.isdigit() or len(self.cik) != 10):
            raise ValueError(f"{self.ticker}: CIK must be 10 digits")
        return self


class Universe(BaseModel):
    schema_version: int
    description: str | None = None
    exchanges: list[UniverseExchange]
    instruments: list[UniverseInstrument]

    @model_validator(mode="after")
    def _check_integrity(self) -> Universe:
        exchange_codes = [exchange.code for exchange in self.exchanges]
        if len(exchange_codes) != len(set(exchange_codes)):
            raise ValueError("duplicate exchange codes in universe")
        known = set(exchange_codes)
        pairs: set[tuple[str, str]] = set()
        seen_symbols: dict[str, set[str]] = {}
        for instrument in self.instruments:
            if instrument.exchange not in known:
                raise ValueError(f"{instrument.ticker}: unknown exchange {instrument.exchange!r}")
            pair = (instrument.exchange, instrument.ticker)
            if pair in pairs:
                raise ValueError(f"duplicate instrument {pair}")
            pairs.add(pair)
            for provider, symbol in instrument.symbols.items():
                used = seen_symbols.setdefault(provider, set())
                if symbol in used:
                    raise ValueError(f"duplicate {provider} symbol {symbol!r}")
                used.add(symbol)
        return self


def load_universe() -> Universe:
    resource = files(UNIVERSE_PACKAGE).joinpath(UNIVERSE_FILE)
    return Universe.model_validate_json(resource.read_text(encoding="utf-8"))


async def seed_reference_data(
    session: AsyncSession, universe: Universe | None = None
) -> dict[str, int]:
    """Upsert exchanges, instruments and provider symbols.

    Safe to run repeatedly: instruments are matched on (exchange, ticker) and
    provider symbols are replaced per instrument.
    """
    universe = universe or load_universe()
    counts = {
        "exchanges_created": 0,
        "exchanges_updated": 0,
        "instruments_created": 0,
        "instruments_updated": 0,
        "provider_symbols": 0,
    }

    existing_exchanges = {
        exchange.code: exchange for exchange in (await session.scalars(select(Exchange))).all()
    }
    for spec in universe.exchanges:
        current = existing_exchanges.get(spec.code)
        if current is None:
            session.add(
                Exchange(
                    code=spec.code,
                    name=spec.name,
                    mic=spec.mic,
                    country=spec.country,
                    timezone=spec.timezone,
                    currency=spec.currency,
                )
            )
            counts["exchanges_created"] += 1
            continue
        values = spec.model_dump()
        if any(getattr(current, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(current, key, value)
            counts["exchanges_updated"] += 1
    await session.flush()

    existing_instruments = {
        (instrument.exchange_code, instrument.ticker): instrument
        for instrument in (await session.scalars(select(Instrument))).all()
    }
    instrument_ids: dict[tuple[str, str], Any] = {}
    for spec in universe.instruments:
        pair = (spec.exchange, spec.ticker)
        values: dict[str, Any] = {
            "exchange_code": spec.exchange,
            "ticker": spec.ticker,
            "name": spec.name,
            "asset_type": spec.asset_type,
            "currency": spec.currency,
            "cik": spec.cik,
            "sector": spec.sector,
            "industry": spec.industry,
            "description": spec.description,
            "is_active": True,
            "extra": {"universe": universe.description or "curated"},
        }
        current = existing_instruments.get(pair)
        if current is None:
            current = Instrument(**values)
            session.add(current)
            counts["instruments_created"] += 1
            existing_instruments[pair] = current
        else:
            changed = False
            for key, value in values.items():
                if getattr(current, key) != value:
                    setattr(current, key, value)
                    changed = True
            if changed:
                counts["instruments_updated"] += 1
        await session.flush()
        instrument_ids[pair] = current.id

    seeded_ids = list(instrument_ids.values())
    await session.execute(
        delete(InstrumentProviderSymbol).where(
            InstrumentProviderSymbol.instrument_id.in_(seeded_ids)
        )
    )
    await session.flush()
    for spec in universe.instruments:
        instrument_id = instrument_ids[(spec.exchange, spec.ticker)]
        for provider, symbol in spec.symbols.items():
            session.add(
                InstrumentProviderSymbol(
                    instrument_id=instrument_id, provider=provider, symbol=symbol
                )
            )
            counts["provider_symbols"] += 1
    await session.flush()
    return counts


async def provider_symbol_map(
    session: AsyncSession,
) -> dict[Any, dict[str, str]]:
    """Return ``instrument_id -> {provider: symbol}`` for active instruments."""
    symbols = (
        await session.execute(
            select(InstrumentProviderSymbol)
            .join(Instrument, Instrument.id == InstrumentProviderSymbol.instrument_id)
            .where(Instrument.is_active.is_(True))
        )
    ).scalars()
    result: dict[Any, dict[str, str]] = {}
    for symbol in symbols:
        result.setdefault(symbol.instrument_id, {})[symbol.provider] = symbol.symbol
    return result
