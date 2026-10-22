from __future__ import annotations

import math
import numpy as np

from app.ml.constants import ALPHAS, GROUPS


class UncalibratedModelError(ValueError):
    pass


def group_codes(aerial_fraction):
    a = np.asarray(aerial_fraction)
    return np.where(a <= 0, 0, np.where(a >= 1, 2, 1))


def conformal_quantile(abs_resid: np.ndarray, alpha: float) -> float:
    if alpha not in ALPHAS:
        raise ValueError("alpha must be one of ALPHAS")
    values = np.asarray(abs_resid, dtype=np.float64).ravel()
    n = values.size
    k = int(math.ceil((n + 1) * (1 - alpha)))
    if n == 0 or k > n or not np.isfinite(values).all():
        raise ValueError("not enough finite calibration points for this alpha")
    return float(np.partition(values, k - 1)[k - 1])


def calibrate(predictor, X_cal, y_cal, alphas=ALPHAS, min_group_n: int = 200, *, suite_name="cal_v1", suite_sha256="",
              train_fingerprints=None, calibration_fingerprints=None) -> dict:
    if train_fingerprints is not None and calibration_fingerprints is not None:
        if set(train_fingerprints).intersection(calibration_fingerprints):
            raise ValueError("calibration suite overlaps training scenarios")
    X, y = np.asarray(X_cal, dtype=np.float64), np.asarray(y_cal, dtype=np.float64)
    if len(X) != len(y) or not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError("calibration arrays must be finite and aligned")
    pred = np.asarray(predictor.predict_w(X), dtype=np.float64)
    residual = np.abs(y - pred)
    names = ("buried", "mixed", "aerial")
    codes = group_codes(X[:, 1])
    global_n = len(y)
    result = {"method": "mondrian_split_conformal", "suite": suite_name, "suite_sha256": suite_sha256,
              "n": {name: int(np.sum(codes == i)) for i, name in enumerate(names)} | {"global": global_n},
              "q": {}, "fallback_groups": []}
    for alpha in alphas:
        if alpha not in ALPHAS:
            raise ValueError("alpha must be one of ALPHAS")
        global_q = conformal_quantile(residual, alpha)
        per = {}
        for i, name in enumerate(names):
            group_residual = residual[codes == i]
            need = max(min_group_n, math.ceil(1 / alpha))
            if len(group_residual) < need:
                per[name] = global_q
                if name not in result["fallback_groups"]:
                    result["fallback_groups"].append(name)
            else:
                per[name] = conformal_quantile(group_residual, alpha)
        per["global"] = global_q
        result["q"][str(alpha)] = per
    return result
