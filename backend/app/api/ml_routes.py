from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.db.session import run_db
from security.auth import Principal, require_role

router = APIRouter()
EXP_ID = r"^exp_[A-Za-z0-9_-]{8,32}$"


@router.get("/model")
async def active_model(request: Request, _: Principal = Depends(require_role("viewer"))):
    row = await run_db(request.app.state.ml_service.registry.active)
    return request.app.state.ml_service.expose_model(row)


@router.get("/experiments")
async def experiments(request: Request, kind: str | None = None, limit: int = Query(default=50, ge=1, le=200),
                      _: Principal = Depends(require_role("viewer"))):
    from app.ml.constants import EXPERIMENT_KINDS
    if kind is not None and kind not in EXPERIMENT_KINDS: raise HTTPException(422, "invalid experiment kind")
    try: rows = await run_db(request.app.state.ml_service.experiments.list, kind, limit)
    except ValueError as exc: raise HTTPException(422, "invalid experiment query") from exc
    return [{k: row[k] for k in ("id", "kind", "name", "profile", "model_id", "created_at", "code_version")} for row in rows]


@router.get("/experiments/{exp_id}")
async def experiment(request: Request, exp_id: str = Path(pattern=EXP_ID), _: Principal = Depends(require_role("viewer"))):
    row = await run_db(request.app.state.ml_service.experiments.get, exp_id)
    if row is None: raise HTTPException(404, "not found")
    return row
