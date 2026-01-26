# worker.py
import os
from redis import Redis
from rq import Worker, Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "video_jobs")

listen = [QUEUE_NAME]

conn = Redis.from_url(REDIS_URL)

if __name__ == "__main__":
    worker = Worker(list(map(lambda n: Queue(n, connection=conn), listen)), connection=conn)
    worker.work()
