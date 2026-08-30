from __future__ import annotations

import asyncio

import pytest

from app import main


@pytest.mark.asyncio
async def test_lifespan_runs_recovery_probe_only_during_healing(monkeypatch):
    calls = 0

    async def probe() -> bool:
        nonlocal calls
        calls += 1
        main.router.healing = False
        return True

    monkeypatch.setattr(main.settings, "probe_interval_seconds", 0.01, raising=False)
    monkeypatch.setattr(main.router, "healing", True)
    monkeypatch.setattr(main.router, "probe_primary", probe)

    async with main.lifespan(main.app):
        await asyncio.sleep(0.04)

    assert calls == 1
