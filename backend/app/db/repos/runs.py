from __future__ import annotations

import secrets
import threading
from datetime import timedelta

from sqlalchemy import delete, func, insert, select, text, update

from app.db.instrument import db_timer
from app.db.jsonutil import to_jsonable
from app.db.models import Benchmark, BenchmarkResult, Run, RunStep
from app.db.types import utcnow

SCALARS = ("step", "t_s", "active", "arrivals", "admitted", "blocked", "reroutes", "mean_fidelity", "useful_rate_pairs_s", "raw_rate_pairs_s", "sla_violations")
COLUMNS = {name: getattr(RunStep, name) for name in SCALARS}
_owner_locks: dict[str, threading.Lock] = {}
_owner_locks_guard = threading.Lock()


def _lock_for(owner: str) -> threading.Lock:
    with _owner_locks_guard:
        return _owner_locks.setdefault(owner, threading.Lock())


def _row(row: Run) -> dict:
    from app.schemas import SimRequest
    try:
        config = SimRequest.model_validate(row.config)
    except Exception:
        config = row.config
    return {"id": row.id, "owner": row.owner_key_id, "status": row.status,
            "config": config, "summary": row.summary, "error": row.error,
            "created_at": row.created_at.isoformat(), "n_steps": row.n_steps,
            "dt_s": row.dt_s}


class RunRepo:
    def __init__(self, sf, max_stored_runs: int = 200, max_stored_benchmarks: int = 200):
        self._sf = sf
        self.max_stored_runs = max_stored_runs
        self.max_stored_benchmarks = max_stored_benchmarks

    def create_run(self, config, owner_key_id: str, *, max_active: int, model_id: int | None = None) -> str | None:
        with _lock_for(owner_key_id), db_timer("run_write"), self._sf.begin() as s:
            if s.bind.dialect.name == "postgresql":
                s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:owner, 0))"), {"owner": owner_key_id})
            count = s.scalar(select(func.count()).select_from(Run).where(
                Run.owner_key_id == owner_key_id, Run.status.in_(("queued", "running")))) or 0
            count += s.scalar(select(func.count()).select_from(Benchmark).where(
                Benchmark.owner_key_id == owner_key_id, Benchmark.status.in_(("queued", "running")))) or 0
            if count >= max_active:
                return None
            rid = secrets.token_urlsafe(12)
            data = to_jsonable(config.model_dump(mode="json"))
            s.add(Run(id=rid, owner_key_id=owner_key_id, model_id=model_id, status="queued",
                      policy=config.policy, topology_preset=config.topology_preset, seed=config.seed,
                      duration_hours=config.duration_hours, dt_s=config.dt_s,
                      n_steps=int(config.duration_hours * 3600 / config.dt_s), config=data))
            return rid

    def set_running(self, run_id: str) -> bool:
        with db_timer("run_write"), self._sf.begin() as s:
            res = s.execute(update(Run).where(Run.id == run_id, Run.status == "queued").values(
                status="running", started_at=utcnow(), heartbeat_at=utcnow()))
            return res.rowcount == 1

    def heartbeat(self, run_ids: list[str]) -> None:
        if not run_ids:
            return
        with db_timer("run_write"), self._sf.begin() as s:
            s.execute(update(Run).where(Run.id.in_(run_ids), Run.status == "running").values(heartbeat_at=utcnow()))

    def finish_ok(self, run_id: str, records: list[dict], summary: dict) -> bool:
        summary = to_jsonable(summary)
        with db_timer("run_write"), self._sf.begin() as s:
            result = s.execute(update(Run).where(Run.id == run_id, Run.status == "running").values(
                status="done", summary=summary, sla_satisfied_pairs=summary.get("sla_satisfied_pairs"),
                violation_fraction=summary.get("violation_fraction"), finished_at=utcnow(),
                heartbeat_at=None, error=None))
            if result.rowcount != 1:
                return False
            for start in range(0, len(records), 500):
                rows = []
                for record in records[start:start + 500]:
                    item = to_jsonable(record)
                    rows.append({"run_id": run_id, **{key: item[key] for key in SCALARS},
                                 "links": item["links"], "allocations": item["allocations"]})
                if rows:
                    s.execute(insert(RunStep), rows)
        self.evict_if_needed(self.max_stored_runs)
        return True

    def finish_error(self, run_id: str, code: str) -> bool:
        code = code if code in {"timeout", "internal", "interrupted"} else "internal"
        with db_timer("run_write"), self._sf.begin() as s:
            result = s.execute(update(Run).where(Run.id == run_id, Run.status.in_(("running", "queued"))).values(
                status="error", error=code, finished_at=utcnow(), heartbeat_at=None))
            changed = result.rowcount == 1
        if changed:
            self.evict_if_needed(self.max_stored_runs)
        return changed

    def get(self, run_id: str):
        with db_timer("run_read"), self._sf() as s:
            row = s.get(Run, run_id)
            return _row(row) if row else None

    def get_for(self, principal, run_id: str):
        with db_timer("run_read"), self._sf() as s:
            query = select(Run).where(Run.id == run_id)
            if principal.role != "admin":
                query = query.where(Run.owner_key_id == principal.key_id)
            row = s.scalar(query)
            return _row(row) if row else None

    def list_for(self, principal, limit: int = 100, offset: int = 0):
        with db_timer("run_read"), self._sf() as s:
            query = select(Run)
            if principal.role != "admin":
                query = query.where(Run.owner_key_id == principal.key_id)
            return [_row(r) for r in s.scalars(query.order_by(Run.created_at.desc()).limit(limit).offset(offset))]

    def list_all(self):
        with db_timer("run_read"), self._sf() as s:
            return [_row(r) for r in s.scalars(select(Run).order_by(Run.created_at.desc()))]

    def count_active(self, owner_key_id: str | None = None) -> int:
        with db_timer("run_read"), self._sf() as s:
            query = select(func.count()).select_from(Run).where(Run.status.in_(("queued", "running")))
            if owner_key_id:
                query = query.where(Run.owner_key_id == owner_key_id)
            count = int(s.scalar(query) or 0)
            benchmarks = select(func.count()).select_from(Benchmark).where(Benchmark.status.in_(("queued", "running")))
            if owner_key_id:
                benchmarks = benchmarks.where(Benchmark.owner_key_id == owner_key_id)
            return count + int(s.scalar(benchmarks) or 0)

    def read_steps(self, run_id: str, after_step: int = -1, limit: int = 200):
        with db_timer("run_steps"), self._sf() as s:
            rows = s.scalars(select(RunStep).where(RunStep.run_id == run_id, RunStep.step > after_step)
                             .order_by(RunStep.step).limit(min(500, max(1, limit))))
            return [{"step": r.step, "t_s": r.t_s, "active": r.active, "arrivals": r.arrivals,
                     "admitted": r.admitted, "blocked": r.blocked, "reroutes": r.reroutes,
                     "mean_fidelity": r.mean_fidelity, "useful_rate_pairs_s": r.useful_rate_pairs_s,
                     "raw_rate_pairs_s": r.raw_rate_pairs_s, "sla_violations": r.sla_violations,
                     "links": r.links, "allocations": r.allocations} for r in rows]

    def timeseries(self, run_id: str, fields: list[str], stride: int):
        selected = [COLUMNS[name] for name in fields if name in COLUMNS]
        with db_timer("timeseries"), self._sf() as s:
            rows = s.execute(select(*selected).where(RunStep.run_id == run_id,
                             RunStep.step % max(stride, 1) == 0).order_by(RunStep.step)).all()
            return {name: [row[i] for row in rows] for i, name in enumerate(fields) if name in COLUMNS}

    def evict_if_needed(self, max_stored: int) -> int:
        with db_timer("maintenance"), self._sf.begin() as s:
            total = s.scalar(select(func.count()).select_from(Run)) or 0
            excess = max(0, total - max_stored)
            if not excess:
                return 0
            ids = list(s.scalars(select(Run.id).where(Run.status.in_(("done", "error")))
                                 .order_by(Run.created_at).limit(excess)))
            if ids:
                s.execute(delete(Run).where(Run.id.in_(ids)))
            return len(ids)

    def reap_stale(self, lease_s: int) -> int:
        cutoff = utcnow() - timedelta(seconds=lease_s)
        with db_timer("maintenance"), self._sf.begin() as s:
            res = s.execute(update(Run).where(Run.status.in_(("queued", "running")),
                                      func.coalesce(Run.heartbeat_at, Run.created_at) < cutoff)
                            .values(status="error", error="interrupted", finished_at=utcnow()))
            return res.rowcount or 0

    def create_benchmark(self, config, owner_key_id: str, model_id: int | None = None, max_active: int = 3) -> str | None:
        bid = secrets.token_urlsafe(12)
        with _lock_for(owner_key_id), db_timer("run_write"), self._sf.begin() as s:
            if s.bind.dialect.name == "postgresql":
                s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:owner, 0))"), {"owner": owner_key_id})
            count = s.scalar(select(func.count()).select_from(Run).where(Run.owner_key_id == owner_key_id, Run.status.in_(("queued", "running")))) or 0
            count += s.scalar(select(func.count()).select_from(Benchmark).where(Benchmark.owner_key_id == owner_key_id, Benchmark.status.in_(("queued", "running")))) or 0
            if count >= max_active: return None
            s.add(Benchmark(id=bid, owner_key_id=owner_key_id, model_id=model_id, status="queued",
                            config=to_jsonable(config.model_dump(mode="json")), improvement={}))
        return bid

    def set_benchmark_running(self, bid: str) -> bool:
        with db_timer("run_write"), self._sf.begin() as s:
            res = s.execute(update(Benchmark).where(Benchmark.id == bid, Benchmark.status == "queued").values(
                status="running", started_at=utcnow(), heartbeat_at=utcnow()))
            return res.rowcount == 1

    def finish_benchmark(self, bid: str, results: dict, improvement: dict) -> bool:
        with db_timer("run_write"), self._sf.begin() as s:
            res = s.execute(update(Benchmark).where(Benchmark.id == bid, Benchmark.status == "running").values(
                status="done", improvement=to_jsonable(improvement),
                finished_at=utcnow(), heartbeat_at=None, error=None))
            if res.rowcount != 1: return False
            for policy, raw in results.items():
                summary = to_jsonable(raw)
                s.add(BenchmarkResult(benchmark_id=bid, policy=policy, summary=summary,
                    sla_satisfied_pairs=summary["sla_satisfied_pairs"], violation_fraction=summary["violation_fraction"],
                    block_rate=summary["block_rate"], reroutes=summary["reroutes"], mean_fidelity=summary.get("mean_fidelity")))
        self.evict_benchmarks(self.max_stored_benchmarks)
        return True

    def fail_benchmark(self, bid: str, code: str) -> bool:
        code = code if code in {"timeout", "internal", "interrupted"} else "internal"
        with db_timer("run_write"), self._sf.begin() as s:
            res = s.execute(update(Benchmark).where(Benchmark.id == bid, Benchmark.status.in_(("queued", "running"))).values(
                status="error", error=code, finished_at=utcnow(), heartbeat_at=None))
            changed = res.rowcount == 1
        if changed: self.evict_benchmarks(self.max_stored_benchmarks)
        return changed

    def evict_benchmarks(self, max_stored: int) -> int:
        with db_timer("maintenance"), self._sf.begin() as s:
            total=s.scalar(select(func.count()).select_from(Benchmark)) or 0
            excess=max(0,total-max_stored)
            if not excess:return 0
            ids=list(s.scalars(select(Benchmark.id).where(Benchmark.status.in_(("done","error"))).order_by(Benchmark.created_at).limit(excess)))
            if ids:s.execute(delete(Benchmark).where(Benchmark.id.in_(ids)))
            return len(ids)

    def _bench_row(self, row):
        from app.schemas import BenchmarkRequest
        try: config = BenchmarkRequest.model_validate(row.config)
        except Exception: config = row.config
        with self._sf() as s:
            results = {item.policy: item.summary for item in s.scalars(select(BenchmarkResult).where(BenchmarkResult.benchmark_id == row.id))}
        return {"id": row.id, "owner": row.owner_key_id, "status": row.status, "config": config,
                "results": results, "improvement": row.improvement or {}, "error": row.error,
                "created_at": row.created_at.isoformat()}

    def get_benchmark_for(self, principal, bid: str):
        with db_timer("run_read"), self._sf() as s:
            q = select(Benchmark).where(Benchmark.id == bid)
            if principal.role != "admin": q = q.where(Benchmark.owner_key_id == principal.key_id)
            row = s.scalar(q)
            return self._bench_row(row) if row else None

    def list_benchmarks_for(self, principal, limit: int = 100):
        with db_timer("run_read"), self._sf() as s:
            q = select(Benchmark)
            if principal.role != "admin": q = q.where(Benchmark.owner_key_id == principal.key_id)
            return [self._bench_row(x) for x in s.scalars(q.order_by(Benchmark.created_at.desc()).limit(limit))]

    def count_active_all(self) -> int:
        with db_timer("run_read"), self._sf() as s:
            run_count = s.scalar(select(func.count()).select_from(Run).where(Run.status.in_(("queued", "running")))) or 0
            bench_count = s.scalar(select(func.count()).select_from(Benchmark).where(Benchmark.status.in_(("queued", "running")))) or 0
            return int(run_count + bench_count)
