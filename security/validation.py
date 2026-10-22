from __future__ import annotations
import os
from pathlib import Path
from app.config import Settings
from sqlalchemy.engine import make_url
from app.ml.constants import ALPHAS

class InsecureConfigError(RuntimeError):
    """Raised when production security settings are unsafe."""

def validate_settings(s: Settings) -> list[str]:
    problems=[]
    if s.env!="production":return problems
    if len(s.api_key_pepper)<32:problems.append("EO_API_KEY_PEPPER must be set and at least 32 characters")
    if len(s.model_signing_key)<32:problems.append("EO_MODEL_SIGNING_KEY must be set and at least 32 characters")
    if s.api_key_pepper and s.api_key_pepper==s.model_signing_key:problems.append("pepper and signing key must be different secrets")
    if not s.cors_origins or "*" in s.cors_origins:problems.append("EO_CORS_ORIGINS must be an explicit non-wildcard allowlist in production")
    if s.max_body_bytes>1_048_576:problems.append("EO_MAX_BODY_BYTES must be <= 1 MiB in production")
    if s.metrics_enabled and len(s.metrics_token)<32:problems.append("EO_METRICS_TOKEN must be set and at least 32 characters when metrics are enabled")
    if s.metrics_token and s.metrics_token in (s.api_key_pepper,s.model_signing_key):problems.append("metrics token must be a distinct secret")
    problems.extend(validate_db_settings(s))
    return problems

def validate_db_settings(s: Settings) -> list[str]:
    problems=[]
    try:
        url=make_url(s.database_url.get_secret_value())
    except Exception:
        return ["EO_DATABASE_URL is invalid"]
    if url.get_backend_name()=="sqlite":
        if not s.allow_sqlite_in_production:problems.append("SQLite is not allowed in production (single-node pilots may set EO_ALLOW_SQLITE_IN_PRODUCTION=true)")
    elif url.drivername!="postgresql+psycopg":
        problems.append("EO_DATABASE_URL must use the postgresql+psycopg driver")
    else:
        if (url.username or "") in ("","postgres","root","eo_admin","eo_owner"):problems.append("the backend must connect as the least-privilege role (eo_app), not an owner or superuser")
        if not s.database_password_file and len(url.password or "")<24:problems.append("database password must be >= 24 chars (or use EO_DATABASE_PASSWORD_FILE)")
        if (url.host or "") not in ("db","localhost","127.0.0.1","") and url.query.get("sslmode") not in ("verify-full","verify-ca"):problems.append("remote PostgreSQL requires sslmode=verify-full (or verify-ca)")
    if s.migration_database_url.get_secret_value():problems.append("migration credentials must not be present in the backend runtime environment")
    if s.db_echo:problems.append("EO_DB_ECHO must be false in production")
    if s.ml_risk_alpha not in ALPHAS:problems.append("EO_ML_RISK_ALPHA must be one of 0.05, 0.1, 0.2")
    if not 1000<=s.ml_prediction_cache_rows<=500000:problems.append("EO_ML_PREDICTION_CACHE_ROWS must be between 1000 and 500000")
    models=Path(s.ml_models_dir)
    if not models.is_dir() or (os.name!="nt" and models.stat().st_mode & 0o002):
        problems.append("EO_ML_MODELS_DIR must exist and must not be world-writable")
    return problems

def enforce(s: Settings)->None:
    problems=validate_settings(s)
    if problems:raise InsecureConfigError("; ".join(problems))
