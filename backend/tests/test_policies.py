from __future__ import annotations
import pytest
from app.config import ScenarioConfig
from app.core.environment import generate_env
from app.core.policies import AdaptivePolicy,PolicyContext,StaticCPolicy,StaticOPolicy
from app.core.requests_gen import EntRequest
from app.core.state import Allocation,NetworkState
from app.core.topology import build_graph,get_preset,link_lookup

def test_static_and_adaptive_admission_and_capacity():
    nodes,ls=get_preset("tiny");links=link_lookup(ls);env=generate_env(list(links),1,60,3,ScenarioConfig(storm_enabled=False));state=NetworkState(links)
    ctx=PolicyContext(0,links,build_graph(ls),env,state,None,5,4,.01);req=EntRequest(1,0,"A","B",.8,10,1,3)
    assert StaticCPolicy().admit(req,ctx).bands==["C"]
    assert StaticOPolicy().admit(req,ctx).bands==["O"]
    impossible=EntRequest(2,0,"A","C",.99,10,1,3)
    assert AdaptivePolicy().admit(impossible,ctx) is None
    alloc=Allocation(req,["A","B"],["A-B"],["C"],0);state.reserve(alloc)
    with pytest.raises(ValueError):state.reserve(Allocation(EntRequest(3,0,"A","B",.8,10,1,3),["A","B"],["A-B"],["C"],0))
    state.release(req.id);assert state.free_channels("A-B")==links["A-B"].channels
