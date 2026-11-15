"""Background worker (E1): scheduled scouting and degraded-mode recovery.

Graph runs execute inside the API process (it owns the MCP sessions and the live-run registry);
the worker only decides *when*. It calls the API's internal endpoints with INTERNAL_TOKEN.

    arq worker.main.WorkerSettings          # with Redis (production; retries + no double-scheduling)
    python -m worker.main --loop            # no Redis (local dev)

Schedules: scouting every SCOUT_EVERY_MIN (default 30 for GigSim; set to the live poll interval,
180, in upwork_live mode); retry of parked threads every 2 minutes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx

API = os.environ.get("API_URL", "http://localhost:8000")
HEADERS = {"X-Internal-Token": os.environ.get("INTERNAL_TOKEN", "")}
SCOUT_EVERY_MIN = int(os.environ.get("SCOUT_EVERY_MIN", "30"))
log = logging.getLogger("gigbid.worker")


async def _post(path: str) -> dict:
    async with httpx.AsyncClient(base_url=API, headers=HEADERS, timeout=120) as c:
        r = await c.post(path)
        r.raise_for_status()
        return r.json()


async def scout_all(ctx=None):
    res = await _post("/internal/scout_all")
    log.info("scout: %s", res)
    return res


async def retry_waiting(ctx=None):
    res = await _post("/internal/retry_waiting")
    log.info("retry: %s", res)
    return res


try:
    from arq import cron
    from arq.connections import RedisSettings

    class WorkerSettings:
        functions = [scout_all, retry_waiting]
        cron_jobs = [
            cron(scout_all, minute=set(range(0, 60, max(1, min(SCOUT_EVERY_MIN, 60))))) if SCOUT_EVERY_MIN <= 60
            else cron(scout_all, hour=set(range(0, 24, SCOUT_EVERY_MIN // 60)), minute={7}),
            cron(retry_waiting, minute=set(range(0, 60, 2))),
        ]
        redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        max_tries = 3
except ImportError:  # arq not installed: the --loop mode still works
    WorkerSettings = None


async def loop():
    tick = 0
    while True:
        try:
            if tick % SCOUT_EVERY_MIN == 0:
                await scout_all()
            if tick % 2 == 0:
                await retry_waiting()
        except Exception as exc:  # noqa: BLE001
            log.warning("worker tick failed: %s", exc)
        tick += 1
        await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--loop" in sys.argv:
        asyncio.run(loop())
    else:
        print(__doc__)
