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
    while True:
        try:
            ok, entries, _ = await asyncio.to_thread(audit.verify_chain, audit.path)
            m.audit_chain_ok.set(1 if ok else 0)
            m.audit_entries.set(entries)
        except Exception:
            log.exception("Audit chain verification failed")
            try: m.audit_chain_ok.set(0)
            except Exception: pass
        await asyncio.sleep(max(1, interval))
