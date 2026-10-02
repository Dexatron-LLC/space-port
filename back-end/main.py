"""FastAPI app for the Spaceport Charter System."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Query

import db
import rules
from schemas import BookingCreate, BookingOut, FleetShip, Ship, Slot


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


@app.post("/api/bookings", status_code=201)
async def create_booking(booking: BookingCreate, conn: Conn) -> BookingOut:
    """Book a ship, unless it conflicts with the ship's existing bookings.

    Args:
        booking: The requested booking, already validated by Pydantic.
        conn: Database connection (injected).

    Returns:
        The stored booking, with its new id.

    Raises:
        HTTPException: 404 if the ship does not exist; 409 if the booking
            overlaps another booking on the ship or its refuel buffer.
    """
    # By now Pydantic has already answered 422 for input that is invalid
    # whatever is stored (bad times, outside hours, bad pilot name).
    ship = await require_ship(conn, booking.ship_id)  # 404 for an unknown ship
    # BEGIN IMMEDIATE takes the write lock BEFORE the conflict check, so the
    # check and the insert are atomic: a concurrent request for the same slot
    # waits on SQLite's busy timeout (the sqlite3 default, 5 s), then sees this
    # booking and gets a 409, instead of both passing the check and
    # double-booking the ship.
    async with db.immediate_transaction(conn):
        # Only bookings within one buffer of the request can conflict with it.
        nearby = await db.bookings_between(
            conn, booking.ship_id, booking.start_time - rules.BUFFER, booking.end_time + rules.BUFFER
        )
        if rules.has_conflict(booking.start_time, booking.end_time, nearby):
            # 409, not 422: the input is valid, but it conflicts with stored
            # bookings. Raising inside the block rolls the transaction back.
            raise HTTPException(
                409,
                f"{ship['name']} is not available then: it overlaps another booking "
                f"or its {rules.BUFFER // timedelta(minutes=1)}-minute refuel buffer.",
            )
        booking_id = await db.insert_booking(
            conn, booking.ship_id, booking.pilot_name, booking.start_time, booking.end_time
        )
    return BookingOut(id=booking_id, **booking.model_dump())


@app.get("/api/fleet")
async def get_fleet(conn: Conn) -> list[FleetShip]:
    """List every ship in id order with all of its bookings, newest first.

    Ships with no bookings are included with an empty list. No filters or
    pagination: the whole fleet's bookings (a few thousand rows) are small.
    """
    ships = await db.list_ships(conn)
    # Two queries grouped in Python: simpler than reshaping a LEFT JOIN's flat
    # rows; every ship starts with an empty list, so ships with no bookings
    # are kept.
    by_ship = {s["id"]: [] for s in ships}
    for row in await db.list_bookings(conn):
        by_ship[row["ship_id"]].append(BookingOut.model_validate(dict(row)))
    return [FleetShip(id=s["id"], name=s["name"], bookings=by_ship[s["id"]]) for s in ships]
