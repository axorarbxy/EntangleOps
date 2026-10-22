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
from sqlalchemy import text
from app.db.migrate import schema_state
from app.db.instrument import db_timer

router = APIRouter()
_STARTED = time.time()

def _db_status(engine):
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        current, head = schema_state(engine)
        return True, current == head
    except Exception:
        return False, False


@router.get("/health/live")
def live():
    return {"status": "alive"}


@router.get("/health")
def health():
    return {"status": "ok"}


def _writable(path: str) -> bool:
    try:
        p = Path(path); p.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=p); os.close(fd); os.unlink(name)
        return True
    except OSError: return False


@router.get("/health/ready")
def ready(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    db_ok,schema_ok=_db_status(engine)
    if hasattr(m,"db_reachable"):m.db_reachable.set(1 if db_ok else 0)
    if hasattr(m,"db_schema_current"):m.db_schema_current.set(1 if schema_ok else 0)
    queue_ok=False
    if db_ok:
        try:queue_ok=request.app.state.store.count_active_all() < settings.max_queued_runs + settings.max_concurrent_runs
        except Exception:queue_ok=False
    checks = [getattr(request.app.state, "predictor", None) is not None,
              _writable(settings.data_dir), db_ok, schema_ok, queue_ok]
    ok = all(checks)
    return JSONResponse({"status": "ready" if ok else "not_ready"}, status_code=200 if ok else 503)


@router.get("/api/v1/admin/health/details")
def details(request: Request, _: Principal = Depends(require_role("admin"))):
    audit = request.app.state.audit
    try: chain_ok = audit.verify_chain(audit._sf if getattr(audit,"_db",False) else audit.path)[0]
    except Exception: chain_ok = False
    db_ok,schema_ok=_db_status(request.app.state.engine)
    checks = {"predictor_loaded": getattr(request.app.state, "predictor", None) is not None,
              "data_dir_writable": _writable(settings.data_dir),
              "keystore_readable": bool(request.app.state.keystore.list() is not None),
              "database_reachable": db_ok,
              "schema_current": schema_ok,
              "audit_chain_ok": chain_ok,
              "metrics_token_configured": not settings.metrics_enabled or len(settings.metrics_token) >= 32}
    predictor = getattr(request.app.state, "predictor", None)
    return {"status": "ok" if all(checks.values()) else "degraded", "uptime_s": max(0, int(time.time()-_STARTED)),
            "version": "1.0.0", "queue": {"capacity": settings.max_queued_runs, "depth": float(m.queue_depth._value.get())},
            "checks": checks, "model_calibrated": bool(getattr(predictor, "calibration", None)),
            "model": {"profile": getattr(predictor, "profile", "legacy"),
                      "feature_schema": getattr(predictor, "feature_schema", "v1")}}
