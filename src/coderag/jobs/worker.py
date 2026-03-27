"""RQ worker placeholder.

This project keeps synchronous ingestion by default for easy local usage.
The worker module is included to align with the target architecture.
"""

from __future__ import annotations

import os

from coderag.core.settings import SETTINGS


def run_worker() -> None:
    """Start an RQ worker for ingestion queue."""
    from redis import Redis
    from rq import Connection, Queue, SimpleWorker, Worker
    from rq.timeouts import TimerDeathPenalty

    redis_conn = Redis.from_url(SETTINGS.redis_url)
    queue = Queue("ingestion", connection=redis_conn)
    with Connection(redis_conn):
        if os.name == "nt":
            # Windows has no os.fork()/SIGALRM; use thread-based worker.
            worker = SimpleWorker([queue], connection=redis_conn)
            worker.death_penalty_class = TimerDeathPenalty
            worker.work(with_scheduler=False)
        else:
            worker = Worker([queue])
            worker.work(with_scheduler=True)
