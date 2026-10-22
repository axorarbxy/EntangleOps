"""Load and run the trained SLATE-PTP one-way delay regressor."""

from __future__ import annotations

from pathlib import Path

import numpy as np


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "slate_ptp_delay_mlp.npz"
MODES = ("M1", "M2", "M3")
TRAFFIC_TYPES = ("IMIX", "LP", "MTU", "SP", "NO")
MESSAGES = ("sync", "delay_req")


def predict_one_way_delay_us(
    *,
    progress: float,
    mode: str,
    load_low_pct: float,
    load_high_pct: float,
    duration_minutes: float,
    traffic_model: str,
    message_type: str,
    recent_same_message_delays_us: tuple[float, ...] | list[float] = (),
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> float:
    """Predict one-way PTP delay from run conditions and up to five prior delays.

    ``progress`` is elapsed run fraction in [0, 1]. History must contain only prior
    rows of the same PTP message type, in chronological order.
    """
    if mode not in MODES or traffic_model not in TRAFFIC_TYPES or message_type not in MESSAGES:
        raise ValueError("mode, traffic_model, or message_type is not supported")
    if not 0 <= progress <= 1:
        raise ValueError("progress must be between 0 and 1")
    history = np.asarray(tuple(recent_same_message_delays_us)[-5:], dtype=np.float32)
    if np.any(~np.isfinite(history)) or np.any(history <= 0):
        raise ValueError("history values must be positive finite delays in microseconds")
    x = np.asarray([[
        progress,
        duration_minutes / 900.0,
        load_low_pct / 100.0,
        load_high_pct / 100.0,
        *(float(mode == item) for item in MODES),
        *(float(traffic_model == item) for item in TRAFFIC_TYPES),
        *(float(message_type == item) for item in MESSAGES),
        float(history[-1]) if len(history) else 0.0,
        float(history.mean()) if len(history) else 0.0,
        float(history.std()) if len(history) else 0.0,
        float(bool(len(history))),
    ]], dtype=np.float32)
    with np.load(model_path) as artifact:
        x_mean, x_scale = artifact["x_mean"], artifact["x_scale"]
        y_mean, y_scale = float(artifact["y_mean"][0]), float(artifact["y_scale"][0])
        w1, b1, w2, b2, w3, b3 = (artifact[f"arr_{i}"] for i in range(6))
    x = (x - x_mean) / x_scale
    h1 = np.maximum(x @ w1 + b1, 0.0)
    h2 = np.maximum(h1 @ w2 + b2, 0.0)
    prediction = float((h2 @ w3 + b3)[0, 0] * y_scale + y_mean)
    return max(prediction, 0.0)
