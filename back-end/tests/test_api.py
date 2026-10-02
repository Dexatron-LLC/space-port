"""API tests for the Spaceport Charter System (storage, loader, endpoints).

Each test gets a fresh SQLite file in tmp_path, loaded through the real seed
loader, and talks to the app in-process over httpx's ASGI transport.
"""

import asyncio
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


def booking(start, end, ship_id=2):
    """Build a booking request body for 2026-10-05 (Central, CDT) from HH:MM times."""
    return {"shipId": ship_id, "pilotName": "Ellen Ripley",
            "startTime": f"2026-10-05T{start}:00-05:00", "endTime": f"2026-10-05T{end}:00-05:00"}


NEW = booking("18:00", "19:00")  # Nostromo, clear of its 14:00-16:00 booking and buffer
CONFLICT = "Nostromo is not available then: it overlaps another booking or its 30-minute refuel buffer."


async def test_create_booking(client):
    r = await client.post("/api/bookings", json=NEW)
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body.pop("id"), int)
    assert body == NEW

    r = await client.get("/api/ships/2/availability", params={"date": "2026-10-05", "durationMinutes": 60})
    blocked = [s["start"] for s in r.json() if not s["available"]]
    assert blocked == [f"2026-10-05T{t}:00-05:00" for t in (
        "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00",
        "17:00", "17:30", "18:00", "18:30", "19:00",
    )]


@pytest.mark.parametrize(
    "start, end, status",
    [
        ("15:00", "17:00", 409),
        ("16:15", "17:00", 409),
        ("12:00", "13:45", 409),
        ("16:30", "17:30", 201),
        ("12:30", "13:30", 201),
    ],
    ids=["overlap", "buffer-after", "buffer-before", "exact-gap-after", "exact-gap-before"],
)
async def test_create_booking_conflicts(client, start, end, status):
    r = await client.post("/api/bookings", json=booking(start, end))
    assert r.status_code == status
    if status == 409:
        assert r.json() == {"detail": CONFLICT}


@pytest.mark.parametrize(
    "body, loc",
    [
        (booking("21:30", "22:30"), ["body"]),
        (booking("05:30", "06:30"), ["body"]),
        ({**NEW, "startTime": "2026-10-05T18:00:00", "endTime": "2026-10-05T19:00:00"}, ["body", "startTime"]),
        (booking("19:00", "18:00"), ["body"]),
        ({**NEW, "pilotName": "   "}, ["body", "pilotName"]),
        ({**NEW, "pilotName": "x" * 101}, ["body", "pilotName"]),
        ({k: v for k, v in NEW.items() if k != "pilotName"}, ["body", "pilotName"]),
    ],
    ids=["ends-after-close", "starts-before-open", "naive-times", "end-before-start",
         "blank-pilot", "pilot-101-chars", "missing-pilot"],
)
async def test_create_booking_invalid(client, body, loc):
    r = await client.post("/api/bookings", json=body)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == loc


async def test_create_booking_unknown_ship(client):
    r = await client.post("/api/bookings", json=booking("18:00", "19:00", ship_id=99))
    assert r.status_code == 404
    assert r.json() == {"detail": "Ship 99 not found"}


async def test_concurrent_bookings_cannot_double_book(client):
    # Two identical requests in flight at once, each on its own connection:
    # exactly one may win the slot.
    responses = await asyncio.gather(*(client.post("/api/bookings", json=NEW) for _ in range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]


async def test_fleet(client):
    r = await client.get("/api/fleet")
    assert r.status_code == 200
    fleet = r.json()
    assert [s["id"] for s in fleet] == [1, 2, 3]
    assert fleet[2]["bookings"] == []
    assert [b["startTime"] for b in fleet[0]["bookings"]] == ["2026-10-05T08:00:00-05:00", "2026-10-04T08:00:00-05:00"]
    for ship in fleet:
        for b in ship["bookings"]:
            assert b["shipId"] == ship["id"]
            assert set(b) == {"id", "shipId", "pilotName", "startTime", "endTime"}


async def test_loader_rejects_booking_outside_hours(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    bad = {**SEED, "bookings": [{"shipId": 1, "pilotName": "Early Bird",
                                 "startTime": "2026-10-05T05:00:00-05:00", "endTime": "2026-10-05T06:00:00-05:00"}]}
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(pydantic.ValidationError):
        await load_seed.load(path)
