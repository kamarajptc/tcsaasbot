import redis

from app.infrastructure.ports.cache import CachePort


class RedisCache(CachePort):
    def __init__(self, redis_url: str):
        self.client = redis.Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self.client.set(name=key, value=value, ex=ttl_seconds)
