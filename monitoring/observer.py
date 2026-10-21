from __future__ import annotations

import logging
from collections.abc import Callable

from . import metrics as m

log = logging.getLogger(__name__)


class SimObserver:
    """Read-only simulator observer. All telemetry failures are contained."""

    def __init__(self, policy: str, drift: Callable[[object], None] | None = None) -> None:
        self.policy = m.bounded(policy, m.RUN_POLICIES)
        self.drift = drift

    def __call__(self, record: object) -> None:
        try:
            get = lambda key, default=0: getattr(record, key, default)
            m.sim_steps.labels(self.policy).inc()
            m.sim_requests.labels(self.policy, "admitted").inc(get("admitted"))
            m.sim_requests.labels(self.policy, "blocked").inc(get("blocked"))
            m.sim_reroutes.labels(self.policy).inc(get("reroutes"))
            m.sim_sla_violations.labels(self.policy).inc(get("sla_violations"))
            m.sim_active.labels(self.policy).set(get("active"))
            for lid, data in get("links", {}).items():
                if lid not in {"A-B", "B-C", "C-D", "D-E", "E-F", "A-F", "B-E", "C-F", "A-C"}:
                    continue
                for band in ("C", "O"):
                    m.link_fidelity.labels(self.policy, lid, band).set(data.get(f"fidelity_{band}", 0))
                m.link_utilization.labels(self.policy, lid).set(data.get("utilization", 0))
            if self.drift:
                self.drift(record)
        except Exception:
            log.exception("Simulation monitoring observer failed")

    def finish(self, records: list[object], summary: dict) -> None:
        try:
            useful = float(summary.get("sla_satisfied_pairs", 0))
            raw = float(summary.get("raw_pairs", 0))
            m.sim_useful_pairs.labels(self.policy).inc(useful)
            m.sim_raw_pairs.labels(self.policy).inc(raw)
            m.sim_sla_efficiency.labels(self.policy).set(useful / raw if raw else 0)
        except Exception:
            log.exception("Simulation monitoring summary failed")
