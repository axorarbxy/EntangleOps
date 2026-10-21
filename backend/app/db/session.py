from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, TypeVar

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

T = TypeVar("T")


def redact_dsn(url: str | URL) -> str:
    parsed = url if isinstance(url, URL) else make_url(url)
    return parsed.render_as_string(hide_password=True)


def resolve_url(raw: str, password_file: str = "") -> URL:
    url = make_url(raw)
    if password_file:
        url = url.set(password=Path(password_file).read_text(encoding="utf-8").strip())
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return url


def make_engine(url: URL, *, pool_size: int = 5, max_overflow: int = 5,
                pool_timeout_s: int = 10, pool_recycle_s: int = 1800,
                statement_timeout_ms: int = 5000, echo: bool = False) -> Engine:
    backend = url.get_backend_name()
    options = {"hide_parameters": True, "echo": echo, "future": True}
    if backend == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 10}
        if url.database in (None, "", ":memory:"):
            options["poolclass"] = StaticPool
    else:
        options.update(pool_size=pool_size, max_overflow=max_overflow,
                       pool_timeout=pool_timeout_s, pool_recycle=pool_recycle_s,
                       pool_pre_ping=True)
        options["connect_args"] = {"options": f"-c statement_timeout={int(statement_timeout_ms)} -c idle_in_transaction_session_timeout=15000 -c timezone=UTC"}
    engine = create_engine(url, **options)
    if backend == "sqlite":
        @event.listens_for(engine, "connect")
        def sqlite_pragmas(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def run_db(fn: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)
