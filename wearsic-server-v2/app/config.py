from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


@dataclass(frozen=True)
class Settings:
    port: int
    db_path: str
    api_key: str
    primary_url: str
    ytdlp_bin: str
    request_timeout_seconds: int
    cache_ttl_seconds: int
    failure_threshold: int
    recovery_threshold: int
    max_concurrent_extractions: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            port=_int("PORT", 8081, 1),
            db_path=os.getenv("WEARSIC_DB_PATH", "wearsic-server-v2.db"),
            api_key=os.getenv("WEARSIC_API_KEY", "").strip(),
            primary_url=os.getenv("WEARSIC_PRIMARY_URL", "http://127.0.0.1:8080").rstrip("/"),
            ytdlp_bin=os.getenv("WEARSIC_YTDLP_BIN", "yt-dlp"),
            request_timeout_seconds=_int("WEARSIC_REQUEST_TIMEOUT_SECONDS", 30),
            cache_ttl_seconds=_int("WEARSIC_CACHE_TTL_SECONDS", 21600),
            failure_threshold=_int("WEARSIC_FAILURE_THRESHOLD", 3),
            recovery_threshold=_int("WEARSIC_RECOVERY_THRESHOLD", 3),
            max_concurrent_extractions=_int("WEARSIC_MAX_CONCURRENT_EXTRACTIONS", 2),
        )
