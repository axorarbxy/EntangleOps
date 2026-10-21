from __future__ import annotations
from app.core.requests_gen import EntRequest

def compute_summary(records:list,requests:list[EntRequest],dt_s:int)->dict:
    admitted=sum(r.admitted for r in records);blocked=sum(r.blocked for r in records);active=sum(r.active for r in records)
    useful=sum(r.useful_rate_pairs_s for r in records)*dt_s;raw=sum(r.raw_rate_pairs_s for r in records)*dt_s
    weighted=0.0
    for r in records:
        for a in r.allocations:weighted+=a["useful_rate"]*a["priority"]*dt_s
    return {"total_requests":len(requests),"admitted":admitted,"blocked":blocked,"block_rate":blocked/max(len(requests),1),"sla_satisfied_pairs":useful,"raw_pairs":raw,"sla_efficiency":useful/raw if raw else 0,"violation_fraction":sum(r.sla_violations for r in records)/active if active else 0,"mean_fidelity":sum(r.mean_fidelity for r in records if r.mean_fidelity is not None)/max(sum(r.mean_fidelity is not None for r in records),1),"reroutes":sum(r.reroutes for r in records),"priority_weighted_useful_pairs":weighted,"peak_active":max((r.active for r in records),default=0)}
