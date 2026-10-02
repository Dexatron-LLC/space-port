"""CLI: load a seed file into the database, replacing existing data.

Usage: ``uv run python load_seed.py ../seed.json``
"""

import asyncio
import sys
from pathlib import Path

import db
import rules
from schemas import BookingCreate, CamelModel, Ship


class SeedFile(CamelModel):
    """The seed file: ships and bookings."""

    # Seed rows go through exactly the same validation as API input (aware
    # times, operating hours, pilot name).
    ships: list[Ship]
    bookings: list[BookingCreate]


async def load(path: Path) -> None:
    """Replace the database contents with the seed file's data.

    Args:
        path: Seed JSON file.

    Raises:
        pydantic.ValidationError: If the file is invalid; the database is
            left untouched.
    """
    # Validate before touching the database, so a bad file changes nothing.
    # utf-8-sig also accepts a byte-order mark.
    seed = SeedFile.model_validate_json(path.read_text(encoding="utf-8-sig"))
    async with db.connect() as conn:
        await conn.executescript("DROP TABLE IF EXISTS bookings; DROP TABLE IF EXISTS ships;" + db.SCHEMA)
        # One transaction: thousands of separate commits would be very slow.
        async with db.immediate_transaction(conn):
            await conn.executemany(
                "INSERT INTO ships (id, name) VALUES (?, ?)", [(s.id, s.name) for s in seed.ships]
            )
            for b in seed.bookings:
                await db.insert_booking(conn, b.ship_id, b.pilot_name, b.start_time, b.end_time)
    first = min(b.start_time for b in seed.bookings).astimezone(rules.TZ)
    last = max(b.end_time for b in seed.bookings).astimezone(rules.TZ)
    print(
        f"Loaded {len(seed.ships)} ships and {len(seed.bookings)} bookings, "
        f"{first:%Y-%m-%d} to {last:%Y-%m-%d} (Central)"
    )


def main() -> None:
    """Entry point: load the file named on the command line, or ../seed.json."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "seed.json"
    asyncio.run(load(path))


if __name__ == "__main__":
    main()
