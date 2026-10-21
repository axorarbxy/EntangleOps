from __future__ import annotations
from contextlib import asynccontextmanager
import logging,os
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router
from app.api.ws import router as ws_router
from app.core.predictor import FidelityPredictor
from app.services.runner import RunStore
from security.validation import enforce,InsecureConfigError
from security.keys import KeyStore
from security.audit import AuditLog
from security.ratelimit import TokenBucketLimiter
from security.tickets import TicketService
from security.netutil import make_client_ip
from security.middleware import BodySizeLimitMiddleware,RequestIdMiddleware,SecurityHeadersMiddleware
from monitoring.endpoint import router as metrics_router
from monitoring.health import router as health_router
from monitoring.middleware import MetricsMiddleware
from monitoring.logging_config import configure_logging
from monitoring.audit_hooks import on_audit_event
from monitoring.tasks import loop_lag_task,audit_verify_task
from monitoring import metrics as mon
import asyncio

@asynccontextmanager
async def lifespan(app:FastAPI):
    configure_logging(settings.log_level,settings.log_json)
    try:enforce(settings)
    except InsecureConfigError:
        AuditLog(settings.audit_path).event("config.invalid",env=settings.env)
        raise
    app.state.store=RunStore()
    app.state.audit=AuditLog(settings.audit_path)
    app.state.audit.add_listener(on_audit_event)
    if settings.env!="production" and not settings.api_key_pepper:logging.getLogger(__name__).warning("EO_API_KEY_PEPPER is unset; using a development-only fallback pepper")
    app.state.keystore=KeyStore(settings.keys_path,settings.api_key_pepper or "development-only-pepper")
    app.state.ticket_service=TicketService(settings.api_key_pepper or settings.model_signing_key or "development-only-ticket-secret",settings.ws_ticket_ttl_s)
    app.state.client_ip=make_client_ip(settings.trusted_proxy_count)
    app.state.limiter_key=TokenBucketLimiter(settings.rate_per_key_per_min)
    app.state.limiter_ip=TokenBucketLimiter(settings.rate_per_ip_per_min)
    app.state.limiter_auth_fail=TokenBucketLimiter(settings.rate_auth_fail_per_ip_per_min)
    app.state.ws_counts={}
    app.state.audit.event("startup",env=settings.env)
    app.state.predictor=FidelityPredictor.load_or_train(settings.model_path,settings.forecast_horizon_steps,settings.default_seed)
    mon.build_info.labels("1.0.0",settings.env).set(1);mon.queue_capacity.set(settings.max_queued_runs)
    if settings.env!="production" and settings.metrics_enabled and not settings.metrics_token:logging.getLogger(__name__).warning("EO_METRICS_TOKEN is unset; /metrics is open in development")
    tasks=[asyncio.create_task(loop_lag_task(settings.loop_lag_interval_s)),asyncio.create_task(audit_verify_task(app.state.audit,settings.audit_verify_interval_s))]
    try:yield
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

def create_app()->FastAPI:
    if settings.env=="production":
        try:enforce(settings)
        except InsecureConfigError:
            AuditLog(settings.audit_path).event("config.invalid",env=settings.env)
            raise
    docs=settings.enable_docs
    if settings.env=="production" and os.environ.get("EO_ENABLE_DOCS","").lower()!="true":docs=False
    app=FastAPI(title="EntangleOps API",description="Quantum network digital twin and control plane. Physical constants are illustrative and are not calibrated to a specific experiment.",version="1.0.0",lifespan=lifespan,docs_url="/docs" if docs else None,redoc_url="/redoc" if docs else None,openapi_url="/openapi.json" if docs else None)
    @app.middleware("http")
    async def ip_rate_limit(request:Request,call_next):
        if request.url.path.startswith("/api/v1") and hasattr(request.app.state,"limiter_ip"):
            ip=request.app.state.client_ip(request)
            if not request.app.state.limiter_ip.consume(ip):
                request.app.state.audit.event("ratelimit.ip",ip=ip,path=request.url.path)
                import re,secrets
                incoming=request.headers.get("x-request-id","");rid=incoming if re.fullmatch(r"[A-Za-z0-9_-]{8,64}",incoming) else secrets.token_urlsafe(9)
                headers={"Retry-After":"30","X-Request-ID":rid,"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Cross-Origin-Resource-Policy":"same-site","Permissions-Policy":"geolocation=(), camera=(), microphone=()","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'","Cache-Control":"no-store"}
                if settings.behind_tls:headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
                return JSONResponse({"error":"rate_limited"},status_code=429,headers=headers)
        return await call_next(request)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request:Request,exc:RequestValidationError):
        return JSONResponse({"error":"validation","fields":[{"loc":e.get("loc",[]),"msg":e.get("msg","invalid")} for e in exc.errors()]},status_code=422)
    @app.exception_handler(Exception)
    async def internal_error(request:Request,exc:Exception):
        logging.getLogger(__name__).exception("Unhandled request exception",exc_info=exc)
        return JSONResponse({"error":"internal","request_id":getattr(request.state,"request_id","unknown")},status_code=500)
    app.include_router(router,prefix="/api/v1");app.include_router(ws_router)
    app.include_router(metrics_router);app.include_router(health_router)
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_methods=["GET","POST","DELETE"],allow_headers=["X-API-Key","Content-Type","Authorization","X-Request-ID"],allow_credentials=False,max_age=600)
    app.add_middleware(BodySizeLimitMiddleware,max_bytes=settings.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware,hsts=settings.behind_tls)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app
app=create_app()
