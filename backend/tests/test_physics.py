from __future__ import annotations
from app.core.physics import Conditions,LinkParams,link_fidelity,link_rate,path_metrics

def test_physics_monotonic_and_bands():
    l=LinkParams("A-B","A","B",40,1);quiet=Conditions(0,20,0,0);busy=Conditions(.9,20,0,0)
    assert link_fidelity(l,"O",busy)>link_fidelity(l,"C",busy)
    assert link_rate(l,"C")>link_rate(l,"O")
    assert link_fidelity(l,"C",quiet)>link_fidelity(l,"C",busy)
    assert .25<=link_fidelity(l,"C",busy)<=1
    buried=LinkParams("A-B","A","B",20,0)
    assert link_fidelity(buried,"C",Conditions(0,0,0,0))==link_fidelity(buried,"C",Conditions(0,40,100,20))

def test_path_swapping_degrades():
    l=LinkParams("A-B","A","B",20,0);c=Conditions(0,20,0,0)
    f,r=path_metrics([(l,"C",c),(l,"C",c)])
    assert f<=link_fidelity(l,"C",c) and r<=link_rate(l,"C")*.5+1e-9
