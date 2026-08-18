import hashlib
import json
from functools import lru_cache

import redis

from app.config import settings

SEARCH_CACHE_TTL_SECONDS = 60 * 60  # 1 hour — doc corpus changes rarely, safe to cache generously


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def search_cache_key(query: str, k: int) -> str:
    digest = hashlib.sha256(f"{query.strip().lower()}:{k}".encode()).hexdigest()
    return f"search:{digest}"


def get_cached_search(query: str, k: int) -> list[dict] | None:
    raw = get_redis().get(search_cache_key(query, k))
    return json.loads(raw) if raw else None


def set_cached_search(query: str, k: int, results: list[dict]) -> None:
    get_redis().setex(search_cache_key(query, k), SEARCH_CACHE_TTL_SECONDS, json.dumps(results))
