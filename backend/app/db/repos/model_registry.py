from __future__ import annotations

import hashlib
import os
from pathlib import Path

import sklearn
from sqlalchemy import select, update

from app.config import settings
from app.db.instrument import db_timer
from app.db.jsonutil import to_jsonable
from app.db.models import ModelArtifact, ModelBaseline
from app.db.types import utcnow


def _model_dict(row: ModelArtifact) -> dict:
    return {"id": row.id, "sha256": row.sha256, "file_name": row.file_name, "horizon_steps": row.horizon_steps,
            "metrics": row.metrics or {}, "feature_min": row.feature_min, "feature_max": row.feature_max,
            "sklearn_version": row.sklearn_version, "n_scenarios": row.n_scenarios, "train_seed": row.train_seed,
            "training_dataset_id": row.training_dataset_id, "trained_at": row.trained_at.isoformat(),
            "is_active": row.is_active, "profile": row.profile, "feature_schema": row.feature_schema,
            "target_mode": row.target_mode, "format_version": row.format_version, "status": row.status,
            "calibration": row.calibration, "card": row.card}


class ModelRegistry:
    """Registry metadata for signed artifacts; serving still loads only settings.model_path."""
    def __init__(self, session_factory): self._sf = session_factory

    def record(self, path: str, meta: dict, *, training_dataset_id: str | None = None, activate: bool = True) -> int:
        model_path = Path(path)
        if not model_path.is_file(): raise ValueError("model artifact is missing")
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        archived_path = None
        if activate:
            if not Path(str(model_path) + ".sig").exists():
                raise ValueError("active model artifact must have a signature sidecar")
            from app.core.predictor import _signing_key
            from app.ml.payload import archive_model, load_payload
            payload = load_payload(model_path, _signing_key())
            if payload.get("format_version") == 2:
                payload_metrics = dict(payload.get("metrics") or {})
                payload_metrics.update({"mean_target": payload.get("mean_target", payload_metrics.get("mean_target", 0.0)),
                                        "format_version": payload.get("format_version")})
                meta = {**meta, "profile": payload.get("profile"), "feature_schema": payload.get("feature_schema"),
                    "target_mode": payload.get("target_mode"), "horizon_steps": payload.get("horizon_steps"),
                    "format_version": payload.get("format_version"),
                    "metrics": payload_metrics, "feature_min": payload.get("feature_min"),
                    "feature_max": payload.get("feature_max"), "sklearn_version": payload.get("sklearn_version"),
                    "n_scenarios": payload.get("n_scenarios"), "train_seed": payload.get("train_seed"),
                    "calibration": payload.get("calibration"), "card": payload.get("card")}
            else:
                from app.core.predictor import FidelityPredictor
                active_model = FidelityPredictor.load(model_path)
                active_metrics = dict(meta.get("metrics", {}))
                active_metrics["format_version"] = active_model.format_version
                active_metrics["mean_target"] = active_model.mean_target
                meta = {**meta, "metrics": active_metrics, "sklearn_version": active_model.sklearn_version}
                meta["format_version"] = active_model.format_version
            archived_path = archive_model(model_path, settings.ml_models_dir)
        profile = str(meta.get("profile", "baseline_v1"))
        schema = str(meta.get("feature_schema", "v1"))
        target = str(meta.get("target_mode", "direct"))
        status = "champion" if activate else "candidate"
        with db_timer("run_write"), self._sf.begin() as s:
            if activate:
                s.execute(update(ModelArtifact).where(ModelArtifact.is_active.is_(True)).values(is_active=False, status="retired"))
            row = s.scalar(select(ModelArtifact).where(ModelArtifact.sha256 == digest))
            if row is None:
                row = ModelArtifact(sha256=digest, file_name=archived_path.name if archived_path else model_path.name,
                    horizon_steps=int(meta.get("horizon_steps", 0)), metrics=to_jsonable(meta.get("metrics", {})),
                    feature_min=to_jsonable(meta.get("feature_min")), feature_max=to_jsonable(meta.get("feature_max")),
                    sklearn_version=str(meta.get("sklearn_version") or sklearn.__version__), n_scenarios=meta.get("n_scenarios"),
                    train_seed=meta.get("train_seed"), training_dataset_id=training_dataset_id,
                    trained_at=utcnow(), is_active=activate, profile=profile, feature_schema=schema,
                    target_mode=target, format_version=int(meta.get("format_version", 2 if activate else 1)),
                    status=status, calibration=to_jsonable(meta.get("calibration")), card=to_jsonable(meta.get("card")))
                s.add(row); s.flush()
            else:
                row.file_name = archived_path.name if archived_path else model_path.name
                row.training_dataset_id = training_dataset_id
                row.horizon_steps = int(meta.get("horizon_steps", row.horizon_steps))
                row.metrics = to_jsonable(meta.get("metrics", row.metrics))
                row.feature_min = to_jsonable(meta.get("feature_min", row.feature_min))
                row.feature_max = to_jsonable(meta.get("feature_max", row.feature_max))
                row.sklearn_version = str(meta.get("sklearn_version") or row.sklearn_version or sklearn.__version__)
                row.n_scenarios, row.train_seed = meta.get("n_scenarios", row.n_scenarios), meta.get("train_seed", row.train_seed)
                row.profile, row.feature_schema, row.target_mode = profile, schema, target
                row.format_version = int(meta.get("format_version", row.format_version))
                if "calibration" in meta: row.calibration = to_jsonable(meta.get("calibration"))
                if "card" in meta: row.card = to_jsonable(meta.get("card"))
                if activate:
                    row.is_active, row.status = True, "champion"
                elif not row.is_active:
                    row.status = "candidate"
            return row.id

    def active_id(self) -> int | None:
        with db_timer("run_read"), self._sf() as s:
            row = s.scalar(select(ModelArtifact.id).where(ModelArtifact.is_active.is_(True)))
            return int(row) if row is not None else None

    def get(self, model_id: int) -> dict | None:
        with db_timer("run_read"), self._sf() as s:
            row = s.get(ModelArtifact, model_id)
            return _model_dict(row) if row else None

    def active(self) -> dict | None:
        with db_timer("run_read"), self._sf() as s:
            row = s.scalar(select(ModelArtifact).where(ModelArtifact.is_active.is_(True)))
            return _model_dict(row) if row else None

    def list_models(self) -> list[dict]:
        with db_timer("run_read"), self._sf() as s:
            return [_model_dict(row) for row in s.scalars(select(ModelArtifact).order_by(ModelArtifact.trained_at.desc(), ModelArtifact.id.desc()))]

    def promote(self, model_id: int, *, expected_sha256: str | None = None) -> int | None:
        from app.core.predictor import _signing_key
        from app.ml.payload import load_payload
        with db_timer("run_write"), self._sf.begin() as s:
            candidate = s.get(ModelArtifact, model_id)
            if candidate is None: raise LookupError("model not found")
            if candidate.status not in {"candidate", "champion"}: raise ValueError("model is not promotable")
            if expected_sha256 is not None and candidate.sha256 != expected_sha256: raise ValueError("model digest changed")
            artifact_dir = Path(settings.ml_models_dir)
            if not artifact_dir.is_absolute(): artifact_dir = Path.cwd() / artifact_dir
            artifact = artifact_dir / candidate.file_name
            if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != candidate.sha256:
                raise ValueError("candidate artifact is missing or has the wrong digest")
            load_payload(artifact, _signing_key())
            previous = s.scalar(select(ModelArtifact).where(ModelArtifact.is_active.is_(True)))
            s.execute(update(ModelArtifact).where(ModelArtifact.is_active.is_(True)).values(is_active=False, status="retired"))
            candidate = s.get(ModelArtifact, model_id)
            candidate.is_active, candidate.status = True, "champion"
            return int(previous.id) if previous and previous.id != model_id else None

    def rollback(self) -> int | None:
        with db_timer("run_write"), self._sf.begin() as s:
            active = s.scalar(select(ModelArtifact).where(ModelArtifact.is_active.is_(True)))
            candidates = list(s.scalars(select(ModelArtifact).where(ModelArtifact.status == "retired").order_by(ModelArtifact.trained_at.desc(), ModelArtifact.id.desc()).limit(1)))
            if not candidates: return None
            previous = candidates[0]
            s.execute(update(ModelArtifact).where(ModelArtifact.is_active.is_(True)).values(is_active=False, status="retired"))
            previous = s.get(ModelArtifact, previous.id)
            previous.is_active, previous.status = True, "champion"
            if active and active.id != previous.id:
                current = s.get(ModelArtifact, active.id); current.status = "candidate"
            return int(previous.id)

    def rollback_candidate(self) -> dict | None:
        with db_timer("run_read"), self._sf() as s:
            row = s.scalar(select(ModelArtifact).where(ModelArtifact.status == "retired")
                           .order_by(ModelArtifact.trained_at.desc(), ModelArtifact.id.desc()).limit(1))
            return _model_dict(row) if row else None

    def status(self, model_id: int, value: str) -> None:
        if value not in {"candidate", "retired"}: raise ValueError("invalid model status")
        with db_timer("run_write"), self._sf.begin() as s:
            row = s.get(ModelArtifact, model_id)
            if row is None: raise LookupError("model not found")
            if row.is_active: raise ValueError("cannot change active model status")
            row.status = value

    def update_card(self, model_id: int, card: dict) -> None:
        with db_timer("run_write"), self._sf.begin() as s:
            row = s.get(ModelArtifact, model_id)
            if row is None: raise LookupError("model not found")
            row.card = to_jsonable(card)

    def store_baseline(self, model_id: int, seeds: list[int], mae: float, p95: float, oor: float) -> None:
        with db_timer("run_write"), self._sf.begin() as s:
            s.add(ModelBaseline(model_id=model_id, seeds=to_jsonable(seeds), mae_ewma_mean=mae,
                                p95_abs_error=p95, oor_ratio_mean=oor, measured_at=utcnow()))
