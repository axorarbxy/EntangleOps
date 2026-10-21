from __future__ import annotations
from dataclasses import dataclass
import networkx as nx
import numpy as np
from app.core.environment import EnvTraces
from app.core.physics import BANDS,LinkParams,SWAP_P,SWAP_W,link_rate,werner_to_fidelity
from app.core.predictor import FidelityPredictor,build_features
from app.core.requests_gen import EntRequest
from app.core.state import Allocation,NetworkState
from app.core.topology import candidate_paths

@dataclass
class PolicyContext:
    step:int;links:dict[str,LinkParams];graph:nx.Graph;env:EnvTraces;state:NetworkState;predictor:FidelityPredictor|None;horizon_steps:int;k_paths:int;safety_margin:float
class Policy:
    name="base"
    def admit(self,req:EntRequest,ctx:PolicyContext)->Allocation|None:raise NotImplementedError
    def maintain(self,alloc:Allocation,ctx:PolicyContext)->Allocation|None:return None

class StaticPolicy(Policy):
    band="C"
    def __init__(self,name:str|None=None):self.name=name or ("static_c" if self.band=="C" else "static_o")
    def admit(self,req:EntRequest,ctx:PolicyContext)->Allocation|None:
        paths=candidate_paths(ctx.graph,req.src,req.dst,1)
        if not paths:return None
        path=paths[0];ids=[ctx.graph[path[i]][path[i+1]]["link_id"] for i in range(len(path)-1)]
        return Allocation(req,path,ids,[self.band]*len(ids),ctx.step) if ctx.state.can_reserve(ids) else None
class StaticCPolicy(StaticPolicy):band="C"
class StaticOPolicy(StaticPolicy):band="O"

class AdaptivePolicy(Policy):
    name="adaptive"
    def _search(self,req:EntRequest,ctx:PolicyContext)->Allocation|None:
        paths=candidate_paths(ctx.graph,req.src,req.dst,ctx.k_paths);rows=[];meta=[]
        for pi,path in enumerate(paths):
            ids=[ctx.graph[path[i]][path[i+1]]["link_id"] for i in range(len(path)-1)]
            if not ctx.state.can_reserve(ids):continue
            for lid in ids:
                for band in BANDS:rows.append(build_features(ctx.env,ctx.links[lid],band,ctx.step));meta.append((pi,lid,band))
        if not rows:return None
        predictor=ctx.predictor
        if predictor is None: vals=np.asarray([.97 for _ in rows])
        else: vals=predictor.predict_w(np.asarray(rows))
        by={}
        for (pi,lid,band),w in zip(meta,vals):by.setdefault((pi,lid),{})[band]=float(w)
        options=[]
        for pi,path in enumerate(paths):
            ids=[ctx.graph[path[i]][path[i+1]]["link_id"] for i in range(len(path)-1)]
            if not all((pi,lid) in by for lid in ids):continue
            bands=[];ws=[];rates=[]
            for lid in ids:
                band=max(BANDS,key=lambda b:by[(pi,lid)][b]);bands.append(band);ws.append(by[(pi,lid)][band]);rates.append(link_rate(ctx.links[lid],band))
            fidelity=werner_to_fidelity(float(np.prod(ws))*SWAP_W**(len(ids)-1));rate=min(rates)*SWAP_P**(len(ids)-1)
            if fidelity>=req.min_fidelity+ctx.safety_margin:options.append((min(req.demand_pairs_s,rate),fidelity,-len(ids),path,ids,bands))
        if not options:return None
        _,_,_,path,ids,bands=max(options,key=lambda o:o[:3]);return Allocation(req,path,ids,bands,ctx.step)
    def admit(self,req:EntRequest,ctx:PolicyContext)->Allocation|None:return self._search(req,ctx)
    def maintain(self,alloc:Allocation,ctx:PolicyContext)->Allocation|None:
        ws=[];rows=[]
        for lid,b in zip(alloc.link_ids,alloc.bands):rows.append(build_features(ctx.env,ctx.links[lid],b,ctx.step))
        if ctx.predictor is None:return None
        f=werner_to_fidelity(float(np.prod(ctx.predictor.predict_w(np.asarray(rows))))*SWAP_W**(len(rows)-1))
        if f>=alloc.request.min_fidelity:return None
        ctx.state.release(alloc.request.id);alt=self._search(alloc.request,ctx)
        if alt is None:ctx.state.reserve(alloc);return None
        alt.reroutes=alloc.reroutes+1;return alt
