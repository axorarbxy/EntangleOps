from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from app.config import settings
from app.db.runtime import open_database
from security.audit import AuditLog


def require_signing_key():
    key=settings.model_signing_key
    if len(key)<32:raise SystemExit("set EO_MODEL_SIGNING_KEY (>= 32 chars) before using ML scripts")
    return key


def open_ml_db():
    return open_database(migrate_development=True)


def audit(sf, kind, **fields):
    AuditLog(sf).event(kind,actor="cli",**fields)


def git_version():
    try:return subprocess.run(["git","rev-parse","--short","HEAD"],capture_output=True,text=True,timeout=3,check=True).stdout.strip()
    except Exception:return os.getenv("GIT_COMMIT","unknown")[:64]


def dump_report(value):
    print(json.dumps(value,indent=2,sort_keys=True,allow_nan=False))


def candidate_path(sha256):
    return Path(settings.ml_models_dir)/f"{sha256}.joblib"
