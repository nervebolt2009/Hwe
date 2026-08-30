from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .config import Settings
from .database import Database
from .models import (
    CreatePlaylistRequest,
    HealthResponse,
    RelatedResponse,
    SearchResponse,
    SuggestionsResponse,
    Track,
)
from .providers import PrimaryHttpProvider, ProviderError, YtDlpProvider
from .router import ProviderRouter

settings = Settings.from_env()
database = Database(settings.db_path)
router = ProviderRouter(settings, PrimaryHttpProvider(settings), YtDlpProvider(settings))


async def _primary_recovery_loop() -> None:
    while True:
        await asyncio.sleep(settings.probe_interval_seconds)
        if not router.healing:
            continue
        try:
            await router.probe_primary()
        except Exception:
            # A failed probe must never terminate the recovery worker or app.
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    recovery_task = asyncio.create_task(_primary_recovery_loop())
    try:
        yield
    finally:
        recovery_task.cancel()
        await asyncio.gather(recovery_task, return_exceptions=True)
        database.close()


app = FastAPI(title="Wearsic Server V2", version="2.0.0", lifespan=lifespan)


def require_api_key(x_wearsic_key: str | None = Header(default=None)) -> None:
    if settings.api_key and not secrets.compare_digest(x_wearsic_key or "", settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Wearsic-Key")


def provider_error(exc: ProviderError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        engine=router.active.name,
        healing=router.healing,
        uptimeSeconds=router.uptime_seconds(),
    )


@app.get("/api/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)])
async def search(q: str = Query(default="", min_length=1, max_length=200)) -> SearchResponse:
    try:
        return await router.search(q)
    except ProviderError as exc:
        raise provider_error(exc)


@app.get("/api/suggestions", response_model=SuggestionsResponse, dependencies=[Depends(require_api_key)])
async def suggestions(q: str = Query(default="", max_length=200)) -> SuggestionsResponse:
    try:
        return await router.suggestions(q)
    except ProviderError as exc:
        raise provider_error(exc)


@app.get("/api/related/{video_id}", response_model=RelatedResponse, dependencies=[Depends(require_api_key)])
async def related(video_id: str) -> RelatedResponse:
    try:
        return await router.related(video_id)
    except ProviderError as exc:
        raise provider_error(exc)


@app.get("/api/search/albums", dependencies=[Depends(require_api_key)])
async def albums(q: str = Query(min_length=1, max_length=200)):
    try:
        return await router.albums(q)
    except ProviderError as exc:
        raise provider_error(exc)


@app.get("/api/playlist", dependencies=[Depends(require_api_key)])
async def playlist_by_url(url: str = Query(min_length=1, max_length=2000)):
    try:
        tracks = await router.playlist_by_url(url)
        return {"id": url, "name": "Playlist", "tracks": tracks}
    except ProviderError as exc:
        raise provider_error(exc)


@app.get("/api/favorites", dependencies=[Depends(require_api_key)])
async def favorites():
    return [track.model_dump() for track in database.favorites()]


@app.post("/api/favorites", dependencies=[Depends(require_api_key)])
async def add_favorite(track: Track):
    database.add_favorite(track)
    return {"ok": True}


@app.delete("/api/favorites/{video_id}", dependencies=[Depends(require_api_key)])
async def remove_favorite(video_id: str):
    database.remove_favorite(video_id)
    return {"ok": True}


@app.get("/api/playlists", dependencies=[Depends(require_api_key)])
async def playlists():
    return [playlist.model_dump() for playlist in database.playlists()]


@app.post("/api/playlists", dependencies=[Depends(require_api_key)])
async def create_playlist(payload: CreatePlaylistRequest):
    return database.create_playlist(payload.name)


@app.get("/api/playlists/{playlist_id}", dependencies=[Depends(require_api_key)])
async def get_playlist(playlist_id: str):
    playlist = database.playlist(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


@app.post("/api/playlists/{playlist_id}/tracks", dependencies=[Depends(require_api_key)])
async def add_playlist_track(playlist_id: str, track: Track):
    if not database.add_track(playlist_id, track):
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"ok": True}


@app.delete("/api/playlists/{playlist_id}/tracks/{video_id}", dependencies=[Depends(require_api_key)])
async def remove_playlist_track(playlist_id: str, video_id: str):
    database.remove_track(playlist_id, video_id)
    return {"ok": True}


@app.get("/api/stream/{video_id}", dependencies=[Depends(require_api_key)])
async def stream(video_id: str, request: Request):
    try:
        target, content_type = await router.resolve_stream(video_id)
    except ProviderError as exc:
        raise provider_error(exc)

    headers = {}
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]
    client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    try:
        upstream = await client.send(client.build_request("GET", target, headers=headers), stream=True)
        upstream.raise_for_status()
    except Exception as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"stream upstream failed: {exc}")

    response_headers = {}
    for name in ("content-length", "content-range", "accept-ranges"):
        if name in upstream.headers:
            response_headers[name] = upstream.headers[name]

    async def close_upstream() -> None:
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_bytes(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", content_type),
        headers=response_headers,
        background=BackgroundTask(close_upstream),
    )
