import asyncio
from monitoring.tasks import loop_lag_task

def test_loop_lag_task_can_be_cancelled():
    async def run():
        task=asyncio.create_task(loop_lag_task(.05))
        await asyncio.sleep(.08)
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        assert task.cancelled()
    asyncio.run(run())
