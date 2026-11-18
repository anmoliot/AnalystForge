"""Launch a loopback-only test API with an ephemeral database and recorded market data."""

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from sqlalchemy import select

from analystforge.api.db import Base, Database
from analystforge.api.models import FundamentalFact, Instrument, PriceBar
from analystforge.api.services.ingest import _fact_row, ingest_seed
from analystforge.providers.fundamentals.sec_edgar import _parse_facts

ROOT = Path(__file__).resolve().parents[2]


async def seed(url: str) -> None:
    db = Database(url)
    try:
        async with db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await ingest_seed(db)
        async with db.session() as session:
            instrument = (
                await session.scalars(select(Instrument).where(Instrument.ticker == "AAPL"))
            ).one()
            bars = json.loads((ROOT / "tests/e2e/fixtures/aapl-daily.json").read_text())
            for row in bars:
                for field in ("ts", "ingested_at"):
                    row[field] = datetime.fromisoformat(row[field])
                row["volume"] = int(row["volume"]) if row["volume"] is not None else None
                session.add(PriceBar(instrument_id=instrument.id, interval="1d", **row))
            recorded = ROOT / "packages/providers/tests/fixtures/sec_companyfacts_aapl.json"
            for fact in _parse_facts(json.loads(recorded.read_text())):
                session.add(
                    FundamentalFact(**_fact_row(instrument, fact, "sec_edgar", datetime.now(UTC)))
                )
    finally:
        await db.dispose()


def main() -> None:
    previous = Path.cwd()
    with TemporaryDirectory(prefix="analystforge-e2e-", ignore_cleanup_errors=True) as temp:
        os.chdir(temp)  # Keep the development .env and data directories out of this process.
        url = os.environ.get("TEST_DATABASE_URL") or (
            "sqlite+aiosqlite:///" + (Path(temp) / "test.sqlite3").as_posix()
        )
        if not url.startswith("sqlite") and not url.rsplit("/", 1)[-1].endswith("_test"):
            raise ValueError("Browser test PostgreSQL database name must end in _test.")
        os.environ.update(
            ENVIRONMENT="test",
            DATABASE_URL=url,
            SECRET_KEY=secrets.token_hex(32),
            REDIS_URL="",
            DEMO_MODE="false",
            EMAIL_ENABLED="false",
            LLM_PROVIDER="none",
            COOKIE_SECURE="false",
            RATE_LIMIT_PER_MINUTE="12000",
        )
        asyncio.run(seed(url))
        try:
            uvicorn.run(
                "analystforge.api.main:app",
                host="127.0.0.1",
                port=int(os.environ.get("TEST_PORT", "8765")),
                access_log=False,
            )
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    main()
