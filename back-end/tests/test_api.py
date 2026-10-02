"""API tests for the Spaceport Charter System (storage, loader, read endpoints).

Each test gets a fresh SQLite file in tmp_path, loaded through the real seed
loader, and talks to the app in-process over httpx's ASGI transport.
"""

import json

import httpx
import pydantic
import pytest

import db
import load_seed
from main import app

SEED = {
    "ships": [{"id": 1, "name": "USS Wanderer"}, {"id": 2, "name": "Nostromo"}, {"id": 3, "name": "Serenity"}],
    "bookings": [
        {"shipId": 2, "pilotName": "Ellen Ripley", "startTime": "2026-10-05T14:00:00-05:00", "endTime": "2026-10-05T16:00:00-05:00"},
        {"shipId": 1, "pilotName": "Han Solo",     "startTime": "2026-10-04T08:00:00-05:00", "endTime": "2026-10-04T09:00:00-05:00"},
        {"shipId": 1, "pilotName": "Leia Organa",  "startTime": "2026-10-05T08:00:00-05:00", "endTime": "2026-10-05T09:00:00-05:00"},
    ],
}


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Yield an HTTP client on an app backed by a freshly seeded temp database."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(SEED))
    await load_seed.load(path)
    # ASGITransport does not run the lifespan; the loader already made the schema.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_ships(client):
    r = await client.get("/api/ships")
    assert r.status_code == 200
    assert r.json() == [
        {"id": 1, "name": "USS Wanderer"},
        {"id": 2, "name": "Nostromo"},
        {"id": 3, "name": "Serenity"},
    ]


async def test_availability(client):
    r = await client.get("/api/ships/2/availability", params={"date": "2026-10-05", "durationMinutes": 60})
    assert r.status_code == 200
    slots = r.json()
    assert len(slots) == 31
    assert slots[0] == {"start": "2026-10-05T06:00:00-05:00", "end": "2026-10-05T07:00:00-05:00", "available": True}
    blocked = [s["start"] for s in slots if not s["available"]]
    assert blocked == [f"2026-10-05T{t}:00-05:00" for t in ("13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00")]


async def test_availability_errors(client):
    r = await client.get("/api/ships/99/availability", params={"date": "2026-10-05", "durationMinutes": 60})
    assert r.status_code == 404
    assert r.json() == {"detail": "Ship 99 not found"}
    for params in (
        {"date": "2026-10-05", "durationMinutes": 0},
        {"date": "2026-13-01", "durationMinutes": 60},
        {"date": "2026-10-05"},
    ):
        r = await client.get("/api/ships/1/availability", params=params)
        assert r.status_code == 422, params


async def test_loader_rejects_booking_outside_hours(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    bad = {**SEED, "bookings": [{"shipId": 1, "pilotName": "Early Bird",
                                 "startTime": "2026-10-05T05:00:00-05:00", "endTime": "2026-10-05T06:00:00-05:00"}]}
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(pydantic.ValidationError):
        await load_seed.load(path)
