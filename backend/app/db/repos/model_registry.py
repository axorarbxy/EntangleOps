from __future__ import annotations

import hashlib
from pathlib import Path

import sklearn
from sqlalchemy import select, update

from app.db.instrument import db_timer
from app.db.jsonutil import to_jsonable
from app.db.models import ModelArtifact, ModelBaseline
from app.db.types import utcnow


class ModelRegistry:
    """Stores model provenance only; model loading remains bound to the signed configured path."""
    def __init__(self, session_factory): self._sf = session_factory

    def record(self, path: str, meta: dict, *, training_dataset_id: str | None = None) -> int:
        model_path = Path(path)
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        with db_timer("run_write"), self._sf.begin() as s:
            s.execute(update(ModelArtifact).where(ModelArtifact.is_active.is_(True)).values(is_active=False))
            row = s.scalar(select(ModelArtifact).where(ModelArtifact.sha256 == digest))
            if row is None:
                row = ModelArtifact(sha256=digest, file_name=model_path.name,
                    horizon_steps=int(meta.get("horizon_steps", 0)), metrics=to_jsonable(meta.get("metrics", {})),
                    feature_min=to_jsonable(meta.get("feature_min")), feature_max=to_jsonable(meta.get("feature_max")),
                    sklearn_version=sklearn.__version__, n_scenarios=meta.get("n_scenarios"),
                    train_seed=meta.get("train_seed"), training_dataset_id=training_dataset_id,
                    trained_at=utcnow(), is_active=True)
                s.add(row); s.flush()
            else:
                row.is_active = True
                row.file_name = model_path.name
                row.training_dataset_id = training_dataset_id
            return row.id

    def active_id(self) -> int | None:
        with db_timer("run_read"), self._sf() as s:
            row = s.scalar(select(ModelArtifact.id).where(ModelArtifact.is_active.is_(True)))
            return int(row) if row is not None else None

    def store_baseline(self, model_id: int, seeds: list[int], mae: float, p95: float, oor: float) -> None:
        with db_timer("run_write"), self._sf.begin() as s:
            s.add(ModelBaseline(model_id=model_id, seeds=to_jsonable(seeds), mae_ewma_mean=mae,
                                p95_abs_error=p95, oor_ratio_mean=oor, measured_at=utcnow()))
