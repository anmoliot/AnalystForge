"""Async database engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs.pop("pool_pre_ping")
            if ":memory:" in url:
                from sqlalchemy.pool import StaticPool

                kwargs["poolclass"] = StaticPool
                kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_size"] = 10
            kwargs["max_overflow"] = 20
            kwargs["pool_recycle"] = 1800
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
