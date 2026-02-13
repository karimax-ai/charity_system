import json
from typing import Optional

_cache = {}

async def get_cache(key: str) -> Optional[str]:
    return _cache.get(key)

async def set_cache(key: str, value: str, ttl: int = 300):
    _cache[key] = value
