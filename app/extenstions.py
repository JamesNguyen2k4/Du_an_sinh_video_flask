# app/extensions.py
import os
from redis import Redis
from rq import Queue

# Redis URL: ví dụ "redis://localhost:6379/0"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_conn: Redis | None = None
rq_queue: Queue | None = None


def init_extensions(app=None):
    global redis_conn, rq_queue
    redis_conn = Redis.from_url(REDIS_URL)
    rq_queue = Queue(
        name=os.getenv("RQ_QUEUE_NAME", "default"),
        connection=redis_conn,
        default_timeout=int(os.getenv("RQ_DEFAULT_TIMEOUT", "3600")),  # 1h
    )
    return rq_queue
