# worker.py
import os
from redis import Redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import NoDeathPenalty

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "video_jobs")

listen = [QUEUE_NAME]
conn = Redis.from_url(REDIS_URL)

if __name__ == "__main__":
    queues = [Queue(name, connection=conn) for name in listen]

    worker = SimpleWorker(
        queues,
        connection=conn,
        death_penalty_class=NoDeathPenalty,   # ✅ Windows: không dùng SIGALRM
    )

    worker.work(with_scheduler=False)