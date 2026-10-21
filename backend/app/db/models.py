from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONDoc, JSONRaw, UTCDateTime, utcnow

BigIntPK = BigInteger().with_variant(Integer, "sqlite")
F = Float(53)
STATUS_CHECK = "status IN ('queued','running','done','error')"


class ApiKey(Base):
    __tablename__ = "api_keys"
    key_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (
        CheckConstraint("role IN ('viewer','operator','admin')", name="role"),
        CheckConstraint("length(name) BETWEEN 1 AND 64", name="name_len"),
        CheckConstraint("length(secret_hash) = 64", name="hash_len"),
    )


class AuditEntry(Base):
    __tablename__ = "audit_log"
    seq: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(F, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str | None] = mapped_column(String(12))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    prev: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    __table_args__ = (Index("ix_audit_log_kind_ts", "kind", "ts"), Index("ix_audit_log_key_id_ts", "key_id", "ts"))


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_key_id: Mapped[str] = mapped_column(String(12), ForeignKey("api_keys.key_id", ondelete="RESTRICT"), nullable=False)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("model_artifacts.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(8), default="queued", nullable=False)
    policy: Mapped[str] = mapped_column(String(16), nullable=False)
    topology_preset: Mapped[str] = mapped_column(String(16), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_hours: Mapped[float] = mapped_column(F, nullable=False)
    dt_s: Mapped[int] = mapped_column(Integer, nullable=False)
    n_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSONDoc)
    sla_satisfied_pairs: Mapped[float | None] = mapped_column(F)
    violation_fraction: Mapped[float | None] = mapped_column(F)
    error: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (
        CheckConstraint(STATUS_CHECK, name="status"),
        CheckConstraint("policy IN ('static_c','static_o','adaptive')", name="policy"),
        CheckConstraint("n_steps > 0", name="n_steps_pos"),
        CheckConstraint("status <> 'done' OR summary IS NOT NULL", name="done_has_summary"),
        CheckConstraint("status <> 'error' OR error IS NOT NULL", name="error_has_code"),
        Index("ix_runs_owner_key_id_created_at", "owner_key_id", "created_at"),
        Index("ix_runs_status", "status"), Index("ix_runs_created_at", "created_at"),
    )


class RunStep(Base):
    __tablename__ = "run_steps"
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    step: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    t_s: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[int] = mapped_column(Integer, nullable=False)
    arrivals: Mapped[int] = mapped_column(Integer, nullable=False)
    admitted: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False)
    reroutes: Mapped[int] = mapped_column(Integer, nullable=False)
    sla_violations: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_fidelity: Mapped[float | None] = mapped_column(F)
    useful_rate_pairs_s: Mapped[float] = mapped_column(F, nullable=False)
    raw_rate_pairs_s: Mapped[float] = mapped_column(F, nullable=False)
    links: Mapped[dict] = mapped_column(JSONRaw, nullable=False)
    allocations: Mapped[list] = mapped_column(JSONRaw, nullable=False)
    __table_args__ = (CheckConstraint("step >= 0", name="step_nonneg"),)


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_key_id: Mapped[str] = mapped_column(String(12), ForeignKey("api_keys.key_id", ondelete="RESTRICT"), nullable=False)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("model_artifacts.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(8), default="queued", nullable=False)
    config: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    improvement: Mapped[dict | None] = mapped_column(JSONDoc)
    error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (
        CheckConstraint(STATUS_CHECK, name="status"),
        CheckConstraint("status <> 'done' OR improvement IS NOT NULL", name="done_has_improvement"),
        CheckConstraint("status <> 'error' OR error IS NOT NULL", name="error_has_code"),
        Index("ix_benchmarks_owner_key_id_created_at", "owner_key_id", "created_at"),
        Index("ix_benchmarks_status", "status"),
    )


class WsTicketNonce(Base):
    __tablename__ = "ws_ticket_nonces"
    nonce: Mapped[str] = mapped_column(String(32), primary_key=True)
    key_id: Mapped[str] = mapped_column(String(12), nullable=False)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    __table_args__ = (Index("ix_ws_ticket_nonces_expires_at", "expires_at"),)


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(128), nullable=False)
    horizon_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    feature_min: Mapped[list | None] = mapped_column(JSONDoc)
    feature_max: Mapped[list | None] = mapped_column(JSONDoc)
    sklearn_version: Mapped[str | None] = mapped_column(String(32))
    n_scenarios: Mapped[int | None] = mapped_column(Integer)
    train_seed: Mapped[int | None] = mapped_column(BigInteger)
    training_dataset_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("datasets.id", ondelete="SET NULL"))
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (Index("uq_model_artifacts_one_active", "is_active", unique=True, postgresql_where=text("is_active"), sqlite_where=text("is_active = 1")),)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    topology_preset: Mapped[str] = mapped_column(String(16), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    config: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    __table_args__ = (CheckConstraint("kind IN ('training','env_trace')", name="kind"),)


class TrainingSample(Base):
    __tablename__ = "training_samples"
    dataset_id: Mapped[str] = mapped_column(String(32), ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True)
    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    scenario: Mapped[int] = mapped_column(Integer, nullable=False)
    split: Mapped[str] = mapped_column(String(5), nullable=False)
    length_km: Mapped[float] = mapped_column(F, nullable=False)
    aerial_fraction: Mapped[float] = mapped_column(F, nullable=False)
    band_is_o: Mapped[float] = mapped_column(F, nullable=False)
    traffic_now: Mapped[float] = mapped_column(F, nullable=False)
    traffic_trend: Mapped[float] = mapped_column(F, nullable=False)
    temp_now: Mapped[float] = mapped_column(F, nullable=False)
    dtemp_dt_now: Mapped[float] = mapped_column(F, nullable=False)
    wind_now: Mapped[float] = mapped_column(F, nullable=False)
    wind_trend: Mapped[float] = mapped_column(F, nullable=False)
    hour_sin: Mapped[float] = mapped_column(F, nullable=False)
    hour_cos: Mapped[float] = mapped_column(F, nullable=False)
    label_w: Mapped[float] = mapped_column(F, nullable=False)
    __table_args__ = (CheckConstraint("split IN ('train','test')", name="split"),)


class EnvTraceSample(Base):
    __tablename__ = "env_trace_samples"
    dataset_id: Mapped[str] = mapped_column(String(32), ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True)
    link_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    step: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    traffic: Mapped[float] = mapped_column(F, nullable=False)
    temp_c: Mapped[float] = mapped_column(F, nullable=False)
    dtemp_dt: Mapped[float] = mapped_column(F, nullable=False)
    wind_ms: Mapped[float] = mapped_column(F, nullable=False)


class ModelBaseline(Base):
    __tablename__ = "model_baselines"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model_artifacts.id", ondelete="CASCADE"), nullable=False)
    seeds: Mapped[list] = mapped_column(JSONDoc, nullable=False)
    mae_ewma_mean: Mapped[float] = mapped_column(F, nullable=False)
    p95_abs_error: Mapped[float] = mapped_column(F, nullable=False)
    oor_ratio_mean: Mapped[float] = mapped_column(F, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class BenchmarkResult(Base):
    __tablename__ = "benchmark_results"
    benchmark_id: Mapped[str] = mapped_column(String(32), ForeignKey("benchmarks.id", ondelete="CASCADE"), primary_key=True)
    policy: Mapped[str] = mapped_column(String(16), primary_key=True)
    summary: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    sla_satisfied_pairs: Mapped[float] = mapped_column(F, nullable=False)
    violation_fraction: Mapped[float] = mapped_column(F, nullable=False)
    block_rate: Mapped[float] = mapped_column(F, nullable=False)
    reroutes: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_fidelity: Mapped[float | None] = mapped_column(F)
    __table_args__ = (CheckConstraint("policy IN ('static_c','static_o','adaptive')", name="policy"),)
