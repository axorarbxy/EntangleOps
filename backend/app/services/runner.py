from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import func, select

from app.config import settings
from app.core.environment import generate_env
from app.core.policies import AdaptivePolicy, StaticCPolicy, StaticOPolicy, make_policy
from app.core.predictor import FidelityPredictor
from app.core.requests_gen import generate_requests
from app.core.simulator import run_simulation
from app.core.topology import get_preset, link_lookup
from app.db.migrate import upgrade_to_head
from app.db.models import ApiKey, Benchmark, Run
from app.db.repos.runs import RunRepo
from app.db.session import make_engine, make_session_factory, resolve_url
from app.db.types import utcnow
from app.schemas import BenchmarkRequest, SimRequest
from monitoring import metrics as mon
from monitoring.drift import DriftMonitor
from monitoring.observer import SimObserver
from app.ml.serving import RowCachePredictor

logger = logging.getLogger(__name__)


def _metric(fn, *args):
    try: fn(*args)
    except Exception: logger.exception("Monitoring update failed")


class RunStore:
    """Run orchestration; durable run state and steps live in the SQL repository."""
    def __init__(self, repo: RunRepo | None = None, session_factory=None, *, temporary: bool = True):
        self._owned_engine = None
        if repo is None:
            if session_factory is None:
                if not temporary:
                    raise ValueError("RunStore requires a persistent RunRepo")
                db_path = Path(tempfile.gettempdir()) / f"entangleops-tests-{time.time_ns()}.db"
                self._owned_engine = make_engine(resolve_url(f"sqlite:///{db_path.as_posix()}"))
                upgrade_to_head(self._owned_engine)
                session_factory = make_session_factory(self._owned_engine)
            self._sf = session_factory
            self.repo = RunRepo(session_factory, settings.max_stored_runs, settings.max_stored_benchmarks)
        else:
            self.repo = repo
            self._sf = session_factory or repo._sf
        self.data = Path(settings.data_dir)  # retained for legacy script compatibility; never used for run storage
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

    def _test_owner(self, owner_key_id: str):
        """Create a placeholder owner only in the isolated temporary test store."""
        if self._owned_engine is None: return
        with self._sf.begin() as s:
            if s.get(ApiKey, owner_key_id) is None:
                s.add(ApiKey(key_id=owner_key_id, name="test owner", role="operator", secret_hash="0" * 64, created_at=utcnow()))

    def create_run(self, config: SimRequest, owner_key_id: str, *, max_active: int | None = None, model_id: int | None = None):
        self._test_owner(owner_key_id)
        return self.repo.create_run(config, owner_key_id,
            max_active=max_active if max_active is not None else settings.max_runs_per_key_active,
            model_id=model_id)

    def get(self, rid): return self.repo.get(rid)
    def list(self): return self.repo.list_all()
    def get_for(self, principal, rid): return self.repo.get_for(principal, rid)
    def list_for(self, principal, limit=100, offset=0): return self.repo.list_for(principal, limit, offset)
    def count_active(self, owner=None): return self.repo.count_active(owner)
    def count_active_all(self): return self.repo.count_active_all()
    def create_benchmark(self, cfg: BenchmarkRequest, owner_key_id: str, model_id: int | None = None, max_active: int | None = None):
        self._test_owner(owner_key_id)
        return self.repo.create_benchmark(cfg, owner_key_id, model_id,
            max_active if max_active is not None else settings.max_runs_per_key_active)
    def get_benchmark_for(self, principal, bid): return self.repo.get_benchmark_for(principal, bid)
    def list_benchmarks_for(self, principal, limit=100): return self.repo.list_benchmarks_for(principal, limit)

    def _sync_counts(self):
        with self._sf() as s:
            queued = (s.scalar(select(func.count()).select_from(Run).where(Run.status == "queued")) or 0) + (s.scalar(select(func.count()).select_from(Benchmark).where(Benchmark.status == "queued")) or 0)
            running = (s.scalar(select(func.count()).select_from(Run).where(Run.status == "running")) or 0) + (s.scalar(select(func.count()).select_from(Benchmark).where(Benchmark.status == "running")) or 0)
            stored = (s.scalar(select(func.count()).select_from(Run)) or 0) + (s.scalar(select(func.count()).select_from(Benchmark)) or 0)
        _metric(mon.runs_active.labels("queued").set, queued); _metric(mon.runs_active.labels("running").set, running)
        _metric(mon.queue_depth.set, queued); _metric(mon.queue_capacity.set, settings.max_queued_runs)
        _metric(mon.runs_stored.set, stored)

    async def execute_run(self, rid: str, predictor: FidelityPredictor | None):
        r = self.repo.get(rid)
        if r is None or not await asyncio.to_thread(self.repo.set_running, rid): return
        self._sync_counts(); config = r["config"]
        if isinstance(config, dict): config = SimRequest.model_validate(config)
        policy = mon.bounded(config.policy, mon.RUN_POLICIES); started = time.monotonic()
        try:
            async with self._semaphore:
                records, summary = await asyncio.to_thread(self._simulate, config, predictor, time.monotonic() + settings.run_timeout_s)
            await asyncio.to_thread(self.repo.finish_ok, rid, [asdict(x) for x in records], summary)
            _metric(mon.runs_total.labels("simulation", policy, "done").inc)
        except TimeoutError:
            await asyncio.to_thread(self.repo.finish_error, rid, "timeout")
            _metric(mon.runs_total.labels("simulation", policy, "timeout").inc)
        except Exception:
            logger.exception("Simulation failed for run %s", rid)
            await asyncio.to_thread(self.repo.finish_error, rid, "internal")
            _metric(mon.runs_total.labels("simulation", policy, "error").inc)
        finally:
            _metric(mon.run_duration.labels("simulation", policy).observe, time.monotonic() - started)
            self._sync_counts()

    async def execute_benchmark(self, bid: str, predictor: FidelityPredictor | None):
        b = self.repo.get_benchmark_for(type("Admin", (), {"role": "admin", "key_id": ""})(), bid)
        if b is None or not await asyncio.to_thread(self.repo.set_benchmark_running, bid): return
        self._sync_counts(); c = b["config"]
        if isinstance(c, dict): c = BenchmarkRequest.model_validate(c)
        started = time.monotonic()
        try:
            nodes, links = get_preset(c.topology_preset); lookup = link_lookup(links)
            env = generate_env(list(lookup), c.duration_hours, c.dt_s, c.seed, c.scenario)
            reqs = generate_requests(nodes, env.n_steps, c.dt_s, c.seed, c.scenario)
            deadline = time.monotonic() + 3 * settings.run_timeout_s; results = {}
            for pol in (StaticCPolicy(), StaticOPolicy(), AdaptivePolicy()):
                async with self._semaphore:
                    run_predictor = self._cached(predictor) if predictor and pol.name == "adaptive" else predictor
                    observer = SimObserver(pol.name, DriftMonitor(run_predictor, env, lookup, settings.drift_ewma_alpha, settings.drift_sample_every_steps, window_rows=settings.ml_psi_window_rows, min_rows=settings.ml_psi_min_rows) if pol.name == "adaptive" and run_predictor else None)
                    records, summary = await asyncio.to_thread(run_simulation, pol, env, reqs, lookup, run_predictor,
                        settings.forecast_horizon_steps, settings.k_paths, settings.safety_margin, deadline, observer)
                    observer.finish(records, summary)
                    results[pol.name] = summary
            adaptive = results["adaptive"]; improvement = {}
            for name in ("static_c", "static_o"):
                base = results[name]
                improvement[name] = {"sla_satisfied_pairs_pct": (adaptive["sla_satisfied_pairs"] - base["sla_satisfied_pairs"]) / max(base["sla_satisfied_pairs"], 1e-9) * 100,
                                     "violation_fraction_delta": adaptive["violation_fraction"] - base["violation_fraction"]}
                _metric(mon.benchmark_improvement.labels(name).set, improvement[name]["sla_satisfied_pairs_pct"])
            await asyncio.to_thread(self.repo.finish_benchmark, bid, results, improvement)
            _metric(mon.runs_total.labels("benchmark", "all", "done").inc)
        except TimeoutError:
            await asyncio.to_thread(self.repo.fail_benchmark, bid, "timeout"); _metric(mon.runs_total.labels("benchmark", "all", "timeout").inc)
        except Exception:
            logger.exception("Benchmark failed for %s", bid)
            await asyncio.to_thread(self.repo.fail_benchmark, bid, "internal"); _metric(mon.runs_total.labels("benchmark", "all", "error").inc)
        finally:
            _metric(mon.run_duration.labels("benchmark", "all").observe, time.monotonic() - started)
            self._sync_counts()

    def _simulate(self, c, predictor, deadline=None):
        nodes, links = get_preset(c.topology_preset); lookup = link_lookup(links)
        env = generate_env(list(lookup), c.duration_hours, c.dt_s, c.seed, c.scenario)
        reqs = generate_requests(nodes, env.n_steps, c.dt_s, c.seed, c.scenario)
        policy = make_policy(c.policy, c.risk_alpha)
        run_predictor = self._cached(predictor) if predictor and c.policy in {"adaptive", "adaptive_risk"} else predictor
        observer = SimObserver(policy.name, DriftMonitor(run_predictor, env, lookup, settings.drift_ewma_alpha, settings.drift_sample_every_steps, window_rows=settings.ml_psi_window_rows, min_rows=settings.ml_psi_min_rows) if c.policy in {"adaptive", "adaptive_risk"} and run_predictor else None)
        records, summary = run_simulation(policy, env, reqs, lookup, run_predictor, settings.forecast_horizon_steps,
                                          settings.k_paths, settings.safety_margin, deadline, observer)
        observer.finish(records, summary)
        return records, summary

    @staticmethod
    def _cached(predictor):
        def event(result, rows, seconds, kind):
            mon.ml_prediction_cache_total.labels(mon.bounded(result, mon.ML_RESULTS)).inc(rows)
            if result == "miss": mon.ml_inference_seconds.labels(mon.bounded(kind, mon.ML_KINDS)).observe(seconds)
        return RowCachePredictor(predictor, settings.ml_prediction_cache_rows, event)
