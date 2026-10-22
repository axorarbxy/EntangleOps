from __future__ import annotations

import math
import numpy as np

from app.core.physics import ALPHA_DB_PER_KM, RAMAN_K, W0, A_TEMP, A_WIND, BURIED_LOSS_PER_KM
from app.ml.constants import FEATURES_V1, FEATURES_V2, IDX, SCHEMAS


def werner_np(length_km, aerial_fraction, is_o, load, dtemp_dt, wind):
    length_km = np.asarray(length_km, dtype=np.float64)
    aerial_fraction = np.asarray(aerial_fraction, dtype=np.float64)
    alpha = np.where(is_o, ALPHA_DB_PER_KM["O"], ALPHA_DB_PER_KM["C"])
    k = np.where(is_o, RAMAN_K["O"], RAMAN_K["C"])
    eta = 10.0 ** (-alpha * length_km / 10.0)
    snr = eta / (eta + k * np.maximum(load, 0.0) * length_km)
    aerial_km = length_km * aerial_fraction
    buried_km = length_km - aerial_km
    penalty = ((A_TEMP * np.abs(dtemp_dt) + A_WIND * np.maximum(wind, 0.0)) * aerial_km / 50.0
               + BURIED_LOSS_PER_KM * buried_km)
    return W0 * snr * np.exp(-penalty)


def physics_w_np(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    return werner_np(X[:, IDX["length_km"]], X[:, IDX["aerial_fraction"]], X[:, IDX["band_is_o"]] > .5,
                     X[:, IDX["traffic_now"]], X[:, IDX["dtemp_dt_now"]], X[:, IDX["wind_now"]])


def build_matrix(env, link, band: str, steps: np.ndarray, schema: str = "v1") -> np.ndarray:
    if schema not in SCHEMAS:
        raise ValueError("unknown feature schema")
    s = np.asarray(steps, dtype=np.int64)
    if s.ndim != 1 or np.any(s < 0) or np.any(s >= env.n_steps):
        raise ValueError("steps outside environment")
    load, temp = env.traffic[link.link_id], env.temp_c[link.link_id]
    dtemp, wind = env.dtemp_dt[link.link_id], env.wind_ms[link.link_id]
    h = (s * env.dt_s / 3600.0) % 24.0
    rows = [np.full(s.size, link.length_km), np.full(s.size, link.aerial_fraction), np.full(s.size, float(band == "O")),
            load[s], load[s] - load[np.maximum(s - 5, 0)], temp[s], dtemp[s], wind[s],
            wind[s] - wind[np.maximum(s - 5, 0)], np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)]
    if schema == "v1":
        return np.column_stack(rows).astype(np.float64, copy=False)
    rows += [wind[s] - wind[np.maximum(s - 15, 0)], load[s] - load[np.maximum(s - 15, 0)],
             dtemp[s] - dtemp[np.maximum(s - 5, 0)]]
    wind_pad = np.concatenate((np.full(30, wind[0]), wind))
    wind_windows = np.lib.stride_tricks.sliding_window_view(wind_pad, 31)
    rows.append(np.max(wind_windows[s], axis=1))
    prefix = np.concatenate(([0.0], np.cumsum(load, dtype=np.float64)))
    starts = np.maximum(s - 30, 0)
    rows.append((prefix[s + 1] - prefix[starts]) / (s - starts + 1))
    rows.append(np.full(s.size, link.length_km * link.aerial_fraction))
    v1 = np.column_stack(rows).astype(np.float64, copy=False)
    rows.append(physics_w_np(v1))
    return np.column_stack(rows).astype(np.float64, copy=False)


def build_features(env, link, band: str, t: int, schema: str = "v1") -> list[float]:
    if schema == "v1":
        h = (t * env.dt_s / 3600) % 24
        return [link.length_km, link.aerial_fraction, float(band == "O"), float(env.traffic[link.link_id][t]),
                env.trend(env.traffic, link.link_id, t), float(env.temp_c[link.link_id][t]),
                float(env.dtemp_dt[link.link_id][t]), float(env.wind_ms[link.link_id][t]),
                env.trend(env.wind_ms, link.link_id, t), math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24)]
    return build_matrix(env, link, band, np.asarray([t]), schema)[0].tolist()
