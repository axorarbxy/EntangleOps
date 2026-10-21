from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from app.config import ScenarioConfig

@dataclass(frozen=True)
class EntRequest:
    id:int;arrive_step:int;src:str;dst:str;min_fidelity:float;demand_pairs_s:float;priority:int;duration_steps:int

def generate_requests(nodes:list[str],n_steps:int,dt_s:int,seed:int,sc:ScenarioConfig)->list[EntRequest]:
    if len(nodes)<2:raise ValueError("at least two nodes required")
    rng=np.random.default_rng(seed+1000);out=[]
    for step in range(n_steps):
        for _ in range(rng.poisson(sc.arrival_rate_per_step*dt_s/60)):
            a,b=rng.choice(len(nodes),2,replace=False)
            weights=np.asarray(sc.min_fidelity_weights,dtype=float);weights=weights/weights.sum()
            out.append(EntRequest(len(out),step,nodes[a],nodes[b],float(rng.choice(sc.min_fidelity_choices,p=weights)),float(rng.choice(sc.demand_choices_pairs_s)),int(rng.integers(1,4)),max(1,int(rng.geometric(1/sc.mean_duration_steps)))))
    return out
