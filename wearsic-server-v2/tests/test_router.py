from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.models import SearchResponse, Track
from app.providers import MusicProvider, ProviderError
from app.router import ProviderRouter


class FakeProvider(MusicProvider):
    def __init__(self, name: str, failures: int = 0):
        self.name = name
        self.failures = failures
        self.calls = 0

    async def search(self, query: str) -> SearchResponse:
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ProviderError(f"{self.name} failure")
        return SearchResponse(results=[Track(id=self.name, title=query)])

    async def suggestions(self, query: str):
        return {"suggestions": []}

    async def related(self, video_id: str):
        return {"results": []}

    async def albums(self, query: str):
        return []

    async def playlist_by_url(self, url: str):
        return []

    async def resolve_stream(self, video_id: str):
        return "https://example.test/audio", "audio/webm"


def settings() -> Settings:
    return Settings(
        port=8081,
        db_path=":memory:",
        api_key="",
        primary_url="http://primary",
        ytdlp_bin="yt-dlp",
        request_timeout_seconds=1,
        cache_ttl_seconds=1,
        failure_threshold=2,
        recovery_threshold=2,
        probe_interval_seconds=1,
        max_concurrent_extractions=1,
    )


@pytest.mark.asyncio
async def test_router_fails_over_after_threshold():
    primary = FakeProvider("primary", failures=2)
    backup = FakeProvider("ytdlp")
    router = ProviderRouter(settings(), primary, backup)

    first = await router.search("one")
    second = await router.search("two")

    assert first.results[0].id == "ytdlp"
    assert second.results[0].id == "ytdlp"
    assert router.active is backup
    assert router.healing is True


@pytest.mark.asyncio
async def test_primary_probe_requires_recovery_threshold():
    primary = FakeProvider("primary")
    backup = FakeProvider("ytdlp")
    router = ProviderRouter(settings(), primary, backup)
    router.active = backup
    router.healing = True

    assert await router.probe_primary() is True
    assert router.active is backup
    assert await router.probe_primary() is True
    assert router.active is primary
    assert router.healing is False
