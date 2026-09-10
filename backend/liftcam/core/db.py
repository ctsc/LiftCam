"""SQLAlchemy engine/session factories: async for API, sync for worker."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from liftcam.core.settings import get_settings


class Base(DeclarativeBase):
    pass


def _to_async_url(url: str) -> str:
    """psycopg sync URLs become asyncpg URLs for the API engine."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def _to_sync_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


@lru_cache
def get_async_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(_to_async_url(settings.database_url), pool_pre_ping=True)


@lru_cache
def get_sync_engine() -> Engine:
    settings = get_settings()
    return create_engine(_to_sync_url(settings.database_direct_url), pool_pre_ping=True)


@lru_cache
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)


@lru_cache
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(), expire_on_commit=False)


async def async_session() -> AsyncIterator[AsyncSession]:
    session = get_async_sessionmaker()()
    try:
        yield session
    finally:
        await session.close()


def sync_session() -> Iterator[Session]:
    session = get_sync_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
