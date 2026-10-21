from __future__ import annotations

import csv
import hashlib
import io
import secrets

from sqlalchemy import delete, select

from app.db.instrument import db_timer
from app.db.jsonutil import to_jsonable
from app.db.models import Dataset, EnvTraceSample, TrainingSample
from app.db.types import utcnow

FEATURE_COLUMNS = ("length_km", "aerial_fraction", "band_is_o", "traffic_now", "traffic_trend",
                   "temp_now", "dtemp_dt_now", "wind_now", "wind_trend", "hour_sin", "hour_cos")
TRAIN_COLUMNS = ("scenario", "split", *FEATURE_COLUMNS, "label_w")


def _number(value) -> str:
    if isinstance(value, int): return str(value)
    return format(float(value), ".17g")


def canonical_training_csv(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(TRAIN_COLUMNS)
    for row in rows:
        writer.writerow([row["scenario"], row["split"], *(_number(row[k]) for k in FEATURE_COLUMNS), _number(row["label_w"])])
    return stream.getvalue().encode("utf-8")


class DatasetStore:
    def __init__(self, session_factory): self._sf = session_factory

    def create_training(self, name: str, seed: int, config: dict, rows: list[dict], topology_preset: str = "metro"):
        if not name or len(name) > 64: raise ValueError("dataset name must be 1..64 characters")
        csv_bytes = canonical_training_csv(rows); digest = hashlib.sha256(csv_bytes).hexdigest(); dataset_id = "ds_" + secrets.token_urlsafe(9)
        with db_timer("run_write"), self._sf.begin() as s:
            s.add(Dataset(id=dataset_id, kind="training", name=name, topology_preset=topology_preset,
                seed=seed, config=to_jsonable(config), n_rows=len(rows), sha256=digest,
                generator_version="entangleops-1"))
            for start in range(0, len(rows), 1000):
                s.execute(TrainingSample.__table__.insert(), [
                    {"dataset_id": dataset_id, "row_id": start + i, **{k: row[k] for k in TRAIN_COLUMNS}}
                    for i, row in enumerate(rows[start:start + 1000])])
        return {"id": dataset_id, "name": name, "n_rows": len(rows), "sha256": digest}

    def create_env_trace(self, name: str, seed: int, config: dict, rows: list[dict], topology_preset: str = "metro"):
        rows = sorted(rows, key=lambda row: (row["link_id"], row["step"]))
        payload = json_bytes(rows); digest = hashlib.sha256(payload).hexdigest(); dataset_id = "ds_" + secrets.token_urlsafe(9)
        with db_timer("run_write"), self._sf.begin() as s:
            s.add(Dataset(id=dataset_id, kind="env_trace", name=name, topology_preset=topology_preset,
                seed=seed, config=to_jsonable(config), n_rows=len(rows), sha256=digest,
                generator_version="entangleops-1"))
            for start in range(0, len(rows), 1000):
                s.execute(EnvTraceSample.__table__.insert(), [{"dataset_id": dataset_id, **r} for r in rows[start:start + 1000]])
        return {"id": dataset_id, "name": name, "n_rows": len(rows), "sha256": digest}

    def list(self):
        with db_timer("run_read"), self._sf() as s:
            return [{"id": d.id, "kind": d.kind, "name": d.name, "seed": d.seed, "n_rows": d.n_rows,
                     "sha256": d.sha256, "created_at": d.created_at.isoformat()}
                    for d in s.scalars(select(Dataset).order_by(Dataset.created_at))]

    def training_rows(self, dataset_id: str):
        with db_timer("run_read"), self._sf() as s:
            rows = list(s.scalars(select(TrainingSample).where(TrainingSample.dataset_id == dataset_id).order_by(TrainingSample.row_id)))
            if not rows: raise ValueError("training dataset not found or empty")
            return [{"scenario": r.scenario, "split": r.split, **{k: getattr(r, k) for k in FEATURE_COLUMNS}, "label_w": r.label_w} for r in rows]

    def env_trace_rows(self, dataset_id: str):
        with db_timer("run_read"), self._sf() as s:
            rows = list(s.scalars(select(EnvTraceSample).where(EnvTraceSample.dataset_id == dataset_id).order_by(EnvTraceSample.link_id, EnvTraceSample.step)))
            if not rows: raise ValueError("environment dataset not found or empty")
            return [{"link_id": r.link_id, "step": r.step, "traffic": r.traffic, "temp_c": r.temp_c,
                     "dtemp_dt": r.dtemp_dt, "wind_ms": r.wind_ms} for r in rows]

    def get(self, dataset_id: str):
        with self._sf() as s:
            d = s.get(Dataset, dataset_id)
            return {"id": d.id, "kind": d.kind, "name": d.name, "seed": d.seed, "config": d.config,
                    "n_rows": d.n_rows, "sha256": d.sha256} if d else None

    def verify(self, dataset_id: str):
        with self._sf() as s:
            dataset = s.get(Dataset, dataset_id)
            if dataset is None: return False, "dataset not found"
            if dataset.kind == "training": payload = canonical_training_csv(self.training_rows(dataset_id))
            else:
                payload = json_bytes(self.env_trace_rows(dataset_id))
            return hashlib.sha256(payload).hexdigest() == dataset.sha256, dataset.sha256

    def delete(self, dataset_id: str) -> bool:
        with db_timer("run_write"), self._sf.begin() as s:
            result = s.execute(delete(Dataset).where(Dataset.id == dataset_id))
            return result.rowcount == 1


def json_bytes(value) -> bytes:
    import json
    return json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
