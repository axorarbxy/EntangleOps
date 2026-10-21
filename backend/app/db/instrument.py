from __future__ import annotations

import logging
from contextlib import contextmanager
from time import perf_counter

from monitoring import metrics as M
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)
DB_OPS = frozenset({"key_read", "key_write", "audit_append", "audit_read", "run_read", "run_write", "run_steps", "timeseries", "ticket_redeem", "maintenance", "health"})


@contextmanager
def db_timer(op: str):
    if op not in DB_OPS:
        raise ValueError("unknown database operation")
    started = perf_counter()
    try:
        yield
    except Exception as exc:
        if not isinstance(exc, IntegrityError) and hasattr(M, "db_errors"):
            M.db_errors.labels(op).inc()
        raise
    finally:
        if hasattr(M, "db_duration"):
            M.db_duration.labels(op).observe(perf_counter() - started)


def instrument_pool(engine, capacity: int) -> None:
    if not hasattr(M, "db_pool_capacity"):
        return
    M.db_pool_capacity.set(capacity)
    from sqlalchemy import event

    @event.listens_for(engine, "checkout")
    def _checkout(*_):
        M.db_pool_checked_out.inc()

    @event.listens_for(engine, "checkin")
    def _checkin(*_):
        M.db_pool_checked_out.dec()
