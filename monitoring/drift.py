from __future__ import annotations

import logging
import math

from . import metrics as m

log = logging.getLogger(__name__)


class DriftMonitor:
    def __init__(self, predictor, env, links, alpha: float = 0.05, sample_every: int = 10) -> None:
        self.predictor, self.env, self.links = predictor, env, links
        self.alpha, self.sample_every = alpha, max(1, sample_every)
        self.samples = 0
        self.ewma: float | None = None
        self.out, self.total = 0, 0

    def __call__(self, record) -> None:
        try:
            from app.core.predictor import build_features
            from app.core.physics import BANDS, link_werner
            t = record.step
            if t % self.sample_every:
                return
            for lid, link in self.links.items():
                for band in BANDS:
                    x = build_features(self.env, link, band, t)
                    pred = float(self.predictor.predict_w([x])[0])
                    target_t = min(self.env.n_steps - 1, t + max(0, int(getattr(self.predictor, "horizon_steps", 0))))
                    actual = float(link_werner(link, band, self.env.conditions(lid, target_t)))
                    err = abs(pred - actual)
                    self.ewma = err if self.ewma is None else self.alpha * err + (1-self.alpha) * self.ewma
                    m.predictor_abs_error.observe(err)
                    self.samples += 1
                    lo, hi = getattr(self.predictor, "feature_min", []), getattr(self.predictor, "feature_max", [])
                    self.out += bool(lo and hi and any(v < a or v > b for v, a, b in zip(x, lo, hi)))
                    self.total += 1
            if self.ewma is not None:
                m.predictor_mae.set(self.ewma)
            m.predictor_oor.set(self.out / self.total if self.total else 0)
        except Exception:
            log.exception("Predictor drift sample failed")
