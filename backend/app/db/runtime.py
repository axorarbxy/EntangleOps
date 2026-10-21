from app.config import settings
from app.db.migrate import schema_state, upgrade_to_head
from app.db.session import make_engine, make_session_factory, resolve_url


def open_database(*, migrate_development: bool = False):
    engine = make_engine(resolve_url(settings.database_url.get_secret_value(), settings.database_password_file),
        pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
        pool_timeout_s=settings.db_pool_timeout_s, pool_recycle_s=settings.db_pool_recycle_s,
        statement_timeout_ms=settings.db_statement_timeout_ms, echo=False)
    if migrate_development and settings.env != "production" and settings.db_auto_migrate:
        upgrade_to_head(engine)
    else:
        current, head = schema_state(engine)
        if current != head:
            engine.dispose()
            raise RuntimeError("database schema is not at head; run the migration command")
    return engine, make_session_factory(engine)
