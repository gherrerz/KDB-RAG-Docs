"""RQ worker placeholder.

This project keeps synchronous ingestion by default for easy local usage.
The worker module is included to align with the target architecture.
"""

from __future__ import annotations

from coderag.core.settings import SETTINGS


def run_worker() -> None:
    """Start an RQ worker for ingestion queue."""
    from redis import Redis
    from rq import Connection, Queue, Worker

    redis_conn = Redis.from_url(SETTINGS.redis_url)
    queue = Queue("ingestion", connection=redis_conn)
    with Connection(redis_conn):
        worker = Worker([queue])
        worker.work(with_scheduler=True)
