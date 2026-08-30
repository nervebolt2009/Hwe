from __future__ import annotations

import asyncio
import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .models import Album, RelatedResponse, SearchResponse, SuggestionsResponse, Track


class ProviderError(RuntimeError):
    pass


def normalize_track(item: dict[str, Any]) -> Track:
    """Build a Track accepting BOTH response dialects.

    V1 (NewPipe server): videoId / uploader / thumbnailUrl, no streamUrl.
    V2 native:           id / artist / artworkUrl / streamUrl.
    The app requires the V2 names; the stream URL is synthesized when the
    upstream does not provide one (the gateway's /api/stream route serves it).
    """
    track_id = str(item.get("id") or item.get("videoId") or "").strip()
    artist = str(item.get("artist") or item.get("uploader") or "Unknown Artist")
    artwork = item.get("artworkUrl") or item.get("thumbnailUrl")
    stream = str(item.get("streamUrl") or "").strip()
    if not stream and track_id:
        stream = f"/api/stream/{quote(track_id, safe='')}"
    return Track(
        id=track_id,
        title=str(item.get("title") or track_id),
        artist=artist,
        album=item.get("album"),
        artworkUrl=artwork,
        durationMs=int(item.get("durationMs") or 0),
        streamUrl=stream,
    )


class MusicProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str) -> SearchResponse: ...

    @abstractmethod
    async def suggestions(self, query: str) -> SuggestionsResponse: ...

    @abstractmethod
    async def related(self, video_id: str) -> RelatedResponse: ...

    @abstractmethod
    async def albums(self, query: str) -> list[Album]: ...

    @abstractmethod
    async def playlist_by_url(self, url: str) -> list[Track]: ...

    @abstractmethod
    async def resolve_stream(self, video_id: str) -> tuple[str, str]: ...


class PrimaryHttpProvider(MusicProvider):
    name = "primary"

    def __init__(self, settings: Settings):
        self.base_url = settings.primary_url
        self.timeout = settings.request_timeout_seconds

    async def _get(self, path: str, **params: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise ProviderError(f"primary provider failed: {exc}") from exc

    async def search(self, query: str) -> SearchResponse:
        data = await self._get("/api/search", q=query)
        return SearchResponse(results=[normalize_track(item) for item in data.get("results", [])])

    async def suggestions(self, query: str) -> SuggestionsResponse:
        data = await self._get("/api/suggestions", q=query)
        return SuggestionsResponse.model_validate(data)

    async def related(self, video_id: str) -> RelatedResponse:
        data = await self._get(f"/api/related/{quote(video_id, safe='')}")
        items = data.get("results", []) if isinstance(data, dict) else []
        return RelatedResponse(results=[normalize_track(item) for item in items])

    async def albums(self, query: str) -> list[Album]:
        data = await self._get("/api/search/albums", q=query)
        return [Album.model_validate(item) for item in data]

    async def playlist_by_url(self, url: str) -> list[Track]:
        data = await self._get("/api/playlist", url=url)
        return [normalize_track(item) for item in data.get("tracks", [])]

    async def resolve_stream(self, video_id: str) -> tuple[str, str]:
        # The primary server's stream route is already compatible with the app.
        return f"{self.base_url}/api/stream/{quote(video_id, safe='')}", "audio/webm"


class YtDlpProvider(MusicProvider):
    name = "ytdlp"

    def __init__(self, settings: Settings):
        self.binary = shutil.which(settings.ytdlp_bin) or settings.ytdlp_bin
        self.timeout = settings.request_timeout_seconds
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_extractions)

    async def _run(self, *args: str) -> Any:
        async with self.semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    self.binary,
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                raise ProviderError("yt-dlp extraction timed out") from exc
            except OSError as exc:
                raise ProviderError(f"yt-dlp unavailable: {exc}") from exc
            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip().splitlines()[-1:] or ["unknown error"]
                raise ProviderError(f"yt-dlp failed: {detail[0]}")
            try:
                return json.loads(stdout.decode())
            except json.JSONDecodeError as exc:
                raise ProviderError("yt-dlp returned invalid JSON") from exc

    @staticmethod
    def _track(info: dict[str, Any]) -> Track:
        video_id = str(info.get("id", ""))
        duration = info.get("duration") or 0
        thumbnail = info.get("thumbnail")
        return Track(
            id=video_id,
            title=str(info.get("title") or video_id),
            artist=str(info.get("uploader") or info.get("channel") or "Unknown Artist"),
            album=None,
            artworkUrl=thumbnail,
            durationMs=int(float(duration) * 1000),
            streamUrl=f"/api/stream/{quote(video_id, safe='')}",
        )

    async def search(self, query: str) -> SearchResponse:
        data = await self._run("ytsearch10:" + query, "--flat-playlist", "--dump-single-json", "--no-warnings")
        return SearchResponse(results=[self._track(item) for item in data.get("entries", []) if item.get("id")])

    async def suggestions(self, query: str) -> SuggestionsResponse:
        result = await self.search(query)
        return SuggestionsResponse(suggestions=[track.title for track in result.results[:5]])

    async def related(self, video_id: str) -> RelatedResponse:
        data = await self._run(f"https://www.youtube.com/watch?v={quote(video_id, safe='')}", "--flat-playlist", "--dump-single-json", "--no-warnings")
        entries = data.get("entries", [])
        return RelatedResponse(results=[self._track(item) for item in entries[:10] if item.get("id")])

    async def albums(self, query: str) -> list[Album]:
        data = await self._run("ytsearch10:" + query + " album", "--flat-playlist", "--dump-single-json", "--no-warnings")
        return [Album(id=str(item.get("webpage_url") or item.get("url") or item.get("id")), name=str(item.get("title") or "Album"), uploader=str(item.get("uploader") or "")) for item in data.get("entries", [])[:10]]

    async def playlist_by_url(self, url: str) -> list[Track]:
        data = await self._run(url, "--flat-playlist", "--dump-single-json", "--no-warnings")
        return [self._track(item) for item in data.get("entries", [])[:10] if item.get("id")]

    async def resolve_stream(self, video_id: str) -> tuple[str, str]:
        async with self.semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    self.binary,
                    f"https://www.youtube.com/watch?v={quote(video_id, safe='')}",
                    "-f", "ba[ext=webm]/ba[ext=m4a]/ba",
                    "-g",
                    "--no-playlist",
                    "--no-warnings",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                raise ProviderError("yt-dlp stream resolution timed out") from exc
            except OSError as exc:
                raise ProviderError(f"yt-dlp unavailable: {exc}") from exc
            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip().splitlines()[-1:] or ["unknown error"]
                raise ProviderError(f"yt-dlp failed: {detail[0]}")
            url = stdout.decode(errors="replace").strip().splitlines()[0] if stdout else ""
        if not url:
            raise ProviderError("yt-dlp did not return a stream URL")
        return url, "audio/webm"
