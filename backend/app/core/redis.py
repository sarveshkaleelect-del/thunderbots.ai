import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)
redis_client: Optional[aioredis.Redis] = None


async def init_redis():
    global redis_client
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Verify connection
        await redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis unavailable — caching disabled: {e}")
        redis_client = None


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> Optional[aioredis.Redis]:
    return redis_client


class CacheService:
    """
    FIX: All methods are now safe when Redis is unavailable.
    The app degrades gracefully — no caching, but still functional.

    PERF/CORRECTNESS FIX (v107): `self.redis` is now a property that reads
    the module-level `redis_client` live on every access, instead of being
    captured once in __init__. Several call sites across the codebase
    (e.g. business_advisor_service.py) construct a module-level
    `_cache = CacheService()` singleton at *import* time — which runs
    before `lifespan()` calls `init_redis()` at app startup. With the old
    `self.redis = redis_client` assignment, that singleton permanently
    captured `None` and silently ran with caching disabled forever, even
    though Redis was healthy — an invisible bottleneck that pushes extra
    load onto Postgres for every request under concurrency. Making it a
    property fixes every existing and future call site in one place.
    """

    @property
    def redis(self) -> Optional[aioredis.Redis]:
        return redis_client

    async def get(self, key: str) -> Optional[Any]:

        if not self.redis:
            return None
        try:
            val = await self.redis.get(key)
            return json.loads(val) if val else None
        except Exception as e:
            logger.warning(f"Redis GET failed for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.setex(key, ttl, json.dumps(value, default=str))
            return True
        except Exception as e:
            logger.warning(f"Redis SET failed for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE failed for {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        # SCALABILITY FIX (v107): KEYS is O(N) over the *entire* keyspace and
        # blocks the single-threaded Redis event loop for its whole
        # duration — under 1,000+ concurrent users sharing one Redis
        # instance, a single cache-invalidation call could stall every other
        # request hitting Redis at the same time. SCAN walks the keyspace in
        # small cursor-based batches with no blocking, at the cost of no
        # longer being atomic (acceptable here: these are invalidation
        # sweeps, not correctness-critical transactions).
        if not self.redis:
            return 0
        try:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    await self.redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            return deleted
        except Exception as e:
            logger.warning(f"Redis DELETE pattern failed for {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        if not self.redis:
            return False
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.warning(f"Redis EXISTS failed for {key}: {e}")
            return False
