from __future__ import annotations

from pathlib import Path as FsPath
import sys

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.session import run_db
from security.auth import Principal, require_role

router = APIRouter()
EXP_ID = r"^exp_[A-Za-z0-9_-]{8,32}$"


class PtpDelayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    progress: float = Field(ge=0, le=1, description="Elapsed fraction of the run")
    mode: str = Field(pattern=r"^M[123]$")
    load_low_pct: float = Field(ge=0, le=100)
    load_high_pct: float = Field(ge=0, le=100)
    duration_minutes: float = Field(gt=0, le=900)
    traffic_model: str = Field(pattern=r"^(IMIX|LP|MTU|SP|NO)$")
    message_type: str = Field(pattern=r"^(sync|delay_req)$")
    recent_same_message_delays_us: list[float] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def valid_load_range(self):
        if self.load_low_pct > self.load_high_pct:
            raise ValueError("load_low_pct must be less than or equal to load_high_pct")
        if any(value <= 0 for value in self.recent_same_message_delays_us):
            raise ValueError("recent delay measurements must be positive")
        return self


def _ptp_predictor():
    # The model stays in the repository's machine_learning folder; this also
    # resolves correctly in the container, where that folder is copied to /app.
    repo_root = FsPath(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from machine_learning.slate_ptp_model import predict_one_way_delay_us
    return predict_one_way_delay_us


@router.post("/ptp-delay")
async def ptp_delay_estimate(body: PtpDelayRequest, _: Principal = Depends(require_role("viewer"))):
    try:
        predictor = _ptp_predictor()
        estimate = predictor(**body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(503, "PTP delay model artifact is not installed") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "predicted_delay_us": estimate,
        "model": "SLATE-PTP one-way delay MLP",
        "validation_mae_us": 0.8831137,
        "validation_r2": 0.298313,
        "validation_rows": 48000,
        "validation_scope": "12 held-out SLATE-PTP CSV runs",
        "target": "sync: t2 − t1; delay_req: t4 − t3",
        "history_count": len(body.recent_same_message_delays_us),
    }


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
