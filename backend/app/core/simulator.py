from __future__ import annotations
from dataclasses import dataclass
import logging
from collections.abc import Callable
import time
from app.core.environment import EnvTraces
from app.core.metrics import compute_summary
from app.core.physics import BANDS,LinkParams,link_fidelity,path_metrics
from app.core.policies import Policy,PolicyContext
from app.core.predictor import FidelityPredictor
from app.core.requests_gen import EntRequest
from app.core.state import NetworkState
from app.core.topology import build_graph

@dataclass
class StepRecord:
    step:int;t_s:int;active:int;arrivals:int;admitted:int;blocked:int;reroutes:int;mean_fidelity:float|None;useful_rate_pairs_s:float;raw_rate_pairs_s:float;sla_violations:int;links:dict;allocations:list

def run_simulation(policy:Policy,env:EnvTraces,requests:list[EntRequest],links:dict[str,LinkParams],predictor:FidelityPredictor|None,horizon_steps:int,k_paths:int,safety_margin:float,deadline:float|None=None,observer:Callable[[StepRecord],None]|None=None)->tuple[list[StepRecord],dict]:
    state=NetworkState(links);graph=build_graph(list(links.values()));by_step={}
    for req in requests:by_step.setdefault(req.arrive_step,[]).append(req)
    records=[]
    for t in range(env.n_steps):
        if deadline is not None and t%50==0 and time.monotonic()>deadline:raise TimeoutError("run exceeded time budget")
        admitted=blocked=reroutes=0
        for rid,a in list(state.active().items()):
            if a.start_step+a.request.duration_steps<=t:state.release(rid)
        ctx=PolicyContext(t,links,graph,env,state,predictor,horizon_steps,k_paths,safety_margin)
        for rid,a in list(state.active().items()):
            new=policy.maintain(a,ctx)
            if new:
                state.release(rid);state.reserve(new);reroutes+=1
        arrivals=by_step.get(t,[])
        for req in arrivals:
            alloc=policy.admit(req,ctx)
            if alloc is None:blocked+=1
            else:state.reserve(alloc);admitted+=1
        alloc_snaps=[];fids=[];useful=raw=0.;viol=0
        for a in state.active().values():
            f,rate=path_metrics([(links[lid],b,env.conditions(lid,t)) for lid,b in zip(a.link_ids,a.bands)])
            achieved=min(a.request.demand_pairs_s,rate);ok=f>=a.request.min_fidelity;raw+=achieved
            if ok:useful+=achieved
            else:viol+=1
            fids.append(f);alloc_snaps.append({"request_id":a.request.id,"path":a.path,"bands":a.bands,"fidelity":f,"rate":rate,"useful_rate":achieved if ok else 0.,"min_fidelity":a.request.min_fidelity,"sla_ok":ok,"priority":a.request.priority})
        ls={}
        util=state.utilization()
        for lid,l in links.items():
            c=env.conditions(lid,t);ls[lid]={"traffic":c.traffic_load,"temp_c":c.temp_c,"wind":c.wind_ms,"dtemp_dt":c.dtemp_dt_c_per_h,"utilization":util[lid],"best_band_true":max(BANDS,key=lambda b:link_fidelity(l,b,c)),"fidelity_C":link_fidelity(l,"C",c),"fidelity_O":link_fidelity(l,"O",c)}
        record=StepRecord(t,t*env.dt_s,len(state.active()),len(arrivals),admitted,blocked,reroutes,sum(fids)/len(fids) if fids else None,useful,raw,viol,ls,alloc_snaps);records.append(record)
        if observer:
            try:observer(record)
            except Exception:logging.getLogger(__name__).exception("Simulation observer failed")
    summary=compute_summary(records,requests,env.dt_s);summary["policy"]=policy.name;return records,summary
