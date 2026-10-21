from __future__ import annotations
import asyncio,time
from fastapi import APIRouter,WebSocket,WebSocketDisconnect,Path,Query
from app.config import settings
from security.auth import Principal
from monitoring.metrics import ws_connections

router=APIRouter()
@router.websocket("/ws/simulations/{rid}")
async def replay(ws:WebSocket,rid:str=Path(pattern=r"^[A-Za-z0-9_-]{8,32}$"),ticket:str=Query(default=""),speed:int=50):
    app=ws.app;origins=settings.ws_allowed_origins or settings.cors_origins;origin=ws.headers.get("origin")
    if (origin is None and settings.env!="development") or (origin is not None and "*" not in origins and origin not in origins):
        app.state.audit.event("ws.deny",reason="origin",path=f"/ws/simulations/{rid}");await ws.close(code=4403);return
    key_id=app.state.ticket_service.redeem(ticket,rid)
    if key_id is None:
        app.state.audit.event("ws.deny",reason="ticket",path=f"/ws/simulations/{rid}");await ws.close(code=4401);return
    rec=app.state.keystore.get(key_id);principal=Principal(rec.key_id,rec.name,rec.role) if rec else None
    run=app.state.store.get_for(principal,rid) if principal else None
    if run is None:
        app.state.audit.event("ws.deny",key_id=key_id,reason="revoked",path=f"/ws/simulations/{rid}");await ws.close(code=4401);return
    count=app.state.ws_counts.get(key_id,0)
    if count>=settings.max_ws_per_key:
        app.state.audit.event("ws.deny",key_id=key_id,reason="limit",path=f"/ws/simulations/{rid}");await ws.close(code=4429);return
    app.state.ws_counts[key_id]=count+1
    connected=False
    try:
        await ws.accept();ws_connections.inc();connected=True;app.state.audit.event("ws.connect",key_id=key_id,path=f"/ws/simulations/{rid}")
        for _ in range(120):
            if run["status"] in ("done","error"):break
            await asyncio.sleep(.5)
        if run["status"]!="done":await ws.close(code=4408);return
        speed=max(1,min(speed,200));start=time.monotonic()
        await ws.send_json({"type":"hello","run_id":rid,"n_steps":len(run["records"]),"dt_s":run["config"].dt_s})
        for row in run["records"]:
            if time.monotonic()-start>900:break
            await ws.send_json({"type":"step","data":row});await asyncio.sleep(1/speed)
        await ws.send_json({"type":"summary","data":run["summary"]});await ws.close()
    except WebSocketDisconnect:pass
    finally:
        if connected:
            try:ws_connections.dec()
            except Exception:pass
        app.state.ws_counts[key_id]=max(0,app.state.ws_counts.get(key_id,1)-1)
