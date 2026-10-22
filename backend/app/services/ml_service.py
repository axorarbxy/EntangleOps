from __future__ import annotations

from app.db.repos.ml_experiments import ExperimentRepo
from app.db.repos.model_registry import ModelRegistry
from app.ml.serving import RowCachePredictor
from app.config import settings
from monitoring import metrics as m


class MlService:
    def __init__(self, session_factory):
        self.registry = ModelRegistry(session_factory)
        self.experiments = ExperimentRepo(session_factory)

    @staticmethod
    def _cache_event(result: str, rows: int, seconds: float, kind: str) -> None:
        m.ml_prediction_cache_total.labels(m.bounded(result, m.ML_RESULTS)).inc(rows)
        if result == "miss":
            m.ml_inference_seconds.labels(m.bounded(kind, m.ML_KINDS)).observe(seconds)

    def cache(self, predictor):
        return RowCachePredictor(predictor, settings.ml_prediction_cache_rows, self._cache_event)

    @staticmethod
    def expose_model(row: dict | None) -> dict | None:
        if row is None: return None
        calibration = row.get("calibration")
        if calibration:
            calibration = {"method": calibration.get("method"), "alphas": list(calibration.get("q", {}).keys()),
                           "groups": ["buried", "mixed", "aerial"], "suite_sha256": calibration.get("suite_sha256"),
                           "n": calibration.get("n")}
        metrics = row.get("metrics") or {}
        return {"id": row["id"], "profile": row["profile"], "status": row["status"],
                "feature_schema": row["feature_schema"], "target_mode": row["target_mode"],
                "horizon_steps": row["horizon_steps"], "sha256": row["sha256"],
                "sklearn_version": row.get("sklearn_version"), "trained_at": row["trained_at"],
                "metrics": {k: metrics[k] for k in ("r2_test", "mae_test") if k in metrics},
                "calibration": calibration, "card": row.get("card")}
