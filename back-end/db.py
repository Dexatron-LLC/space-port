"""SQLite storage for the Spaceport Charter System, via raw aiosqlite (no ORM)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).parent / "spaceport.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ships (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    id         INTEGER PRIMARY KEY,
    ship_id    INTEGER NOT NULL REFERENCES ships (id),
    pilot_name TEXT NOT NULL,
    start_time TEXT NOT NULL,  -- UTC, fixed-width ISO-8601: text order == time order
    end_time   TEXT NOT NULL   -- UTC, fixed-width ISO-8601
);
CREATE INDEX IF NOT EXISTS bookings_by_ship_time ON bookings (ship_id, start_time);
"""


def to_db(dt: datetime) -> str:
    """Format an aware datetime as the fixed-width UTC text we store.

    Args:
        dt: Aware datetime in any time zone.

    Returns:
        ISO-8601 UTC text, e.g. ``2026-10-05T19:00:00.000000+00:00``.
    """
    # SQLite has no time-zone type. Storing every time as same-width UTC text
    # makes string comparison equal time comparison. The seed's raw strings
    # mix -05:00/-06:00 and would mis-sort (07:00-06:00 = 13:00Z sorts before
    # 07:30-05:00 = 12:30Z).
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


@asynccontextmanager
async def connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open a connection to the database and close it afterwards."""
    # DB_PATH is read here, at call time, so tests can point it at a temp file.
    # isolation_level=None is autocommit: the sqlite3 module's implicit
    # transactions are off and we open transactions explicitly where needed.
    # SQLite ignores foreign keys unless enabled on every connection.
    conn = await aiosqlite.connect(DB_PATH, isolation_level=None)
    try:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    finally:
        await conn.close()


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI dependency: yield a connection for the duration of one request."""
    # One connection per request: a shared connection would interleave
    # concurrent requests' transactions.
    async with connect() as conn:
        yield conn


@asynccontextmanager
async def immediate_transaction(conn: aiosqlite.Connection) -> AsyncIterator[None]:
    """Run a block in a write transaction: commit on success, roll back on error."""
    # IMMEDIATE takes SQLite's write lock before we read anything, so a
    # check-then-insert cannot race another writer between the check and the
    # insert. Used by the seed loader and by booking creation.
    await conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        await conn.execute("ROLLBACK")
        raise
    else:
        await conn.execute("COMMIT")


async def list_ships(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    """Return all ships ordered by id."""
    async with conn.execute("SELECT id, name FROM ships ORDER BY id") as cur:
        return list(await cur.fetchall())


async def get_ship(conn: aiosqlite.Connection, ship_id: int) -> aiosqlite.Row | None:
    """Return one ship, or None if it does not exist."""
    async with conn.execute("SELECT id, name FROM ships WHERE id = ?", (ship_id,)) as cur:
        return await cur.fetchone()


async def bookings_between(
    conn: aiosqlite.Connection, ship_id: int, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """Return a ship's bookings overlapping the half-open window ``[start, end)``.

    Args:
        conn: Open connection.
        ship_id: The ship to look at.
        start: Aware window start.
        end: Aware window end.

    Returns:
        ``(start, end)`` pairs as aware UTC datetimes, in start order.
    """
    async with conn.execute(
        "SELECT start_time, end_time FROM bookings "
        "WHERE ship_id = ? AND start_time < ? AND end_time > ? ORDER BY start_time",
        (ship_id, to_db(end), to_db(start)),
    ) as cur:
        rows = await cur.fetchall()
    return [(datetime.fromisoformat(r["start_time"]), datetime.fromisoformat(r["end_time"])) for r in rows]


async def insert_booking(
    conn: aiosqlite.Connection, ship_id: int, pilot_name: str, start: datetime, end: datetime
) -> int:
    """Insert a booking and return its new id."""
    cur = await conn.execute(
        "INSERT INTO bookings (ship_id, pilot_name, start_time, end_time) VALUES (?, ?, ?, ?)",
        (ship_id, pilot_name, to_db(start), to_db(end)),
    )
    return cur.lastrowid
