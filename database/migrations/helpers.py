from alembic import op

APP_ROLE = "eo_app"


def audit_immutable_up():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE FUNCTION eo_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$")
        op.execute("CREATE TRIGGER trg_audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION eo_audit_immutable()")
        op.execute("CREATE TRIGGER trg_audit_log_no_truncate BEFORE TRUNCATE ON audit_log FOR EACH STATEMENT EXECUTE FUNCTION eo_audit_immutable()")
    else:
        op.execute("CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END")
        op.execute("CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END")


def audit_immutable_down():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_change ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS eo_audit_immutable()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_delete")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_update")


def grant_app(privileges: str, tables: list[str]):
    """Grant literal migration-owned objects only; never pass request data here."""
    if op.get_bind().dialect.name != "postgresql": return
    op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{APP_ROLE}') THEN GRANT {privileges} ON TABLE {', '.join(tables)} TO {APP_ROLE}; END IF; END $$;")


def grant_sequences():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{APP_ROLE}') THEN GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}; END IF; END $$;")
