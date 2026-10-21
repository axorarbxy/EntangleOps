from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Path, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.db.session import run_db
from monitoring.metrics import ws_connections
from security.auth import Principal

router = APIRouter()


@router.websocket("/ws/simulations/{rid}")
async def replay(ws: WebSocket, rid: str = Path(pattern=r"^[A-Za-z0-9_-]{8,32}$"),
                 ticket: str = Query(default=""), speed: int = 50):
    app = ws.app
    origins = settings.ws_allowed_origins or settings.cors_origins
    origin = ws.headers.get("origin")
    if (origin is None and settings.env != "development") or (origin is not None and "*" not in origins and origin not in origins):
        app.state.audit.event("ws.deny", reason="origin", path=f"/ws/simulations/{rid}")
        await ws.close(code=4403); return
    key_id = await run_db(app.state.ticket_service.redeem, ticket, rid)
    if key_id is None:
        app.state.audit.event("ws.deny", reason="ticket", path=f"/ws/simulations/{rid}")
        await ws.close(code=4401); return
    rec = await run_db(app.state.keystore.get, key_id, fresh=True)
    principal = Principal(rec.key_id, rec.name, rec.role) if rec else None
    run = await run_db(app.state.store.get_for, principal, rid) if principal else None
    if run is None:
        app.state.audit.event("ws.deny", key_id=key_id, reason="revoked", path=f"/ws/simulations/{rid}")
        await ws.close(code=4401); return
    count = app.state.ws_counts.get(key_id, 0)
    if count >= settings.max_ws_per_key:
        app.state.audit.event("ws.deny", key_id=key_id, reason="limit", path=f"/ws/simulations/{rid}")
        await ws.close(code=4429); return
    app.state.ws_counts[key_id] = count + 1
    connected = False
    try:
        await ws.accept(); ws_connections.inc(); connected = True
        app.state.audit.event("ws.connect", key_id=key_id, path=f"/ws/simulations/{rid}")
        run = await run_db(app.state.store.get_for, principal, rid)
        for _ in range(120):
            if run is None or run["status"] in ("done", "error"): break
            await asyncio.sleep(.5)
            run = await run_db(app.state.store.get_for, principal, rid)
        if run is None or run["status"] != "done":
            await ws.close(code=4408); return
        config = run["config"]
        await ws.send_json({"type": "hello", "run_id": rid, "n_steps": run["n_steps"], "dt_s": config.dt_s})
        speed = max(1, min(speed, 200)); started = time.monotonic(); after = -1
        while time.monotonic() - started <= 900:
            batch = await run_db(app.state.store.repo.read_steps, rid, after, 200)
            if not batch: break
            for row in batch:
                await ws.send_json({"type": "step", "data": row})
                after = row["step"]
                await asyncio.sleep(1 / speed)
        await ws.send_json({"type": "summary", "data": run["summary"]})
        await ws.close()
    except WebSocketDisconnect:
        pass
    finally:
        if connected:
            try: ws_connections.dec()
            except Exception: pass
        app.state.ws_counts[key_id] = max(0, app.state.ws_counts.get(key_id, 1) - 1)
