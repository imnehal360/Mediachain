"""Content-keyed caches. Values are serialized; no pickle deserialization."""

from __future__ import annotations

import time
from typing import Any

from mediachain.core.models import stable_id


def cache_key(content_hash: str, config: dict[str, Any], model_id: str, model_version: str) -> str:
    return stable_id("mediachain-cache-v1", content_hash, config, model_id, model_version)


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> str | None:
        item = self.values.get(key)
        if item is not None and item[0] > time.monotonic():
            return item[1]
        self.values.pop(key, None)
        return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        self.values[key] = (time.monotonic() + ttl, value)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        for key in list(self.values):
            if key.startswith(prefix):
                self.values.pop(key, None)


class RedisCache:
    def __init__(self, url: str, prefix: str = "mediachain:cache:"):
        from redis.asyncio import Redis

        self.client = Redis.from_url(url, decode_responses=True)
        self.prefix = prefix

    async def get(self, key: str) -> str | None:
        value = await self.client.get(self.prefix + key)
        return str(value) if value is not None else None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        await self.client.set(self.prefix + key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.client.delete(self.prefix + key)

    async def delete_prefix(self, prefix: str) -> None:
        # Prefixes are generated asset IDs, never raw user-supplied glob patterns.
        if any(c in prefix for c in "*?[]"):
            raise ValueError("Cache prefixes cannot contain wildcard characters")
        async for key in self.client.scan_iter(match=self.prefix + prefix + "*", count=100):
            await self.client.delete(key)

    async def close(self) -> None:
        await self.client.aclose()
