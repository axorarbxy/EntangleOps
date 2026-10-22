from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import joblib
import sklearn

from app.ml.constants import SCHEMAS
from security.model_integrity import sign_file, verify_file


class ModelIntegrityError(RuntimeError):
    pass


def normalize_payload(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ModelIntegrityError("invalid model payload")
    if "format_version" not in raw:
        # Legacy artifacts were dictionaries containing model and v1 metadata.
        model = raw.get("model")
        if model is None:
            raise ModelIntegrityError("unsupported model payload")
        return {"format_version": 1, "profile": "baseline_v1", "feature_schema": "v1", "target_mode": "direct",
                "horizon_steps": raw.get("horizon_steps"), "estimator": model, "metrics": raw.get("metrics", {}),
                "feature_min": raw.get("feature_min", []), "feature_max": raw.get("feature_max", []),
                "calibration": None, "reference": None, "sklearn_version": None}
    if raw.get("format_version") != 2 or raw.get("feature_schema") not in SCHEMAS or raw.get("target_mode") not in {"direct", "residual"}:
        raise ModelIntegrityError("unsupported model format")
    schema = raw["feature_schema"]
    if len(raw.get("feature_min") or []) != len(SCHEMAS[schema]) or len(raw.get("feature_max") or []) != len(SCHEMAS[schema]):
        raise ModelIntegrityError("invalid feature dimensions")
    version = raw.get("sklearn_version")
    if version and ".".join(version.split(".")[:2]) != ".".join(sklearn.__version__.split(".")[:2]):
        raise ModelIntegrityError("scikit-learn version mismatch")
    if raw.get("estimator") is None:
        raise ModelIntegrityError("missing estimator")
    return raw


def save_payload(payload: dict, path: str | Path, key: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try: path.parent.chmod(0o700)
    except OSError: pass
    joblib.dump(payload, path)
    sign_file(path, key)
    return path


def load_payload(path: str | Path, key: str) -> dict:
    if not verify_file(path, key):
        raise ModelIntegrityError("model signature verification failed")
    try:
        return normalize_payload(joblib.load(path))
    except ModelIntegrityError:
        raise
    except Exception as exc:
        raise ModelIntegrityError("invalid model payload") from exc


def archive_model(path: str | Path, archive_dir: str | Path) -> Path | None:
    source = Path(path)
    sig = source.with_suffix(source.suffix + ".sig")
    if not source.exists(): return None
    archive = Path(archive_dir)
    archive.mkdir(parents=True, exist_ok=True)
    try: archive.chmod(0o700)
    except OSError: pass
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target = archive / f"{digest}.joblib"
    if not target.exists():
        shutil.copy2(source, target)
        try: target.chmod(0o600)
        except OSError: pass
        if sig.exists():
            shutil.copy2(sig, target.with_suffix(".joblib.sig"))
            try: target.with_suffix(".joblib.sig").chmod(0o600)
            except OSError: pass
    return target
