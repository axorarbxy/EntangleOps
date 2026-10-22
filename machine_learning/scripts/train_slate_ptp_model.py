from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import deque
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = ROOT / "machine_learning"
DATA_ROOT = ROOT / "data"
MODEL_DIR = ML_ROOT / "models"
REPORT_DIR = ML_ROOT / "reports"
MODEL_PATH = MODEL_DIR / "slate_ptp_delay_mlp.npz"
REPORT_PATH = REPORT_DIR / "slate_ptp_training_report.json"
CARD_PATH = REPORT_DIR / "slate_ptp_model_card.md"

TRAFFIC_TYPES = ("IMIX", "LP", "MTU", "SP", "NO")
MODES = ("M1", "M2", "M3")
MESSAGES = ("sync", "delay_req")
FEATURE_NAMES = (
    "progress", "duration_fraction", "load_low_fraction", "load_high_fraction",
    "mode_M1", "mode_M2", "mode_M3",
    "traffic_IMIX", "traffic_LP", "traffic_MTU", "traffic_SP", "traffic_NO",
    "message_sync", "message_delay_req",
    "lag1_delay_us", "lag5_mean_delay_us", "lag5_std_delay_us", "has_lag",
)
NAME_RE = re.compile(r"^(M[123])-L(\d+)-T(\d+)-TM([A-Z]+)\.csv$")
MAX_SAMPLES_PER_FILE = 4_000
RANDOM_SEED = 20261022


def metadata_for(path: Path) -> dict:
    match = NAME_RE.match(path.name)
    if not match:
        raise ValueError(f"unexpected SLATE-PTP filename: {path.name}")
    mode, load_code, duration, traffic = match.groups()
    code = int(load_code)
    if mode == "M1":
        load_low = load_high = code
    else:
        load_low, load_high = divmod(code, 100)
    if traffic not in TRAFFIC_TYPES:
        raise ValueError(f"unsupported traffic model in {path.name}: {traffic}")
    return {
        "mode": mode,
        "load_low": load_low,
        "load_high": load_high,
        "duration_minutes": int(duration),
        "traffic": traffic,
    }


def one_hot(value: str, categories: tuple[str, ...]) -> list[float]:
    return [float(value == category) for category in categories]


def read_track(path: Path) -> tuple[np.ndarray, np.ndarray, int]:
    info = metadata_for(path)
    features: list[list[float]] = []
    targets: list[float] = []
    invalid = 0
    duration_seconds = info["duration_minutes"] * 60.0
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        expected = ["seq_id", "capture_ts", "msg_type", "t1", "t2", "t3", "t4"]
        if reader.fieldnames != expected:
            raise ValueError(f"unexpected columns in {path.name}: {reader.fieldnames}")
        first_capture = None
        pending: list[tuple[dict[str, str], int, int]] = []
        for row in reader:
            try:
                capture = int(row["capture_ts"])
                msg = row["msg_type"]
                tx_col, rx_col = ("t1", "t2") if msg == "sync" else ("t3", "t4")
                if msg not in MESSAGES or not row[tx_col] or not row[rx_col]:
                    invalid += 1
                    continue
                delay_ns = int(row[rx_col]) - int(row[tx_col])
                if delay_ns <= 0 or delay_ns >= 1_000_000:
                    invalid += 1
                    continue
                first_capture = capture if first_capture is None else min(first_capture, capture)
                pending.append((row, capture, delay_ns))
            except (KeyError, TypeError, ValueError):
                invalid += 1
        if first_capture is None:
            raise ValueError(f"no valid PTP timestamp rows found in {path.name}")
        previous_delays = {message: deque(maxlen=5) for message in MESSAGES}
        for row, capture, delay_ns in sorted(pending, key=lambda item: item[1]):
            progress = min(max((capture - first_capture) / 1_000_000_000 / duration_seconds, 0.0), 1.0)
            msg = row["msg_type"]
            recent = previous_delays[msg]
            recent_values = np.asarray(recent, dtype=np.float32)
            lag1 = float(recent_values[-1]) if len(recent_values) else 0.0
            lag_mean = float(recent_values.mean()) if len(recent_values) else 0.0
            lag_std = float(recent_values.std()) if len(recent_values) else 0.0
            vector = [
                progress,
                duration_seconds / 54_000.0,
                info["load_low"] / 100.0,
                info["load_high"] / 100.0,
                *one_hot(info["mode"], MODES),
                *one_hot(info["traffic"], TRAFFIC_TYPES),
                *one_hot(msg, MESSAGES),
                lag1, lag_mean, lag_std, float(bool(len(recent))),
            ]
            features.append(vector)
            delay_us = delay_ns / 1_000.0
            targets.append(delay_us)
            recent.append(delay_us)
    return np.asarray(features, dtype=np.float32), np.asarray(targets, dtype=np.float32), invalid


def select_per_file(x: np.ndarray, y: np.ndarray, cap: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    if len(y) <= cap:
        return x, y
    indices = np.sort(rng.choice(len(y), size=cap, replace=False))
    return x[indices], y[indices]


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    ss_total = float(np.sum((actual - np.mean(actual)) ** 2))
    return {
        "mae_us": float(np.mean(np.abs(error))),
        "rmse_us": float(np.sqrt(np.mean(error**2))),
        "r2": float(1.0 - np.sum(error**2) / ss_total) if ss_total else 0.0,
    }


def forward(x: np.ndarray, weights: tuple[np.ndarray, ...]) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    w1, b1, w2, b2, w3, b3 = weights
    z1 = x @ w1 + b1
    h1 = np.maximum(z1, 0.0)
    z2 = h1 @ w2 + b2
    h2 = np.maximum(z2, 0.0)
    output = h2 @ w3 + b3
    return output, (x, z1, h1, z2, h2)


def train_network(x_train: np.ndarray, y_train: np.ndarray, x_val: np.ndarray, y_val: np.ndarray) -> tuple[tuple[np.ndarray, ...], list[dict]]:
    rng = np.random.default_rng(RANDOM_SEED)
    in_dim = x_train.shape[1]
    weights = (
        rng.normal(0, np.sqrt(2 / in_dim), (in_dim, 24)).astype(np.float32), np.zeros(24, np.float32),
        rng.normal(0, np.sqrt(2 / 24), (24, 12)).astype(np.float32), np.zeros(12, np.float32),
        rng.normal(0, np.sqrt(2 / 12), (12, 1)).astype(np.float32), np.zeros(1, np.float32),
    )
    first_moments = tuple(np.zeros_like(p) for p in weights)
    second_moments = tuple(np.zeros_like(p) for p in weights)
    beta1, beta2, epsilon, learning_rate = 0.9, 0.999, 1e-8, 0.001
    batch_size, max_epochs, patience = 1024, 24, 5
    step = 0
    best_loss = float("inf")
    best_weights = tuple(p.copy() for p in weights)
    best_epoch = 0
    no_improve = 0
    history = []
    for epoch in range(max_epochs):
        order = rng.permutation(len(y_train))
        for start in range(0, len(order), batch_size):
            ix = order[start:start + batch_size]
            xb, yb = x_train[ix], y_train[ix, None]
            prediction, cache = forward(xb, weights)
            x0, z1, h1, z2, h2 = cache
            grad_out = (2.0 / len(ix)) * (prediction - yb)
            w1, b1, w2, b2, w3, b3 = weights
            gw3 = h2.T @ grad_out
            gb3 = np.sum(grad_out, axis=0)
            gh2 = grad_out @ w3.T
            gz2 = gh2 * (z2 > 0)
            gw2 = h1.T @ gz2
            gb2 = np.sum(gz2, axis=0)
            gh1 = gz2 @ w2.T
            gz1 = gh1 * (z1 > 0)
            gw1 = x0.T @ gz1
            gb1 = np.sum(gz1, axis=0)
            gradients = (gw1, gb1, gw2, gb2, gw3, gb3)
            step += 1
            updated = []
            for i, (parameter, gradient) in enumerate(zip(weights, gradients)):
                first_moments[i][...] *= beta1
                first_moments[i][...] += (1 - beta1) * gradient
                second_moments[i][...] *= beta2
                second_moments[i][...] += (1 - beta2) * gradient * gradient
                m_hat = first_moments[i] / (1 - beta1**step)
                v_hat = second_moments[i] / (1 - beta2**step)
                updated.append(parameter - learning_rate * m_hat / (np.sqrt(v_hat) + epsilon))
            weights = tuple(updated)
        val_prediction, _ = forward(x_val, weights)
        val_loss = float(np.mean((val_prediction[:, 0] - y_val) ** 2))
        history.append({"epoch": epoch + 1, "validation_mse_us2": val_loss})
        if val_loss < best_loss - 1e-8:
            best_loss = val_loss
            best_weights = tuple(p.copy() for p in weights)
            best_epoch = epoch + 1
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break
    return best_weights, history[:best_epoch]


def main() -> None:
    files = sorted(DATA_ROOT.glob("*.csv"))
    if not files:
        raise SystemExit(f"No CSV tracks found in {DATA_ROOT}")
    rng = np.random.default_rng(RANDOM_SEED)
    train_x, train_y, val_x, val_y = [], [], [], []
    train_files, val_files, invalid_rows = [], [], 0
    per_file_rows = {}
    for path in files:
        x, y, invalid = read_track(path)
        invalid_rows += invalid
        # Split whole experimental runs; no rows from a validation file enter training.
        is_validation = int.from_bytes(hashlib.sha256(path.name.encode()).digest()[:4], "big") % 5 == 0
        sx, sy = select_per_file(x, y, MAX_SAMPLES_PER_FILE, rng)
        per_file_rows[path.name] = {"valid_rows": len(y), "used_rows": len(sy), "invalid_rows": invalid}
        if is_validation:
            val_x.append(sx); val_y.append(sy); val_files.append(path.name)
        else:
            train_x.append(sx); train_y.append(sy); train_files.append(path.name)
    if not val_x or not train_x:
        raise SystemExit("The grouped split did not produce both training and validation files")

    x_train_raw, y_train_raw = np.vstack(train_x), np.concatenate(train_y)
    x_val_raw, y_val_raw = np.vstack(val_x), np.concatenate(val_y)
    x_mean = x_train_raw.mean(axis=0)
    x_scale = x_train_raw.std(axis=0)
    x_scale[x_scale < 1e-6] = 1.0
    y_mean = float(y_train_raw.mean())
    y_scale = float(y_train_raw.std()) or 1.0
    x_train = ((x_train_raw - x_mean) / x_scale).astype(np.float32)
    x_val = ((x_val_raw - x_mean) / x_scale).astype(np.float32)
    y_train = ((y_train_raw - y_mean) / y_scale).astype(np.float32)
    y_val = ((y_val_raw - y_mean) / y_scale).astype(np.float32)

    weights, history = train_network(x_train, y_train, x_val, y_val)
    pred_standard, _ = forward(x_val, weights)
    predictions = pred_standard[:, 0] * y_scale + y_mean
    model_metrics = metrics(y_val_raw, predictions)
    baseline_metrics = metrics(y_val_raw, np.full_like(y_val_raw, y_mean))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MODEL_PATH,
        x_mean=x_mean.astype(np.float32), x_scale=x_scale.astype(np.float32),
        y_mean=np.asarray([y_mean], dtype=np.float32), y_scale=np.asarray([y_scale], dtype=np.float32),
        *weights,
    )
    report = {
        "model": "two-hidden-layer NumPy MLP regressor",
        "target": "one-way PTP path delay in microseconds: t2-t1 for sync, t4-t3 for delay_req",
        "source": "SLATE-PTP CSV tracks in the repository data/ folder",
        "features": list(FEATURE_NAMES),
        "split": "grouped by whole CSV file; SHA-256 filename split, 80/20 target",
        "random_seed": RANDOM_SEED,
        "files_total": len(files),
        "files_train": train_files,
        "files_validation": val_files,
        "rows_train": len(y_train_raw),
        "rows_validation": len(y_val_raw),
        "invalid_rows_skipped": invalid_rows,
        "max_samples_per_file": MAX_SAMPLES_PER_FILE,
        "target_train_mean_us": y_mean,
        "target_validation_min_us": float(y_val_raw.min()),
        "target_validation_max_us": float(y_val_raw.max()),
        "model_validation": model_metrics,
        "mean_baseline_validation": baseline_metrics,
        "epochs_completed": len(history),
        "training_history": history,
        "per_file": per_file_rows,
        "model_file": str(MODEL_PATH.relative_to(ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    CARD_PATH.write_text(
        "# SLATE-PTP one-way delay model\n\n"
        "This model predicts measured one-way PTP path delay from the experiment conditions "
        "and normalized run progress. For `sync` rows, the target is `(t2 - t1)`; for `delay_req` "
        "rows, it is `(t4 - t3)`, converted from nanoseconds to microseconds.\n\n"
        "It is a separate network telemetry model and does not replace EntangleOps' synthetic "
        "Werner-fidelity predictor. The target measurements come from the SLATE-PTP testbed; "
        "generalization beyond those captured configurations is not established. Validation "
        "holds out complete CSV runs.\n\n"
        f"- Training rows: {len(y_train_raw):,} across {len(train_files)} files\n"
        f"- Validation rows: {len(y_val_raw):,} across {len(val_files)} held-out files\n"
        f"- Validation MAE: {model_metrics['mae_us']:.6f} µs (mean baseline {baseline_metrics['mae_us']:.6f} µs)\n"
        f"- Validation RMSE: {model_metrics['rmse_us']:.6f} µs (mean baseline {baseline_metrics['rmse_us']:.6f} µs)\n"
        f"- Validation R²: {model_metrics['r2']:.6f} (mean baseline {baseline_metrics['r2']:.6f})\n"
        f"- Model artifact: `{MODEL_PATH.relative_to(ROOT).as_posix()}`\n"
        f"- Detailed report: `{REPORT_PATH.relative_to(ROOT).as_posix()}`\n",
        encoding="utf-8",
    )
    print(json.dumps({"model_file": str(MODEL_PATH), "report_file": str(REPORT_PATH),
                      "rows_train": len(y_train_raw), "rows_validation": len(y_val_raw),
                      "validation": model_metrics, "baseline": baseline_metrics,
                      "epochs": len(history)}, indent=2))


if __name__ == "__main__":
    main()
