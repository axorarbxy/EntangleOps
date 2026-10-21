from __future__ import annotations
from app.config import Settings

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
    return problems

def enforce(s: Settings)->None:
    problems=validate_settings(s)
    if problems:raise InsecureConfigError("; ".join(problems))
