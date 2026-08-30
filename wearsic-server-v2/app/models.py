from __future__ import annotations

from pydantic import BaseModel, Field


class Track(BaseModel):
    id: str
    title: str
    artist: str = "Unknown Artist"
    album: str | None = None
    artworkUrl: str | None = None
    durationMs: int = 0
    streamUrl: str = ""


class SearchResponse(BaseModel):
    results: list[Track] = Field(default_factory=list)


class SuggestionsResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)


class RelatedResponse(BaseModel):
    results: list[Track] = Field(default_factory=list)


class Album(BaseModel):
    id: str
    name: str
    uploader: str = ""
    trackCount: int = 0
    thumbnailUrl: str | None = None


class PlaylistSummary(BaseModel):
    id: str
    name: str
    trackCount: int = 0
    thumbnailUrl: str | None = None


class Playlist(PlaylistSummary):
    tracks: list[Track] = Field(default_factory=list)


class CreatePlaylistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
    serverName: str = "Wearsic Engine V2"
    engine: str = "primary"
    healing: bool = False
    uptimeSeconds: int = 0


class ErrorResponse(BaseModel):
    error: str
