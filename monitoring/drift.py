from __future__ import annotations

import logging

import numpy as np

from app.core.physics import BANDS, link_werner
from app.ml.constants import ALPHAS
from app.ml.drift import FeatureDriftTracker
from app.ml.features import build_features
from . import metrics as m

log = logging.getLogger(__name__)


class DriftMonitor:
    def __init__(self, predictor, env, links, alpha: float = .05, sample_every: int = 10, *, window_rows=2000, min_rows=500):
        self.predictor, self.env, self.links = predictor, env, links
        self.alpha, self.sample_every = alpha, max(1, sample_every)
        self.samples = 0; self.ewma = None; self.out = self.total = 0
        self.tracker = FeatureDriftTracker(getattr(predictor, "reference", None), window_rows, min_rows)
        self._coverage = {a: None for a in ALPHAS}; self._width = {a: None for a in ALPHAS}

    def __call__(self, record) -> None:
        try:
            t = int(record.step)
            if t % self.sample_every: return
            horizon = max(0, int(getattr(self.predictor, "horizon_steps", 0)))
            for lid, link in self.links.items():
                for band in BANDS:
                    current_x = build_features(self.env, link, band, t, schema=self.predictor.feature_schema)
                    for name, value in self.tracker.observe(current_x).items():
                        m.ml_feature_psi.labels(m.bounded(name, m.ML_FEATURES)).set(value)
                    history_t = max(0, t - horizon)
                    x = np.asarray([build_features(self.env, link, band, history_t, schema=self.predictor.feature_schema)])
                    target = float(link_werner(link, band, self.env.conditions(lid, t)))
                    pred = float(self.predictor.predict_w(x)[0])
                    err = abs(pred - target)
                    self.ewma = err if self.ewma is None else self.alpha * err + (1-self.alpha) * self.ewma
                    m.predictor_abs_error.observe(err); self.samples += 1
                    lo, hi = getattr(self.predictor, "feature_min", []), getattr(self.predictor, "feature_max", [])
                    self.out += bool(lo and hi and any(v < a or v > b for v, a, b in zip(x[0], lo, hi)))
                    self.total += 1
                    if getattr(self.predictor, "calibration", None):
                        for a in ALPHAS:
                            try:
                                _point, lower, upper = self.predictor.predict_w_interval_full(x, a)
                                hit = float(lower[0] <= target <= upper[0]); width = float(upper[0] - lower[0])
                                self._coverage[a] = hit if self._coverage[a] is None else self.alpha * hit + (1-self.alpha) * self._coverage[a]
                                self._width[a] = width if self._width[a] is None else self.alpha * width + (1-self.alpha) * self._width[a]
                                m.ml_interval_coverage.labels(str(a)).set(self._coverage[a])
                                m.ml_interval_width.labels(str(a)).set(self._width[a])
                            except Exception: continue
            if self.ewma is not None: m.predictor_mae.set(self.ewma)
            m.predictor_oor.set(self.out / self.total if self.total else 0)
        except Exception:
            log.exception("Predictor drift sample failed")
