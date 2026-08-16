import redis.asyncio as aioredis
from app.core.config import settings

_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


async def publish_event(channel: str, payload: str):
    r = get_redis()
    await r.publish(channel, payload)
