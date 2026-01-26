# queue.py
import os
from redis import Redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "video_jobs")

redis_conn = Redis.from_url(REDIS_URL)
queue = Queue(name=QUEUE_NAME, connection=redis_conn)
