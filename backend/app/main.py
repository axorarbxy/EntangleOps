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
from app.core.predictor import FidelityPredictor,set_audit_callback
from app.services.runner import RunStore
from app.db.migrate import schema_state, upgrade_to_head
from app.db.instrument import instrument_pool
from app.db.repos.runs import RunRepo
from app.services.ml_service import MlService
from app.db.session import make_engine, make_session_factory, resolve_url
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
from monitoring.tasks import loop_lag_task,audit_verify_task,db_maintenance_task
from monitoring import metrics as mon
import asyncio
from sqlalchemy.exc import SQLAlchemyError

@asynccontextmanager
async def lifespan(app:FastAPI):
    configure_logging(settings.log_level,settings.log_json)
    try:enforce(settings)
    except InsecureConfigError:
        logging.getLogger(__name__).error("config.invalid env=%s", settings.env)
        raise
    engine=make_engine(resolve_url(settings.database_url.get_secret_value(),settings.database_password_file),
        pool_size=settings.db_pool_size,max_overflow=settings.db_max_overflow,pool_timeout_s=settings.db_pool_timeout_s,
        pool_recycle_s=settings.db_pool_recycle_s,statement_timeout_ms=settings.db_statement_timeout_ms,
        echo=settings.db_echo and settings.env!="production")
    instrument_pool(engine,settings.db_pool_size+settings.db_max_overflow)
    if settings.env!="production" and settings.db_auto_migrate:
        upgrade_to_head(engine)
    else:
        current,head=schema_state(engine)
        if current!=head:
            engine.dispose()
            raise RuntimeError("database schema is not at head; run the migrate job")
    session_factory=make_session_factory(engine)
    app.state.engine=engine;app.state.session_factory=session_factory
    repo=RunRepo(session_factory,settings.max_stored_runs,settings.max_stored_benchmarks)
    app.state.store=RunStore(repo,session_factory)
    app.state.audit=AuditLog(session_factory)
    app.state.audit.add_listener(on_audit_event)
    if settings.env!="production" and not settings.api_key_pepper:logging.getLogger(__name__).warning("EO_API_KEY_PEPPER is unset; using a development-only fallback pepper")
    app.state.keystore=KeyStore(session_factory,settings.api_key_pepper or "development-only-pepper",settings.key_cache_ttl_s)
    app.state.ticket_service=TicketService(settings.api_key_pepper or settings.model_signing_key or "development-only-ticket-secret",settings.ws_ticket_ttl_s,session_factory)
    app.state.client_ip=make_client_ip(settings.trusted_proxy_count)
    app.state.limiter_key=TokenBucketLimiter(settings.rate_per_key_per_min)
    app.state.limiter_ip=TokenBucketLimiter(settings.rate_per_ip_per_min)
    app.state.limiter_auth_fail=TokenBucketLimiter(settings.rate_auth_fail_per_ip_per_min)
    app.state.ws_counts={}
    app.state.audit.event("startup",env=settings.env)
    recovered=repo.reap_stale(settings.run_lease_s)
    if recovered:app.state.audit.event("db.recovered",count=recovered)
    set_audit_callback(app.state.audit.event)
    app.state.predictor=FidelityPredictor.load_or_train(settings.model_path,settings.forecast_horizon_steps,settings.default_seed)
    app.state.ml_service=MlService(session_factory)
    app.state.model_registry=app.state.ml_service.registry
    app.state.model_id=app.state.model_registry.record(settings.model_path,{
        "horizon_steps":app.state.predictor.horizon_steps,"metrics":app.state.predictor.metrics,
        "feature_min":app.state.predictor.feature_min,"feature_max":app.state.predictor.feature_max,
        "profile":app.state.predictor.profile,"feature_schema":app.state.predictor.feature_schema,
        "target_mode":app.state.predictor.target_mode,"calibration":app.state.predictor.calibration,
        "card":app.state.predictor.card,"sklearn_version":app.state.predictor.sklearn_version,
        "n_scenarios":app.state.predictor.n_scenarios,
        "train_seed":app.state.predictor.train_seed,
        "metrics":{**app.state.predictor.metrics,"mean_target":app.state.predictor.mean_target,
                   "format_version":app.state.predictor.format_version}})
    try:
        from monitoring.metrics import bounded
        mon.ml_model_info.labels(bounded(app.state.predictor.profile,mon.ML_PROFILES,"legacy"),
                                 bounded(app.state.predictor.feature_schema,mon.ML_SCHEMAS),
                                 bounded(app.state.predictor.target_mode,mon.ML_TARGETS)).set(1)
    except Exception:logging.getLogger(__name__).exception("Unable to publish ML model metadata")
    mon.build_info.labels("1.0.0",settings.env).set(1);mon.queue_capacity.set(settings.max_queued_runs)
    if settings.env!="production" and settings.metrics_enabled and not settings.metrics_token:logging.getLogger(__name__).warning("EO_METRICS_TOKEN is unset; /metrics is open in development")
    tasks=[asyncio.create_task(loop_lag_task(settings.loop_lag_interval_s)),asyncio.create_task(audit_verify_task(app.state.audit,settings.audit_verify_interval_s)),asyncio.create_task(db_maintenance_task(app,settings.db_maintenance_interval_s,settings.run_lease_s))]
    try:yield
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        engine.dispose()

def create_app()->FastAPI:
    if settings.env=="production":
        try:enforce(settings)
        except InsecureConfigError:
            logging.getLogger(__name__).error("config.invalid env=%s", settings.env)
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
    @app.exception_handler(SQLAlchemyError)
    async def database_error(request:Request,exc:SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed request_id=%s error_type=%s",getattr(request.state,"request_id","unknown"),type(exc).__name__)
        return JSONResponse({"error":"database_unavailable","request_id":getattr(request.state,"request_id","unknown")},status_code=503,headers={"Retry-After":"5"})
    @app.exception_handler(Exception)
    async def internal_error(request:Request,exc:Exception):
        logging.getLogger(__name__).exception("Unhandled request exception",exc_info=exc)
        return JSONResponse({"error":"internal","request_id":getattr(request.state,"request_id","unknown")},status_code=500)
    from app.api.ml_routes import router as ml_router
    app.include_router(router,prefix="/api/v1");app.include_router(ml_router,prefix="/api/v1/ml");app.include_router(ws_router)
    app.include_router(metrics_router);app.include_router(health_router)
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_methods=["GET","POST","DELETE"],allow_headers=["X-API-Key","Content-Type","Authorization","X-Request-ID"],allow_credentials=False,max_age=600)
    app.add_middleware(BodySizeLimitMiddleware,max_bytes=settings.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware,hsts=settings.behind_tls)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app
app=create_app()
