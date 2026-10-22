"""Apply the configured database migrations through the shared DB helper."""

from app.config import settings
from app.db.migrate import schema_state, upgrade_to_head
from app.db.session import make_engine, resolve_url


def main() -> None:
    url = settings.migration_database_url.get_secret_value()
    password_file = settings.migration_password_file
    if not url:
        raise RuntimeError("EO_MIGRATION_DATABASE_URL must be configured for the migration job")

    engine = make_engine(resolve_url(url, password_file))
    try:
        upgrade_to_head(engine)
        current, head = schema_state(engine)
        if current != head:
            raise RuntimeError(f"Database migration incomplete: current={current!r}, head={head!r}")
        print(f"Database schema is at migration head {head}.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
