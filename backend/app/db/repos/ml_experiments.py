from __future__ import annotations

import os
import re
import secrets

from sqlalchemy import select

from app.db.instrument import db_timer
from app.db.jsonutil import to_jsonable
from app.db.models import MlExperiment
from app.db.types import utcnow
from app.ml.constants import EXPERIMENT_KINDS

_ID = re.compile(r"^exp_[A-Za-z0-9_-]{8,32}$")


def _dict(row):
    return {"id": row.id, "kind": row.kind, "name": row.name, "profile": row.profile, "model_id": row.model_id,
            "dataset_id": row.dataset_id, "config": row.config, "metrics": row.metrics, "slices": row.slices,
            "code_version": row.code_version, "schema_version": row.schema_version, "created_at": row.created_at.isoformat()}


class ExperimentRepo:
    def __init__(self, session_factory): self._sf = session_factory

    def record(self, kind: str, name: str, config: dict, metrics: dict, *, slices=None, profile=None, model_id=None, dataset_id=None) -> str:
        if kind not in EXPERIMENT_KINDS: raise ValueError("invalid experiment kind")
        if not name or len(name) > 64: raise ValueError("invalid experiment name")
        exp_id = "exp_" + secrets.token_urlsafe(9)
        with db_timer("ml_experiment_write"), self._sf.begin() as s:
            s.add(MlExperiment(id=exp_id, kind=kind, name=name, profile=profile, model_id=model_id, dataset_id=dataset_id,
                               config=to_jsonable(config), metrics=to_jsonable(metrics), slices=to_jsonable(slices),
                               code_version=os.getenv("GIT_COMMIT", "unknown")[:64], schema_version=1, created_at=utcnow()))
        return exp_id

    def list(self, kind: str | None = None, limit: int = 50) -> list[dict]:
        if kind is not None and kind not in EXPERIMENT_KINDS: raise ValueError("invalid experiment kind")
        if not 1 <= limit <= 200: raise ValueError("invalid experiment limit")
        q = select(MlExperiment)
        if kind: q = q.where(MlExperiment.kind == kind)
        with db_timer("ml_experiment_read"), self._sf() as s:
            return [_dict(row) for row in s.scalars(q.order_by(MlExperiment.created_at.desc()).limit(limit))]

    def get(self, exp_id: str) -> dict | None:
        if not _ID.fullmatch(exp_id): raise ValueError("invalid experiment id")
        with db_timer("ml_experiment_read"), self._sf() as s:
            row = s.get(MlExperiment, exp_id)
            return _dict(row) if row else None

    def latest(self, kind: str, model_id: int | None = None, suite_hash: str | None = None) -> dict | None:
        q = select(MlExperiment).where(MlExperiment.kind == kind)
        if model_id is not None: q = q.where(MlExperiment.model_id == model_id)
        with db_timer("ml_experiment_read"), self._sf() as s:
            rows = s.scalars(q.order_by(MlExperiment.created_at.desc()).limit(100)).all()
            for row in rows:
                if suite_hash is None or suite_hash in str(row.config): return _dict(row)
            return None
