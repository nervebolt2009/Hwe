from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .config import Settings
from .models import Album, RelatedResponse, SearchResponse, SuggestionsResponse, Track
from .providers import MusicProvider, ProviderError


@dataclass
class ProviderHealth:
    failures: int = 0
    successes: int = 0


class ProviderRouter:
    def __init__(self, settings: Settings, primary: MusicProvider, backup: MusicProvider):
        self.settings = settings
        self.primary = primary
        self.backup = backup
        self.active: MusicProvider = primary
        self.health = {primary.name: ProviderHealth(), backup.name: ProviderHealth()}
        self.healing = False
        self.started_at = time.monotonic()
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, object]] = {}
        self._cache_limit = 256

    def uptime_seconds(self) -> int:
        return int(time.monotonic() - self.started_at)

    def _cached(self, key: str) -> object | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry[0] <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return entry[1]

    def _put(self, key: str, value: object) -> object:
        if len(self._cache) >= self._cache_limit:
            oldest = min(self._cache, key=lambda item: self._cache[item][0])
            self._cache.pop(oldest, None)
        self._cache[key] = (time.monotonic() + self.settings.cache_ttl_seconds, value)
        return value

    async def _success(self, provider: MusicProvider) -> None:
        async with self._lock:
            state = self.health[provider.name]
            state.failures = 0
            state.successes += 1

    async def _failure(self, provider: MusicProvider) -> None:
        async with self._lock:
            state = self.health[provider.name]
            state.failures += 1
            state.successes = 0
            if provider is self.primary and state.failures >= self.settings.failure_threshold:
                self.active = self.backup
                self.healing = True
                self.health[self.backup.name].successes = 0

    async def _call(self, method: str, *args: str):
        key = method + ":" + ":".join(args)
        cached = self._cached(key)
        if cached is not None:
            return cached
        provider = self.active
        try:
            result = await getattr(provider, method)(*args)
            await self._success(provider)
            return self._put(key, result)
        except ProviderError as primary_error:
            await self._failure(provider)
            if provider is self.primary:
                try:
                    result = await getattr(self.backup, method)(*args)
                    await self._success(self.backup)
                    return self._put(key, result)
                except ProviderError as backup_error:
                    await self._failure(self.backup)
                    raise ProviderError(f"primary and backup providers failed: {backup_error}") from primary_error
            raise

    async def probe_primary(self) -> bool:
        try:
            await self.primary.search("test")
        except ProviderError:
            async with self._lock:
                self.health[self.primary.name].successes = 0
            return False
        async with self._lock:
            state = self.health[self.primary.name]
            state.failures = 0
            state.successes += 1
            if state.successes >= self.settings.recovery_threshold:
                self.active = self.primary
                self.healing = False
        return True

    async def search(self, query: str) -> SearchResponse:
        return await self._call("search", query)

    async def suggestions(self, query: str) -> SuggestionsResponse:
        return await self._call("suggestions", query)

    async def related(self, video_id: str) -> RelatedResponse:
        return await self._call("related", video_id)

    async def albums(self, query: str) -> list[Album]:
        return await self._call("albums", query)

    async def playlist_by_url(self, url: str) -> list[Track]:
        return await self._call("playlist_by_url", url)

    async def resolve_stream(self, video_id: str) -> tuple[str, str]:
        return await self._call("resolve_stream", video_id)
