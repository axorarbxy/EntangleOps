from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory


def _config() -> Config:
    root = Path(__file__).resolve().parents[2]
    return Config(str(root / "database" / "alembic.ini"))


def upgrade_to_head(engine) -> None:
    cfg = _config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        if connection.dialect.name == "postgresql":
            # The runtime role checks the applied revision during startup.
            connection.exec_driver_sql("GRANT SELECT ON TABLE alembic_version TO eo_app")


def schema_state(engine) -> tuple[str | None, str]:
    cfg = _config()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    return current, head
