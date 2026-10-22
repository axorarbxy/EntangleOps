"""Governed ML artifacts, experiments, and risk-policy support."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import NAMING_CONVENTION
from app.db.types import UTCDateTime
from database.migrations.helpers import grant_app

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
id_type = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade():
    for column in (
        sa.Column("format_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("profile", sa.String(32), nullable=False, server_default="baseline_v1"),
        sa.Column("feature_schema", sa.String(8), nullable=False, server_default="v1"),
        sa.Column("target_mode", sa.String(16), nullable=False, server_default="direct"),
        sa.Column("status", sa.String(12), nullable=False, server_default="candidate"),
        sa.Column("calibration", json_type), sa.Column("card", json_type),
    ):
        op.add_column("model_artifacts", column)
    op.execute("UPDATE model_artifacts SET status = CASE WHEN is_active THEN 'champion' ELSE 'retired' END")
    with op.batch_alter_table("model_artifacts", naming_convention=NAMING_CONVENTION) as batch:
        batch.create_check_constraint("feature_schema", "feature_schema IN ('v1','v2')")
        batch.create_check_constraint("target_mode", "target_mode IN ('direct','residual')")
        batch.create_check_constraint("status", "status IN ('candidate','champion','retired')")
        batch.create_check_constraint("active_is_champion", "NOT is_active OR status = 'champion'")
    # Existing checks were created by 0001 under the application's naming convention.
    # Preserve those already-expanded names during SQLite table recreation.
    run_naming = {**NAMING_CONVENTION, "ck": "%(constraint_name)s"}
    with op.batch_alter_table("runs", naming_convention=run_naming) as batch:
        batch.drop_constraint(op.f("ck_runs_policy"), type_="check")
        batch.create_check_constraint(op.f("ck_runs_policy"), "policy IN ('static_c','static_o','adaptive','adaptive_risk')")
    op.create_table("ml_experiments",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False), sa.Column("profile", sa.String(32)),
        sa.Column("model_id", id_type, sa.ForeignKey("model_artifacts.id", ondelete="SET NULL")),
        sa.Column("dataset_id", sa.String(32), sa.ForeignKey("datasets.id", ondelete="SET NULL")),
        sa.Column("config", json_type, nullable=False), sa.Column("metrics", json_type, nullable=False),
        sa.Column("slices", json_type), sa.Column("code_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('train','evaluation','tuning','ablation','policy_study','drift_baseline')", name="kind"))
    op.create_index("ix_ml_experiments_kind_created_at", "ml_experiments", ["kind", "created_at"])
    op.create_index("ix_ml_experiments_model_id", "ml_experiments", ["model_id"])
    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER trg_ml_experiments_no_update BEFORE UPDATE ON ml_experiments BEGIN SELECT RAISE(ABORT, 'ml_experiments is append-only'); END")
        op.execute("CREATE TRIGGER trg_ml_experiments_no_delete BEFORE DELETE ON ml_experiments BEGIN SELECT RAISE(ABORT, 'ml_experiments is append-only'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE FUNCTION eo_ml_experiments_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'ml_experiments is append-only'; END; $$")
        op.execute("CREATE TRIGGER trg_ml_experiments_no_change BEFORE UPDATE OR DELETE ON ml_experiments FOR EACH ROW EXECUTE FUNCTION eo_ml_experiments_immutable()")
        op.execute("CREATE TRIGGER trg_ml_experiments_no_truncate BEFORE TRUNCATE ON ml_experiments FOR EACH STATEMENT EXECUTE FUNCTION eo_ml_experiments_immutable()")
    grant_app("SELECT, INSERT", ["ml_experiments"])


def downgrade():
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM runs WHERE policy = 'adaptive_risk'")).scalar_one()
    if count:
        raise RuntimeError("cannot downgrade ML migration while adaptive_risk runs exist")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_ml_experiments_no_delete")
        op.execute("DROP TRIGGER IF EXISTS trg_ml_experiments_no_update")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_ml_experiments_no_truncate ON ml_experiments")
        op.execute("DROP TRIGGER IF EXISTS trg_ml_experiments_no_change ON ml_experiments")
        op.execute("DROP FUNCTION IF EXISTS eo_ml_experiments_immutable()")
    op.drop_index("ix_ml_experiments_model_id", table_name="ml_experiments")
    op.drop_index("ix_ml_experiments_kind_created_at", table_name="ml_experiments")
    op.drop_table("ml_experiments")
    run_naming = {**NAMING_CONVENTION, "ck": "%(constraint_name)s"}
    with op.batch_alter_table("runs", naming_convention=run_naming) as batch:
        batch.drop_constraint(op.f("ck_runs_policy"), type_="check")
        batch.create_check_constraint(op.f("ck_runs_policy"), "policy IN ('static_c','static_o','adaptive')")
    with op.batch_alter_table("model_artifacts", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("ck_model_artifacts_active_is_champion", type_="check")
        batch.drop_constraint("ck_model_artifacts_status", type_="check")
        batch.drop_constraint("ck_model_artifacts_target_mode", type_="check")
        batch.drop_constraint("ck_model_artifacts_feature_schema", type_="check")
        for name in ("card", "calibration", "status", "target_mode", "feature_schema", "profile", "format_version"):
            batch.drop_column(name)
