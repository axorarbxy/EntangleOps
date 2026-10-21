from __future__ import annotations

import asyncio, json, logging, secrets, time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from app.config import settings
from app.core.environment import generate_env
from app.core.policies import AdaptivePolicy, StaticCPolicy, StaticOPolicy
from app.core.predictor import FidelityPredictor
from app.core.requests_gen import generate_requests
from app.core.simulator import run_simulation
from app.core.topology import get_preset, link_lookup
from app.schemas import BenchmarkRequest, SimRequest
from monitoring import metrics as mon
from monitoring.observer import SimObserver
from monitoring.drift import DriftMonitor

logger = logging.getLogger(__name__)

def _metric(fn, *args):
    try: fn(*args)
    except Exception: logger.exception("Monitoring update failed")

class RunStore:
    def __init__(self): self.runs={}; self.benchmarks={}; self.data=Path(settings.data_dir); self._semaphore=asyncio.Semaphore(settings.max_concurrent_runs)
    def create_run(self,config:SimRequest,owner_key_id:str)->str:
        rid=secrets.token_urlsafe(12);self.runs[rid]={"id":rid,"owner":owner_key_id,"status":"queued","config":config,"summary":None,"records":[],"error":None,"created_at":datetime.now(timezone.utc).isoformat()};self._evict();self._queued(1);return rid
    def get(self,rid:str):return self.runs.get(rid)
    def list(self):return list(self.runs.values())
    def get_for(self,principal,rid:str):
        r=self.runs.get(rid);return r if r and (principal.role=="admin" or r["owner"]==principal.key_id) else None
    def list_for(self,principal):return list(self.runs.values()) if principal.role=="admin" else [r for r in self.runs.values() if r["owner"]==principal.key_id]
    def create_benchmark(self,cfg:BenchmarkRequest,owner_key_id:str)->str:
        bid=secrets.token_urlsafe(12);self.benchmarks[bid]={"id":bid,"owner":owner_key_id,"status":"queued","config":cfg,"results":{},"improvement":{},"error":None};self._evict();self._queued(1);return bid
    def _queued(self,delta):
        _metric(mon.runs_active.labels("queued").inc if delta>0 else mon.runs_active.labels("queued").dec);_metric(mon.queue_depth.inc if delta>0 else mon.queue_depth.dec);_metric(mon.queue_capacity.set,settings.max_queued_runs);_metric(mon.runs_stored.set,len(self.runs)+len(self.benchmarks))
    async def execute_run(self,rid:str,predictor:FidelityPredictor|None):
        r=self.runs[rid];kind="simulation";policy=mon.bounded(r["config"].policy,mon.RUN_POLICIES);started=time.monotonic();running=False
        try:
            async with self._semaphore:
                self._queued(-1);_metric(mon.runs_active.labels("running").inc);running=True;r["status"]="running"
                rec,s=await asyncio.to_thread(self._simulate,r["config"],predictor,time.monotonic()+settings.run_timeout_s)
            r["records"]=[asdict(x) for x in rec];r["summary"]=s;r["status"]="done";self._persist("runs",rid,r);self._finished(kind,policy,"done",started)
        except TimeoutError:r["error"]="timeout";r["status"]="error";self._persist("runs",rid,r);self._finished(kind,policy,"timeout",started)
        except Exception:r["error"]="simulation failed";r["status"]="error";self._persist("runs",rid,r);self._finished(kind,policy,"error",started)
        finally:
            if running:_metric(mon.runs_active.labels("running").dec)
            elif r["status"]=="queued":self._queued(-1)
            _metric(mon.runs_stored.set,len(self.runs)+len(self.benchmarks))
    def _finished(self,kind,policy,status,started):
        _metric(mon.runs_total.labels(kind,policy,status).inc);_metric(mon.run_duration.labels(kind,policy).observe,time.monotonic()-started)
    async def execute_benchmark(self,bid:str,predictor:FidelityPredictor|None):
        b=self.benchmarks[bid];started=time.monotonic();running=False
        try:
            c=b["config"];nodes,ls=get_preset(c.topology_preset);lookup=link_lookup(ls);env=generate_env(list(lookup),c.duration_hours,c.dt_s,c.seed,c.scenario);reqs=generate_requests(nodes,env.n_steps,c.dt_s,c.seed,c.scenario);deadline=time.monotonic()+3*settings.run_timeout_s
            for pol in (StaticCPolicy(),StaticOPolicy(),AdaptivePolicy()):
                async with self._semaphore:
                    if not running:self._queued(-1);_metric(mon.runs_active.labels("running").inc);running=True;b["status"]="running"
                    observer=SimObserver(pol.name,DriftMonitor(predictor,env,lookup,settings.drift_ewma_alpha,settings.drift_sample_every_steps) if pol.name=="adaptive" and predictor else None)
                    records,s=await asyncio.to_thread(run_simulation,pol,env,reqs,lookup,predictor,settings.forecast_horizon_steps,settings.k_paths,settings.safety_margin,deadline,observer);observer.finish(records,s);b["results"][pol.name]=s
            a=b["results"]["adaptive"]
            for name in ("static_c","static_o"):
                base=b["results"][name];b["improvement"][name]={"sla_satisfied_pairs_pct":(a["sla_satisfied_pairs"]-base["sla_satisfied_pairs"])/max(base["sla_satisfied_pairs"],1e-9)*100,"violation_fraction_delta":a["violation_fraction"]-base["violation_fraction"]};_metric(mon.benchmark_improvement.labels(name).set,b["improvement"][name]["sla_satisfied_pairs_pct"])
            b["status"]="done";self._persist("benchmarks",bid,b);self._finished("benchmark","all","done",started)
        except TimeoutError:b["error"]="timeout";b["status"]="error";self._persist("benchmarks",bid,b);self._finished("benchmark","all","timeout",started)
        except Exception:b["error"]="benchmark failed";b["status"]="error";self._persist("benchmarks",bid,b);self._finished("benchmark","all","error",started)
        finally:
            if running:_metric(mon.runs_active.labels("running").dec)
            elif b["status"]=="queued":self._queued(-1)
            _metric(mon.runs_stored.set,len(self.runs)+len(self.benchmarks))
    def _simulate(self,c,predictor,deadline=None):
        nodes,ls=get_preset(c.topology_preset);lookup=link_lookup(ls);env=generate_env(list(lookup),c.duration_hours,c.dt_s,c.seed,c.scenario);reqs=generate_requests(nodes,env.n_steps,c.dt_s,c.seed,c.scenario);policy={"static_c":StaticCPolicy(),"static_o":StaticOPolicy(),"adaptive":AdaptivePolicy()}[c.policy]
        observer=SimObserver(policy.name,DriftMonitor(predictor,env,lookup,settings.drift_ewma_alpha,settings.drift_sample_every_steps) if policy.name=="adaptive" and predictor else None)
        records,summary=run_simulation(policy,env,reqs,lookup,predictor,settings.forecast_horizon_steps,settings.k_paths,settings.safety_margin,deadline,observer);observer.finish(records,summary);return records,summary
    def _persist(self,kind,rid,obj):
        self.data.joinpath(kind).mkdir(parents=True,exist_ok=True)
        def clean(x):
            if hasattr(x,"model_dump"):return x.model_dump(mode="json")
            raise TypeError()
        base=(self.data/kind).resolve();path=(base/f"{rid}.json").resolve()
        if not path.is_relative_to(base):raise ValueError("unsafe persistence path")
        path.write_text(json.dumps(obj,default=clean,allow_nan=False));path.chmod(0o600)
    def _evict(self):
        combined=[("runs",k,v) for k,v in self.runs.items()]+[("benchmarks",k,v) for k,v in self.benchmarks.items()]
        while len(combined)>settings.max_stored_runs:
            done=[x for x in combined if x[2]["status"] in ("done","error")]
            if not done:break
            kind,key,_=done[0];(self.runs if kind=="runs" else self.benchmarks).pop(key,None);p=(self.data/kind/f"{key}.json").resolve();base=(self.data/kind).resolve()
            if p.is_relative_to(base):p.unlink(missing_ok=True)
            combined=[x for x in combined if not (x[0]==kind and x[1]==key)]
