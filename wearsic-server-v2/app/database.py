from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path

from .models import Playlist, PlaylistSummary, Track


class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS playlists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                    track_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (playlist_id, track_id)
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def favorites(self) -> list[Track]:
        with self._lock:
            rows = self._connection.execute("SELECT payload FROM favorites ORDER BY created_at DESC").fetchall()
        return [Track.model_validate(json.loads(row[0])) for row in rows]

    def add_favorite(self, track: Track) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO favorites(id, payload) VALUES (?, ?)",
                (track.id, track.model_dump_json()),
            )

    def remove_favorite(self, track_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute("DELETE FROM favorites WHERE id = ?", (track_id,))
            return cursor.rowcount > 0

    def playlists(self) -> list[PlaylistSummary]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT p.id, p.name, COUNT(t.track_id) AS track_count "
                "FROM playlists p LEFT JOIN playlist_tracks t ON t.playlist_id = p.id "
                "GROUP BY p.id ORDER BY p.created_at DESC"
            ).fetchall()
        return [PlaylistSummary(id=row[0], name=row[1], trackCount=row[2]) for row in rows]

    def create_playlist(self, name: str) -> PlaylistSummary:
        playlist_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute("INSERT INTO playlists(id, name) VALUES (?, ?)", (playlist_id, name.strip()))
        return PlaylistSummary(id=playlist_id, name=name.strip(), trackCount=0)

    def playlist(self, playlist_id: str) -> Playlist | None:
        with self._lock:
            row = self._connection.execute("SELECT id, name FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
            if row is None:
                return None
            tracks = self._connection.execute(
                "SELECT payload FROM playlist_tracks WHERE playlist_id = ? ORDER BY position, rowid",
                (playlist_id,),
            ).fetchall()
        return Playlist(id=row[0], name=row[1], tracks=[Track.model_validate(json.loads(r[0])) for r in tracks], trackCount=len(tracks))

    def add_track(self, playlist_id: str, track: Track) -> bool:
        with self._lock, self._connection:
            exists = self._connection.execute("SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
            if exists is None:
                return False
            position = self._connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()[0]
            self._connection.execute(
                "INSERT OR REPLACE INTO playlist_tracks(playlist_id, track_id, payload, position) VALUES (?, ?, ?, ?)",
                (playlist_id, track.id, track.model_dump_json(), position),
            )
            return True

    def remove_track(self, playlist_id: str, track_id: str) -> bool:
        with self._lock, self._connection:
            if track_id == "*":
                cursor = self._connection.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
            else:
                cursor = self._connection.execute(
                    "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                    (playlist_id, track_id),
                )
            return cursor.rowcount > 0
