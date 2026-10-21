from __future__ import annotations
from app.config import ScenarioConfig
from app.core.environment import generate_env
from app.core.policies import StaticCPolicy
from app.core.requests_gen import generate_requests
from app.core.simulator import run_simulation
from app.core.topology import get_preset,link_lookup

def test_run_is_deterministic():
    nodes,ls=get_preset("tiny");lookup=link_lookup(ls);sc=ScenarioConfig(arrival_rate_per_step=.1)
    env=generate_env(list(lookup),6,60,4,sc);req=generate_requests(nodes,env.n_steps,60,4,sc)
    a,sa=run_simulation(StaticCPolicy(),env,req,lookup,None,5,4,.01);b,sb=run_simulation(StaticCPolicy(),env,req,lookup,None,5,4,.01)
    assert sa==sb and [x.admitted for x in a]==[x.admitted for x in b]
    assert sum(x.admitted+x.blocked for x in a)==len(req)
