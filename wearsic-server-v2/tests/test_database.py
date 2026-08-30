from __future__ import annotations

from app.database import Database
from app.models import Track


def test_favorites_and_playlist_lifecycle(tmp_path):
    database = Database(str(tmp_path / "wearsic.db"))
    track = Track(id="abc", title="Test Song")

    database.add_favorite(track)
    assert database.favorites()[0].id == "abc"
    assert database.remove_favorite("abc") is True
    assert database.favorites() == []

    playlist = database.create_playlist("My List")
    assert database.add_track(playlist.id, track) is True
    loaded = database.playlist(playlist.id)
    assert loaded is not None
    assert loaded.tracks[0].title == "Test Song"
    assert database.remove_track(playlist.id, "*") is True
    assert database.playlist(playlist.id) is None
    database.close()
