from __future__ import annotations

import logging

from . import metrics as m

log = logging.getLogger(__name__)


def on_audit_event(kind: str, fields: dict) -> None:
    try:
        m.audit_events.labels(m.bounded(kind, m.AUDIT_KINDS)).inc()
        if kind == "auth.fail":
            m.auth_failures.labels(m.bounded(fields.get("reason"), m.AUTH_REASONS)).inc()
        if kind == "ratelimit.key": m.rate_limited.labels("key").inc()
        if kind == "ratelimit.ip": m.rate_limited.labels("ip").inc()
        if kind == "auth.throttled": m.rate_limited.labels("auth_fail").inc()
        if kind == "run.denied": m.run_denied.labels(m.bounded(fields.get("reason"), m.DENY_REASONS)).inc()
        if kind == "ws.deny": m.ws_denied.labels(m.bounded(fields.get("reason"), m.WS_REASONS)).inc()
        if kind == "model.verify_fail": m.model_verify_failures.inc()
    except Exception:
        log.exception("Audit monitoring listener failed")
