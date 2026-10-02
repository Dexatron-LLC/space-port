"""FastAPI app for the Spaceport Charter System."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Query

import db
import rules
from schemas import Ship, Slot


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database tables on startup if they do not exist."""
    async with db.connect() as conn:
        await conn.executescript(db.SCHEMA)
    yield


app = FastAPI(title="Spaceport Charter System", lifespan=lifespan)

Conn = Annotated[aiosqlite.Connection, Depends(db.get_db)]


async def require_ship(conn: aiosqlite.Connection, ship_id: int) -> aiosqlite.Row:
    """Return the ship row, or raise HTTP 404 if there is no such ship."""
    ship = await db.get_ship(conn, ship_id)
    if ship is None:
        raise HTTPException(404, f"Ship {ship_id} not found")
    return ship


@app.get("/api/ships")
async def get_ships(conn: Conn) -> list[Ship]:
    """List all ships, ordered by id."""
    return [Ship.model_validate(dict(row)) for row in await db.list_ships(conn)]


@app.get("/api/ships/{ship_id}/availability")
async def get_availability(
    ship_id: int,
    conn: Conn,
    day: Annotated[date, Query(alias="date")],
    duration_minutes: Annotated[int, Query(alias="durationMinutes", gt=0, le=24 * 60)],
) -> list[Slot]:
    """List every candidate slot of the requested length on a Central day.

    Args:
        ship_id: The ship to check.
        conn: Database connection (injected).
        day: Calendar day in Central Time (``date`` query parameter).
        duration_minutes: Charter length (``durationMinutes`` query parameter).

    Raises:
        HTTPException: 404 if the ship does not exist.
    """
    await require_ship(conn, ship_id)
    open_, close = rules.operating_window(day)
    # Only bookings within one buffer of the operating window can conflict
    # with any slot that day.
    booked = await db.bookings_between(conn, ship_id, open_ - rules.BUFFER, close + rules.BUFFER)
    return [
        Slot(start=s, end=e, available=a)
        for s, e, a in rules.day_slots(day, timedelta(minutes=duration_minutes), booked)
    ]
