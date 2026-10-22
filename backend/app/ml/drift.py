from __future__ import annotations

from collections import deque

import numpy as np

from app.ml.constants import DYNAMIC_FEATURES, IDX


def psi(reference_fraction, actual_fraction, floor: float = 1e-4) -> float:
    expected = np.maximum(np.asarray(reference_fraction, dtype=np.float64), floor)
    actual = np.maximum(np.asarray(actual_fraction, dtype=np.float64), floor)
    if expected.shape != actual.shape or not np.isfinite(expected).all() or not np.isfinite(actual).all():
        raise ValueError("PSI fractions must be finite and aligned")
    expected, actual = expected / expected.sum(), actual / actual.sum()
    return float(np.sum((actual - expected) * np.log(actual / expected)))


class FeatureDriftTracker:
    def __init__(self, reference: dict | None, window_rows: int = 2000, min_rows: int = 500):
        self.reference = reference or {"edges": [], "frac": []}
        n_features = len(self.reference.get("edges", []))
        self._features = tuple(name for name in DYNAMIC_FEATURES if IDX[name] < n_features)
        self.window_rows = max(1, int(window_rows)); self.min_rows = max(1, int(min_rows))
        self._rows = {name: deque(maxlen=self.window_rows) for name in self._features}

    @property
    def count(self): return min((len(x) for x in self._rows.values()), default=0)

    def observe(self, row) -> dict[str, float]:
        values = np.asarray(row, dtype=np.float64).reshape(-1)
        for name in self._features:
            self._rows[name].append(float(values[IDX[name]]))
        if self.count < self.min_rows: return {}
        result = {}
        for name in self._features:
            i = IDX[name]
            edges = np.asarray(self.reference.get("edges", [])[i], dtype=np.float64)
            expected = np.asarray(self.reference.get("frac", [])[i], dtype=np.float64)
            if edges.size < 2 or expected.size < 1: continue
            observed = np.asarray(self._rows[name], dtype=np.float64)
            bins = np.searchsorted(edges[1:-1], observed, side="right")
            actual = np.bincount(bins, minlength=expected.size)[:expected.size] / max(len(observed), 1)
            result[name] = psi(expected, actual)
        return result
