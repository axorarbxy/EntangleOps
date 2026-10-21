from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.config import settings
from security.auth import Principal, require_role
from . import metrics as m

router = APIRouter()
_STARTED = time.time()


@router.get("/health/live")
@router.get("/health")
def live():
    return {"status": "alive"}


def _writable(path: str) -> bool:
    try:
        p = Path(path); p.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=p); os.close(fd); os.unlink(name)
        return True
    except OSError: return False


@router.get("/health/ready")
def ready(request: Request):
    checks = [getattr(request.app.state, "predictor", None) is not None,
              _writable(settings.data_dir),
              sum(1 for r in getattr(getattr(request.app.state, "store", None), "runs", {}).values() if r["status"] == "queued") < settings.max_queued_runs]
    ok = all(checks)
    return JSONResponse({"status": "ready" if ok else "not_ready"}, status_code=200 if ok else 503)


@router.get("/api/v1/admin/health/details")
def details(request: Request, _: Principal = Depends(require_role("admin"))):
    audit = request.app.state.audit
    try: chain_ok = audit.verify_chain(audit.path)[0]
    except Exception: chain_ok = False
    checks = {"predictor_loaded": getattr(request.app.state, "predictor", None) is not None,
              "data_dir_writable": _writable(settings.data_dir),
              "keystore_readable": bool(request.app.state.keystore.list() is not None),
              "audit_writable": _writable(str(Path(settings.audit_path).parent)),
              "audit_chain_ok": chain_ok,
              "metrics_token_configured": not settings.metrics_enabled or len(settings.metrics_token) >= 32}
    return {"status": "ok" if all(checks.values()) else "degraded", "uptime_s": max(0, int(time.time()-_STARTED)),
            "version": "1.0.0", "queue": {"capacity": settings.max_queued_runs, "depth": float(m.queue_depth._value.get())}, "checks": checks}
