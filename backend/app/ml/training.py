from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from app.core.physics import W0
from app.ml.features import physics_w_np
from app.ml.profiles import Profile


def split_by_scenario(groups: np.ndarray) -> np.ndarray:
    """Return a boolean test mask containing the last 20% of scenario ids."""
    groups = np.asarray(groups)
    unique = np.unique(groups)
    if unique.size < 2:
        raise ValueError("at least two scenarios are required for a held-out split")
    n_test = max(1, int(np.ceil(unique.size * .2)))
    return np.isin(groups, unique[-n_test:])


@dataclass
class FittedProfile:
    profile: Profile
    estimator: HistGradientBoostingRegressor
    metrics: dict
    feature_min: list[float]
    feature_max: list[float]
    reference: dict
    mean_target: float

    def predict_w(self, X):
        X = np.asarray(X, dtype=np.float64)
        raw = self.estimator.predict(X)
        if self.profile.target_mode == "residual":
            raw = raw + physics_w_np(X)
        return np.clip(raw, 0, W0)


def _reference(X: np.ndarray) -> dict:
    edges, frac = [], []
    for column in X.T:
        e = np.unique(np.quantile(column, np.linspace(0, 1, 11))).astype(float)
        edges.append(e.tolist())
        bins = np.searchsorted(e[1:-1], column, side="right")
        frac.append((np.bincount(bins, minlength=max(1, len(e) - 1)) / max(len(column), 1)).astype(float).tolist())
    return {"edges": edges, "frac": frac}


def fit_profile(profile: Profile, X, y, groups, params_override: dict | None = None) -> FittedProfile:
    X, y, groups = np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.float64), np.asarray(groups)
    if X.ndim != 2 or y.ndim != 1 or len(X) != len(y) or len(groups) != len(y):
        raise ValueError("invalid training arrays")
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError("training arrays must be finite")
    test = split_by_scenario(groups)
    train = ~test
    if train.sum() == 0 or test.sum() == 0:
        raise ValueError("training split is empty")
    yfit = y[train] - physics_w_np(X[train]) if profile.target_mode == "residual" else y[train]
    estimator = HistGradientBoostingRegressor(**{**profile.hgb, **(params_override or {})})
    estimator.fit(X[train], yfit)
    pred_train = np.clip(estimator.predict(X[train]) + (physics_w_np(X[train]) if profile.target_mode == "residual" else 0), 0, W0)
    raw_test = estimator.predict(X[test])
    pred_test = np.clip(raw_test + (physics_w_np(X[test]) if profile.target_mode == "residual" else 0), 0, W0)
    metrics = {"r2_train": float(r2_score(y[train], pred_train)), "r2_test": float(r2_score(y[test], pred_test)),
               "mae_test": float(mean_absolute_error(y[test], pred_test))}
    lo, hi = np.min(X[train], axis=0), np.max(X[train], axis=0)
    pad = (hi - lo) * .05
    return FittedProfile(profile, estimator, metrics, (lo - pad).tolist(), (hi + pad).tolist(),
                         _reference(X[train]), float(np.mean(y[train])))
