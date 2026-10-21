"""Initial persistent storage schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.types import UTCDateTime
from database.migrations.helpers import audit_immutable_up, audit_immutable_down, grant_app, grant_sequences

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
id_type = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade():
    op.create_table("api_keys",
        sa.Column("key_id", sa.String(12), primary_key=True), sa.Column("name", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False), sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False), sa.Column("expires_at", UTCDateTime()),
        sa.Column("revoked_at", UTCDateTime()), sa.Column("last_used_at", UTCDateTime()),
        sa.CheckConstraint("role IN ('viewer','operator','admin')", name="role"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 64", name="name_len"),
        sa.CheckConstraint("length(secret_hash) = 64", name="hash_len"))
    op.create_table("audit_log",
        sa.Column("seq", id_type, primary_key=True, autoincrement=True), sa.Column("ts", sa.Float(53), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False), sa.Column("key_id", sa.String(12)),
        sa.Column("body", sa.Text(), nullable=False), sa.Column("prev", sa.String(64), nullable=False, unique=True),
        sa.Column("hash", sa.String(64), nullable=False, unique=True))
    op.create_index("ix_audit_log_kind_ts", "audit_log", ["kind", "ts"])
    op.create_index("ix_audit_log_key_id_ts", "audit_log", ["key_id", "ts"])
    op.create_table("datasets",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, unique=True), sa.Column("topology_preset", sa.String(16), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False), sa.Column("config", json_type, nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("generator_version", sa.String(64), nullable=False), sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", UTCDateTime(), nullable=False), sa.CheckConstraint("kind IN ('training','env_trace')", name="kind"))
    op.create_table("training_samples",
        sa.Column("dataset_id", sa.String(32), sa.ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("row_id", sa.Integer(), primary_key=True), sa.Column("scenario", sa.Integer(), nullable=False),
        sa.Column("split", sa.String(5), nullable=False), sa.Column("length_km", sa.Float(53), nullable=False),
        sa.Column("aerial_fraction", sa.Float(53), nullable=False), sa.Column("band_is_o", sa.Float(53), nullable=False),
        sa.Column("traffic_now", sa.Float(53), nullable=False), sa.Column("traffic_trend", sa.Float(53), nullable=False),
        sa.Column("temp_now", sa.Float(53), nullable=False), sa.Column("dtemp_dt_now", sa.Float(53), nullable=False),
        sa.Column("wind_now", sa.Float(53), nullable=False), sa.Column("wind_trend", sa.Float(53), nullable=False),
        sa.Column("hour_sin", sa.Float(53), nullable=False), sa.Column("hour_cos", sa.Float(53), nullable=False),
        sa.Column("label_w", sa.Float(53), nullable=False), sa.CheckConstraint("split IN ('train','test')", name="split"))
    op.create_table("env_trace_samples",
        sa.Column("dataset_id", sa.String(32), sa.ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("link_id", sa.String(16), primary_key=True), sa.Column("step", sa.Integer(), primary_key=True),
        sa.Column("traffic", sa.Float(53), nullable=False), sa.Column("temp_c", sa.Float(53), nullable=False),
        sa.Column("dtemp_dt", sa.Float(53), nullable=False), sa.Column("wind_ms", sa.Float(53), nullable=False))
    op.create_table("model_artifacts",
        sa.Column("id", id_type, primary_key=True, autoincrement=True), sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("file_name", sa.String(128), nullable=False), sa.Column("horizon_steps", sa.Integer(), nullable=False),
        sa.Column("metrics", json_type, nullable=False), sa.Column("feature_min", json_type), sa.Column("feature_max", json_type),
        sa.Column("sklearn_version", sa.String(32)), sa.Column("n_scenarios", sa.Integer()), sa.Column("train_seed", sa.BigInteger()),
        sa.Column("training_dataset_id", sa.String(32), sa.ForeignKey("datasets.id", ondelete="SET NULL")), sa.Column("trained_at", UTCDateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("uq_model_artifacts_one_active", "model_artifacts", ["is_active"], unique=True,
                    postgresql_where=sa.text("is_active"), sqlite_where=sa.text("is_active = 1"))
    op.create_table("model_baselines", sa.Column("id", id_type, primary_key=True, autoincrement=True),
        sa.Column("model_id", id_type, sa.ForeignKey("model_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seeds", json_type, nullable=False), sa.Column("mae_ewma_mean", sa.Float(53), nullable=False),
        sa.Column("p95_abs_error", sa.Float(53), nullable=False), sa.Column("oor_ratio_mean", sa.Float(53), nullable=False),
        sa.Column("measured_at", UTCDateTime(), nullable=False))
    op.create_table("runs",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("owner_key_id", sa.String(12), sa.ForeignKey("api_keys.key_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("model_id", id_type, sa.ForeignKey("model_artifacts.id", ondelete="RESTRICT")), sa.Column("status", sa.String(8), nullable=False), sa.Column("policy", sa.String(16), nullable=False),
        sa.Column("topology_preset", sa.String(16), nullable=False), sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("duration_hours", sa.Float(53), nullable=False), sa.Column("dt_s", sa.Integer(), nullable=False), sa.Column("n_steps", sa.Integer(), nullable=False),
        sa.Column("config", json_type, nullable=False), sa.Column("summary", json_type), sa.Column("sla_satisfied_pairs", sa.Float(53)),
        sa.Column("violation_fraction", sa.Float(53)), sa.Column("error", sa.String(64)), sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", UTCDateTime(), nullable=False), sa.Column("started_at", UTCDateTime()), sa.Column("finished_at", UTCDateTime()), sa.Column("heartbeat_at", UTCDateTime()),
        sa.CheckConstraint("status IN ('queued','running','done','error')", name="status"),
        sa.CheckConstraint("policy IN ('static_c','static_o','adaptive')", name="policy"),
        sa.CheckConstraint("n_steps > 0", name="n_steps_pos"),
        sa.CheckConstraint("status <> 'done' OR summary IS NOT NULL", name="done_has_summary"),
        sa.CheckConstraint("status <> 'error' OR error IS NOT NULL", name="error_has_code"))
    op.create_index("ix_runs_owner_key_id_created_at", "runs", ["owner_key_id", "created_at"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])
    op.create_table("run_steps",
        sa.Column("run_id", sa.String(32), sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("step", sa.Integer(), primary_key=True), sa.Column("t_s", sa.Integer(), nullable=False), sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("arrivals", sa.Integer(), nullable=False), sa.Column("admitted", sa.Integer(), nullable=False), sa.Column("blocked", sa.Integer(), nullable=False),
        sa.Column("reroutes", sa.Integer(), nullable=False), sa.Column("sla_violations", sa.Integer(), nullable=False), sa.Column("mean_fidelity", sa.Float(53)),
        sa.Column("useful_rate_pairs_s", sa.Float(53), nullable=False), sa.Column("raw_rate_pairs_s", sa.Float(53), nullable=False),
        sa.Column("links", sa.JSON(), nullable=False), sa.Column("allocations", sa.JSON(), nullable=False),
        sa.CheckConstraint("step >= 0", name="step_nonneg"))
    op.create_table("benchmarks",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("owner_key_id", sa.String(12), sa.ForeignKey("api_keys.key_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("model_id", id_type, sa.ForeignKey("model_artifacts.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(8), nullable=False), sa.Column("config", json_type, nullable=False), sa.Column("improvement", json_type),
        sa.Column("error", sa.String(64)), sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("started_at", UTCDateTime()), sa.Column("finished_at", UTCDateTime()), sa.Column("heartbeat_at", UTCDateTime()),
        sa.CheckConstraint("status IN ('queued','running','done','error')", name="status"),
        sa.CheckConstraint("status <> 'done' OR improvement IS NOT NULL", name="done_has_improvement"),
        sa.CheckConstraint("status <> 'error' OR error IS NOT NULL", name="error_has_code"))
    op.create_index("ix_benchmarks_owner_key_id_created_at", "benchmarks", ["owner_key_id", "created_at"])
    op.create_index("ix_benchmarks_status", "benchmarks", ["status"])
    op.create_table("benchmark_results", sa.Column("benchmark_id", sa.String(32), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("policy", sa.String(16), primary_key=True), sa.Column("summary", json_type, nullable=False),
        sa.Column("sla_satisfied_pairs", sa.Float(53), nullable=False), sa.Column("violation_fraction", sa.Float(53), nullable=False),
        sa.Column("block_rate", sa.Float(53), nullable=False), sa.Column("reroutes", sa.Integer(), nullable=False),
        sa.Column("mean_fidelity", sa.Float(53)), sa.CheckConstraint("policy IN ('static_c','static_o','adaptive')", name="policy"))
    op.create_table("ws_ticket_nonces", sa.Column("nonce", sa.String(32), primary_key=True), sa.Column("key_id", sa.String(12), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False), sa.Column("expires_at", UTCDateTime(), nullable=False), sa.Column("used_at", UTCDateTime(), nullable=False))
    op.create_index("ix_ws_ticket_nonces_expires_at", "ws_ticket_nonces", ["expires_at"])
    audit_immutable_up()
    grant_app("SELECT, INSERT, UPDATE", ["api_keys"])
    grant_app("SELECT, INSERT", ["audit_log"])
    grant_app("SELECT, INSERT, UPDATE, DELETE", ["runs", "run_steps", "benchmarks", "benchmark_results", "ws_ticket_nonces", "datasets", "training_samples", "env_trace_samples"])
    grant_app("SELECT, INSERT, UPDATE", ["model_artifacts", "model_baselines"])
    grant_sequences()


def downgrade():
    audit_immutable_down()
    op.drop_index("ix_ws_ticket_nonces_expires_at", table_name="ws_ticket_nonces")
    op.drop_table("ws_ticket_nonces")
    op.drop_index("ix_benchmarks_status", table_name="benchmarks")
    op.drop_index("ix_benchmarks_owner_key_id_created_at", table_name="benchmarks")
    op.drop_table("benchmark_results")
    op.drop_table("benchmarks")
    op.drop_table("run_steps")
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_owner_key_id_created_at", table_name="runs")
    op.drop_table("runs")
    op.drop_table("model_baselines")
    op.drop_index("uq_model_artifacts_one_active", table_name="model_artifacts")
    op.drop_table("model_artifacts")
    op.drop_table("env_trace_samples")
    op.drop_table("training_samples")
    op.drop_table("datasets")
    op.drop_index("ix_audit_log_key_id_ts", table_name="audit_log")
    op.drop_index("ix_audit_log_kind_ts", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("api_keys")
