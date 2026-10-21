from __future__ import annotations
import math
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Path,Query,Request
from pydantic import BaseModel,ConfigDict,Field
from app.config import settings
from app.schemas import BenchmarkRequest,PredictRequest,RunStatus,RunSummary,SimRequest,WsTicketRequest
from app.core.topology import get_preset
from app.core.physics import LinkParams,werner_to_fidelity
from app.core.sequence_adapter import cross_check_link
from security.auth import Principal,get_principal,require_role
from monitoring import metrics as mon

router=APIRouter();ID=r"^[A-Za-z0-9_-]{8,32}$"
class KeyCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=64);role:str=Field(pattern=r"^(viewer|operator|admin)$");ttl_days:float|None=Field(default=None,gt=0,le=3650)
@router.get("/health")
def health():return {"status":"ok"}
@router.get("/topology")
def topology(preset:str="metro",principal:Principal=Depends(get_principal)):
    try:nodes,links=get_preset(preset)
    except ValueError as e:raise HTTPException(422,"invalid topology preset") from e
    return {"nodes":nodes,"links":[{k:getattr(l,k) for k in ("link_id","u","v","length_km","aerial_fraction","modes","channels")} for l in links]}
def _budget(c:SimRequest|BenchmarkRequest)->None:
    steps=c.duration_hours*3600/c.dt_s
    if steps>settings.max_steps_per_run or c.scenario.arrival_rate_per_step*steps*c.dt_s/60>settings.max_expected_requests_per_run:raise HTTPException(422,"compute budget exceeded")
def _active_count(store,owner:str)->int:return sum(1 for r in list(store.runs.values())+list(store.benchmarks.values()) if r["owner"]==owner and r["status"] in ("queued","running"))
def _queue_check(store)->None:
    pending=sum(1 for r in list(store.runs.values())+list(store.benchmarks.values()) if r["status"] in ("queued","running"))
    if pending>=settings.max_concurrent_runs+settings.max_queued_runs:
        try:mon.run_denied.labels("queue_full").inc()
        except Exception:pass
        raise HTTPException(503,"run queue is full",headers={"Retry-After":"30"})
def _extra_cost(request:Request,principal:Principal,cost:float)->None:
    if not request.app.state.limiter_key.consume(principal.key_id,cost):raise HTTPException(429,"Rate limit exceeded",headers={"Retry-After":"30"})
@router.post("/simulations",status_code=202,response_model=RunStatus)
async def start_sim(c:SimRequest,bg:BackgroundTasks,request:Request,p:Principal=Depends(require_role("operator"))):
    _budget(c);store=request.app.state.store;_queue_check(store)
    if _active_count(store,p.key_id)>=settings.max_runs_per_key_active:
        try:mon.run_denied.labels("quota").inc()
        except Exception:pass
        raise HTTPException(429,"active run quota exceeded")
    _extra_cost(request,p,4);rid=store.create_run(c,p.key_id);request.app.state.audit.event("run.create",key_id=p.key_id,ip=request.app.state.client_ip(request),path=request.url.path,request_id=request.state.request_id)
    bg.add_task(store.execute_run,rid,request.app.state.predictor);return store.get(rid)
@router.get("/simulations",response_model=list[RunStatus])
def list_sim(request:Request,p:Principal=Depends(get_principal)):return request.app.state.store.list_for(p)
@router.get("/simulations/{rid}",response_model=RunSummary)
def get_sim(request:Request,rid:str=Path(pattern=ID),p:Principal=Depends(get_principal)):
    r=request.app.state.store.get_for(p,rid)
    if not r:request.app.state.audit.event("run.denied",key_id=p.key_id,path=request.url.path,request_id=request.state.request_id,reason="not_owner");raise HTTPException(404,"not found")
    return r
@router.get("/simulations/{rid}/timeseries")
def timeseries(request:Request,rid:str=Path(pattern=ID),fields:str|None=None,stride:int=Query(default=1,ge=1,le=1000),p:Principal=Depends(get_principal)):
    r=request.app.state.store.get_for(p,rid)
    if not r:request.app.state.audit.event("run.denied",key_id=p.key_id,path=request.url.path,request_id=request.state.request_id,reason="not_owner");raise HTTPException(404,"not found")
    if r["status"]!="done":raise HTTPException(409,"results not ready")
    rows=r["records"][::stride];keys=fields.split(",") if fields else ["step","t_s","active","arrivals","admitted","blocked","reroutes","mean_fidelity","useful_rate_pairs_s","raw_rate_pairs_s","sla_violations"]
    if any(k not in (rows[0] if rows else {}) for k in keys):raise HTTPException(422,"invalid fields")
    return {k:[row[k] for row in rows] for k in keys}
@router.post("/benchmarks",status_code=202)
async def start_bench(c:BenchmarkRequest,bg:BackgroundTasks,request:Request,p:Principal=Depends(require_role("operator"))):
    _budget(c);store=request.app.state.store;_queue_check(store)
    if _active_count(store,p.key_id)>=settings.max_runs_per_key_active:
        try:mon.run_denied.labels("quota").inc()
        except Exception:pass
        raise HTTPException(429,"active run quota exceeded")
    _extra_cost(request,p,9);bid=store.create_benchmark(c,p.key_id);request.app.state.audit.event("benchmark.create",key_id=p.key_id,ip=request.app.state.client_ip(request),path=request.url.path,request_id=request.state.request_id)
    bg.add_task(store.execute_benchmark,bid,request.app.state.predictor);return {"id":bid,"status":"queued"}
@router.get("/benchmarks/{bid}")
def get_bench(request:Request,bid:str=Path(pattern=ID),p:Principal=Depends(get_principal)):
    b=request.app.state.store.benchmarks.get(bid)
    if not b or (p.role!="admin" and b["owner"]!=p.key_id):request.app.state.audit.event("run.denied",key_id=p.key_id,path=request.url.path);raise HTTPException(404,"not found")
    return b
@router.post("/predict")
def predict(c:PredictRequest,request:Request,p:Principal=Depends(get_principal)):
    h=c.hour%24;features=[c.length_km,c.aerial_fraction,float(c.band=="O"),c.traffic_now,c.traffic_trend,c.temp_now,c.dtemp_dt_now,c.wind_now,c.wind_trend,math.sin(2*math.pi*h/24),math.cos(2*math.pi*h/24)]
    w=float(request.app.state.predictor.predict_w([features])[0]);return {"werner":w,"fidelity":werner_to_fidelity(w)}
@router.get("/crosscheck")
def crosscheck(length_km:float=Query(default=30,ge=.1,le=200),band:str=Query(default="O",pattern="^(C|O)$"),p:Principal=Depends(require_role("admin"))):return cross_check_link(length_km,band)
@router.post("/ws-ticket")
def ws_ticket(c:WsTicketRequest,request:Request,p:Principal=Depends(get_principal)):
    if request.app.state.store.get_for(p,c.run_id) is None:raise HTTPException(404,"not found")
    return {"ticket":request.app.state.ticket_service.issue(p.key_id,c.run_id),"expires_in":settings.ws_ticket_ttl_s}
@router.post("/admin/keys")
def create_key(c:KeyCreate,request:Request,p:Principal=Depends(require_role("admin"))):
    secret,rec=request.app.state.keystore.create(c.name,c.role,c.ttl_days);request.app.state.audit.event("key.create",key_id=rec.key_id,role=rec.role);return {"key":secret,"key_id":rec.key_id,"warning":"Store this key now; it will not be shown again."}
@router.get("/admin/keys")
def list_keys(request:Request,p:Principal=Depends(require_role("admin"))):return [{"key_id":x.key_id,"name":x.name,"role":x.role,"created_at":x.created_at,"expires_at":x.expires_at,"revoked":x.revoked} for x in request.app.state.keystore.list()]
@router.delete("/admin/keys/{key_id}")
def revoke_key(request:Request,key_id:str=Path(pattern=r"^[a-f0-9]{12}$"),p:Principal=Depends(require_role("admin"))):
    if not request.app.state.keystore.revoke(key_id):raise HTTPException(404,"not found")
    request.app.state.audit.event("key.revoke",key_id=key_id);return {"status":"revoked"}
@router.get("/admin/audit")
def audit(request:Request,limit:int=Query(default=100,ge=1,le=1000),p:Principal=Depends(require_role("admin"))):return request.app.state.audit.entries(limit)
