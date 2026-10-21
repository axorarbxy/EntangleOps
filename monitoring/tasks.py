from __future__ import annotations

import asyncio
import logging
import time

from . import metrics as m

log = logging.getLogger(__name__)


async def loop_lag_task(interval: float) -> None:
    interval = max(0.05, interval)
    target = asyncio.get_running_loop().time() + interval
    while True:
        await asyncio.sleep(max(0, target - asyncio.get_running_loop().time()))
        now = asyncio.get_running_loop().time()
        try: m.loop_lag.observe(max(0, now - target))
        except Exception: log.exception("Loop lag metric failed")
        target = now + interval


async def audit_verify_task(audit, interval: float) -> None:
    last_seq=0;last_hash="0"*64;total=0
    while True:
        try:
            if getattr(audit,"_db",False):
                ok,entries,_,new_seq,new_hash=await asyncio.to_thread(audit.verify_chain_from,audit._sf,last_seq,last_hash)
                if ok:last_seq,last_hash,total=new_seq,new_hash,total+entries
            else:
                ok,total,_=await asyncio.to_thread(audit.verify_chain,audit.path)
                entries=total
            m.audit_chain_ok.set(1 if ok else 0)
            m.audit_entries.set(total)
        except Exception:
            log.exception("Audit chain verification failed")
            try: m.audit_chain_ok.set(0)
            except Exception: pass
        await asyncio.sleep(max(1, interval))


async def db_maintenance_task(app, interval: float, lease_s: int) -> None:
    while True:
        try:
            runs = await asyncio.to_thread(app.state.store.repo.reap_stale, lease_s)
            tickets = await asyncio.to_thread(app.state.ticket_service.purge_expired)
            if runs or tickets:
                app.state.audit.event("db.maintenance", runs_reaped=runs, tickets_purged=tickets)
        except Exception:
            log.exception("Database maintenance failed")
        await asyncio.sleep(max(1, interval))
