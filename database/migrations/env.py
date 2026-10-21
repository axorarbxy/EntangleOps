import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine

from app.config import settings
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import resolve_url

config = context.config
target_metadata = Base.metadata


def _url():
    raw = settings.migration_database_url.get_secret_value() or settings.database_url.get_secret_value()
    password_file = settings.migration_password_file if settings.migration_database_url.get_secret_value() else settings.database_password_file
    return resolve_url(raw, password_file)


def run_migrations_offline():
    context.configure(url=_url().render_as_string(hide_password=True), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection):
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(_url(), poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            conn.exec_driver_sql("SELECT pg_advisory_lock(727274)")
        try:
            _run(conn)
        finally:
            if conn.dialect.name == "postgresql":
                conn.exec_driver_sql("SELECT pg_advisory_unlock(727274)")
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
