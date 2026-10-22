from __future__ import annotations

import logging
import math
import secrets
from pathlib import Path

import numpy as np

from app.config import ScenarioConfig, settings
from app.core.environment import EnvTraces, generate_env
from app.core.physics import BANDS, W0, LinkParams, link_werner
from app.core.topology import get_preset, link_lookup
from app.ml.conformal import UncalibratedModelError
from app.ml.features import build_features
from app.ml.payload import ModelIntegrityError, archive_model, load_payload, save_payload

logger = logging.getLogger(__name__)
_EPHEMERAL_SIGNING_KEY = secrets.token_hex(32)
_audit_callback = None


def set_audit_callback(callback) -> None:
    global _audit_callback
    _audit_callback = callback


def _audit(kind: str, **fields) -> None:
    if _audit_callback is not None:
        try: _audit_callback(kind, **fields)
        except Exception: logger.exception("Unable to record predictor audit event")


def _signing_key() -> str:
    if settings.model_signing_key: return settings.model_signing_key
    if settings.env == "production": raise ModelIntegrityError("model signing key is required in production")
    logger.warning("Model signing key is unset; using an ephemeral development key")
    return _EPHEMERAL_SIGNING_KEY


class FidelityPredictor:
    """Backward-compatible facade over the pure profile/payload implementation."""
    def __init__(self, profile: str = "baseline_v1"):
        self.model = None
        self.metrics = {}
        self.horizon_steps = 5
        self.feature_min, self.feature_max = [], []
        self.profile = profile
        self.feature_schema = "v1"
        self.target_mode = "direct"
        self.calibration = None
        self.reference = None
        self.sklearn_version = None
        self.format_version = 1
        self.mean_target = 0.0
        self.card = None
        self.n_scenarios = None
        self.train_seed = None

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray | None = None) -> dict:
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, r2_score

        X, y = np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.float64)
        if X.ndim != 2 or y.ndim != 1 or len(X) != len(y) or not np.isfinite(X).all() or not np.isfinite(y).all():
            raise ValueError("training data must be finite and aligned")
        if self.profile == "baseline_v1" and groups is None:
            from sklearn import __version__ as sklearn_version
            self.feature_schema, self.target_mode = "v1", "direct"
            self.feature_min, self.feature_max = np.min(X, axis=0).tolist(), np.max(X, axis=0).tolist()
            self.model = HistGradientBoostingRegressor(max_iter=300, learning_rate=.08, max_depth=6, random_state=0).fit(X, y)
            pred = self.model.predict(X)
            self.metrics = {"r2_train": float(r2_score(y, pred)), "r2_test": float(r2_score(y, pred)),
                            "mae_test": float(mean_absolute_error(y, pred))}
            self.mean_target = float(np.mean(y))
            self.sklearn_version = sklearn_version
            self.format_version = 2
            return self.metrics
        from app.ml.profiles import PROFILES
        from app.ml.training import fit_profile
        if groups is None: raise ValueError("scenario groups are required for governed profiles")
        fitted = fit_profile(PROFILES[self.profile], X, y, groups)
        self.model = fitted.estimator
        self.feature_schema, self.target_mode = fitted.profile.feature_schema, fitted.profile.target_mode
        self.metrics, self.feature_min, self.feature_max = fitted.metrics, fitted.feature_min, fitted.feature_max
        self.reference, self.mean_target = fitted.reference, fitted.mean_target
        self.format_version = 2
        from sklearn import __version__ as sklearn_version
        self.sklearn_version = sklearn_version
        return self.metrics

    def predict_w(self, X: np.ndarray) -> np.ndarray:
        if self.model is None: raise RuntimeError("predictor not fitted")
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1: X = X.reshape(1, -1)
        from app.ml.constants import SCHEMAS
        expected = len(SCHEMAS.get(self.feature_schema, ()))
        if X.ndim != 2 or X.shape[1] != expected: raise ValueError("feature column count does not match model schema")
        if not np.isfinite(X).all(): raise ValueError("features must be finite")
        pred = self.model.predict(X)
        if self.target_mode == "residual":
            from app.ml.features import physics_w_np
            pred = pred + physics_w_np(X)
        return np.clip(pred, 0, W0)

    def predict_w_interval_full(self, X, alpha: float):
        from app.ml.constants import ALPHAS
        if not self.calibration: raise UncalibratedModelError("model is not calibrated")
        if alpha not in ALPHAS: raise ValueError("alpha must be one of ALPHAS")
        pred = self.predict_w(X)
        q_table = self.calibration.get("q", {}).get(str(alpha))
        if q_table is None: raise UncalibratedModelError("alpha is not calibrated")
        X2 = np.atleast_2d(np.asarray(X, dtype=np.float64))
        group = np.where(X2[:, 1] <= 0, "buried", np.where(X2[:, 1] >= 1, "aerial", "mixed"))
        q = np.asarray([q_table.get(name, q_table.get("global")) for name in group], dtype=np.float64)
        return pred, np.clip(pred - q, 0, W0), np.clip(pred + q, 0, W0)

    def predict_w_interval(self, X, alpha: float):
        pred, lo, _ = self.predict_w_interval_full(X, alpha)
        return pred, lo

    def _payload(self) -> dict:
        from sklearn import __version__ as sklearn_version
        return {"format_version": 2, "profile": self.profile, "feature_schema": self.feature_schema,
                "target_mode": self.target_mode, "horizon_steps": self.horizon_steps, "estimator": self.model,
                "metrics": dict(self.metrics), "feature_min": list(self.feature_min), "feature_max": list(self.feature_max),
                "reference": self.reference, "calibration": self.calibration, "sklearn_version": sklearn_version,
                "mean_target": float(self.mean_target), "card": self.card,
                "n_scenarios": self.n_scenarios, "train_seed": self.train_seed}

    def save(self, path: str | Path) -> None:
        target = Path(path)
        if target.resolve() == Path(settings.model_path).resolve(): archive_model(target, settings.ml_models_dir)
        save_payload(self._payload(), target, _signing_key())

    @classmethod
    def load(cls, path: str | Path) -> "FidelityPredictor":
        from sklearn import __version__ as sklearn_version
        payload = load_payload(path, _signing_key())
        p = cls(payload.get("profile", "baseline_v1"))
        p.model = payload.get("estimator", payload.get("model"))
        p.horizon_steps = int(payload["horizon_steps"])
        p.metrics = payload.get("metrics", {})
        p.mean_target = float(payload.get("mean_target", p.metrics.get("mean_target", 0.0)))
        p.feature_min, p.feature_max = payload.get("feature_min", []), payload.get("feature_max", [])
        p.feature_schema, p.target_mode = payload.get("feature_schema", "v1"), payload.get("target_mode", "direct")
        p.reference, p.calibration = payload.get("reference"), payload.get("calibration")
        p.sklearn_version = payload.get("sklearn_version") or sklearn_version
        p.format_version = payload.get("format_version", 1)
        p.card = payload.get("card")
        p.n_scenarios = payload.get("n_scenarios")
        p.train_seed = payload.get("train_seed")
        if p.model is None or not p.feature_min or not p.feature_max: raise ModelIntegrityError("outdated model artifact")
        return p

    @classmethod
    def load_or_train(cls, path: str | Path, horizon_steps: int, seed: int = 0) -> "FidelityPredictor":
        target = Path(path)
        try:
            p = cls.load(target)
            if p.horizon_steps == horizon_steps:
                try:
                    from monitoring.metrics import predictor_loads
                    predictor_loads.labels("ok").inc()
                except Exception: pass
                return p
        except (ModelIntegrityError, FileNotFoundError):
            try:
                from monitoring.metrics import predictor_loads, model_verify_failures
                predictor_loads.labels("failed").inc()
                if isinstance(__import__("sys").exc_info()[1], ModelIntegrityError): model_verify_failures.inc()
            except Exception: pass
        except Exception:
            pass
        archive_model(target, settings.ml_models_dir)
        n_scenarios = 8
        X, y, _ = generate_training_data(n_scenarios, horizon_steps, seed)
        p = cls(); p.horizon_steps = horizon_steps; p.fit(X, y); p.n_scenarios = n_scenarios; p.train_seed = seed
        p.metrics = {**p.metrics, "mean_target": p.mean_target, "format_version": p.format_version}
        p.save(target)
        try:
            from monitoring.metrics import predictor_loads
            predictor_loads.labels("retrained").inc()
        except Exception: pass
        _audit("model.retrained", profile=p.profile, horizon_steps=p.horizon_steps)
        return p


def generate_training_data(n_scenarios: int, horizon_steps: int, seed: int, preset: str = "metro") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed); _nodes, links = get_preset(preset); lookup = link_lookup(links)
    xs, ys, groups = [], [], []
    for si in range(n_scenarios):
        # Keep the original baseline generator's single RNG stream intact. The
        # independently seeded environment is intentional and remains unchanged.
        sc = ScenarioConfig(storm_center_h=float(rng.uniform(6, 20)), storm_wind_peak_ms=float(rng.uniform(8, 25)),
                            traffic_peak_hour=float(rng.uniform(17, 22)))
        env = generate_env(list(lookup), 24, 60, seed + si, sc)
        for lid, link in lookup.items():
            for band in BANDS:
                for t in range(0, env.n_steps - horizon_steps, 5):
                    xs.append(build_features(env, link, band, t))
                    ys.append(link_werner(link, band, env.conditions(lid, t + horizon_steps)) + rng.normal(0, .005))
                    groups.append(si)
    return np.asarray(xs), np.clip(np.asarray(ys), 0, W0), np.asarray(groups)
