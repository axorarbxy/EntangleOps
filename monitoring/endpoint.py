from __future__ import annotations
import hmac
from fastapi import APIRouter,Request,Response
from prometheus_client import CONTENT_TYPE_LATEST,generate_latest
from app.config import settings
from monitoring.metrics import registry

router=APIRouter()
@router.get("/metrics",include_in_schema=False)
async def metrics(request:Request)->Response:
    if not settings.metrics_enabled:return Response(status_code=404)
    token=settings.metrics_token
    if token:
        header=request.headers.get("authorization","");presented=header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(presented.encode(),token.encode()):return Response(status_code=401,headers={"WWW-Authenticate":"Bearer"})
    return Response(generate_latest(registry),media_type=CONTENT_TYPE_LATEST)
