from __future__ import annotations

import time
from typing import Protocol

import numpy as np


class PredictorLike(Protocol):
    feature_schema: str
    horizon_steps: int
    def predict_w(self, X: np.ndarray) -> np.ndarray: ...


class RowCachePredictor:
    def __init__(self, inner, max_rows: int = 50_000, on_event=None) -> None:
        self._inner, self._max, self._on_event = inner, max(0, int(max_rows)), on_event
        self._point: dict[bytes, float] = {}
        self._interval: dict[tuple[float, bytes], tuple[float, float, float]] = {}

    @property
    def feature_schema(self): return getattr(self._inner, "feature_schema", "v1")
    @property
    def horizon_steps(self): return self._inner.horizon_steps
    @property
    def calibration(self): return getattr(self._inner, "calibration", None)
    @property
    def reference(self): return getattr(self._inner, "reference", None)
    @property
    def feature_min(self): return getattr(self._inner, "feature_min", [])
    @property
    def feature_max(self): return getattr(self._inner, "feature_max", [])

    def _emit(self, result, rows, seconds, kind):
        if self._on_event is not None:
            try: self._on_event(result, rows, seconds, kind)
            except Exception: pass

    def predict_w(self, X):
        X = np.atleast_2d(np.ascontiguousarray(X, dtype=np.float64))
        keys = [row.tobytes() for row in X]
        out = np.empty(len(keys), dtype=np.float64)
        misses = []
        for i, key in enumerate(keys):
            if key in self._point: out[i] = self._point[key]
            else: misses.append(i)
        if misses:
            started = time.perf_counter(); values = np.asarray(self._inner.predict_w(X[misses]), dtype=np.float64)
            for i, value in zip(misses, values):
                if self._max and len(self._point) + len(self._interval) < self._max: self._point[keys[i]] = float(value)
                out[i] = value
            self._emit("miss", len(misses), time.perf_counter() - started, "point")
        self._emit("hit", len(keys) - len(misses), 0.0, "point")
        return out

    def predict_w_interval(self, X, alpha):
        values = self._interval_values(X, alpha)
        return values[:, 0], values[:, 1]

    def _interval_values(self, X, alpha):
        X = np.atleast_2d(np.ascontiguousarray(X, dtype=np.float64))
        keys = [(float(alpha), row.tobytes()) for row in X]
        out = np.empty((len(keys), 3), dtype=np.float64); misses = []
        for i, key in enumerate(keys):
            if key in self._interval: out[i] = self._interval[key]
            else: misses.append(i)
        if misses:
            started = time.perf_counter()
            values = self._inner.predict_w_interval_full(X[misses], alpha) if hasattr(self._inner, "predict_w_interval_full") else self._inner.predict_w_interval(X[misses], alpha)
            point, lo = values[0], values[1]
            hi = values[2] if len(values) >= 3 else lo
            for i, p, l, h in zip(misses, point, lo, hi):
                if self._max and len(self._point) + len(self._interval) < self._max: self._interval[keys[i]] = (float(p), float(l), float(h))
                out[i] = (p,l,h)
            self._emit("miss", len(misses), time.perf_counter() - started, "interval")
        self._emit("hit", len(keys) - len(misses), 0.0, "interval")
        return out

    def predict_w_interval_full(self, X, alpha):
        values=self._interval_values(X,alpha)
        return values[:,0],values[:,1],values[:,2]
