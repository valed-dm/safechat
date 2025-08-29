import uuid

from redis.asyncio import Redis


CACHE_TTL = 600  # 10 minutes


async def cache_large_data(data: str, redis: Redis) -> str:
    """
    Stores a large string in Redis and returns a short, unique reference key.

    Args:
        data: The large string to store (e.g., encrypted hex).
        redis: The Redis client instance.

    Returns:
        A unique key that can be used to retrieve the data.
    """
    key = str(uuid.uuid4())
    redis_key = f"cache:{key}"
    await redis.setex(redis_key, CACHE_TTL, data)
    return key


async def retrieve_cached_data(key: str, redis: Redis) -> str | None:
    """
    Retrieves data from the cache using a reference key.

    Args:
        key: The unique key returned by cache_large_data.
        redis: The Redis client instance.

    Returns:
        The original data string, or None if it has expired.
    """
    return await redis.get(f"cache:{key}")
