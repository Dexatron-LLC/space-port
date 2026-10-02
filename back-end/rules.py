"""Pure booking rules for the Spaceport Charter System.

This is the single implementation of the rules, used by BOTH the availability
endpoint and booking creation, so the UI can never offer a slot the server
would reject. Standard library only: no I/O, no framework imports.

Rules:
    * No overlapping bookings for the same ship.
    * Consecutive bookings on one ship are separated by at least BUFFER
      (exactly BUFFER is allowed).
    * A booking must fall entirely within 06:00-22:00 Central Time, every day.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")   # the spaceport's local time zone (DST-aware)
OPEN = time(6, 0)                  # opening time, Central wall clock
CLOSE = time(22, 0)                # closing time, Central wall clock
BUFFER = timedelta(minutes=30)     # minimum refuelling gap between bookings on one ship
SLOT_STEP = timedelta(minutes=30)  # spacing of offered start times


def operating_window(day: date) -> tuple[datetime, datetime]:
    """Return the spaceport's opening and closing instants for a Central day.

    Args:
        day: The calendar day, interpreted in Central Time.

    Returns:
        ``(open_utc, close_utc)`` as aware UTC datetimes.
    """
    # Build the Central wall-clock times, then convert to UTC immediately.
    # zoneinfo picks the right offset for that date (CDT -05:00 / CST -06:00),
    # and once in UTC all arithmetic and comparisons are absolute. (Python does
    # wall-clock arithmetic between datetimes sharing a tzinfo and ignores
    # `fold` when comparing them, which is wrong around DST changes.)
    # DST changes happen at 02:00 local, outside opening hours, so every
    # operating day is exactly 16 hours.
    open_utc = datetime.combine(day, OPEN, tzinfo=TZ).astimezone(UTC)
    close_utc = datetime.combine(day, CLOSE, tzinfo=TZ).astimezone(UTC)
    return open_utc, close_utc


def within_operating_hours(start: datetime, end: datetime) -> bool:
    """Check that a booking lies entirely inside one Central operating day.

    Args:
        start: Aware booking start, in any time zone.
        end: Aware booking end, in any time zone.

    Returns:
        True if ``start < end`` and both fall within the window of the Central
        day on which the booking starts.
    """
    day = start.astimezone(TZ).date()
    open_utc, close_utc = operating_window(day)
    # `end` is checked against the same Central day's close, so a booking
    # cannot span days. Ending exactly at 22:00 is allowed even though its
    # refuel buffer runs past closing: the rule constrains bookings, not
    # refuelling (and the provided seed data has such rows).
    return open_utc <= start < end <= close_utc


def has_conflict(
    start: datetime,
    end: datetime,
    booked: Iterable[tuple[datetime, datetime]],
) -> bool:
    """Check a proposed booking against a ship's existing bookings.

    Args:
        start: Aware proposed start.
        end: Aware proposed end.
        booked: The ship's existing ``(start, end)`` bookings.

    Returns:
        True if the proposal overlaps an existing booking or leaves less than
        BUFFER between them on either side.
    """
    # Padding each booking's end by the buffer turns "no overlap AND at least a
    # 30-minute gap" into one half-open interval-overlap test. It covers
    # overlap, touching, and the buffer on both sides. A gap of exactly BUFFER
    # is allowed because the comparisons are strict (<).
    return any(
        start < booked_end + BUFFER and booked_start < end + BUFFER
        for booked_start, booked_end in booked
    )


def day_slots(
    day: date,
    duration: timedelta,
    booked: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime, bool]]:
    """List every candidate slot of a given length on a Central day.

    Args:
        day: The calendar day, interpreted in Central Time.
        duration: Length of the charter.
        booked: The ship's existing ``(start, end)`` bookings.

    Returns:
        ``(start, end, available)`` tuples in UTC, in start order, stepping by
        SLOT_STEP from opening while the slot still ends by closing. Empty if
        the duration does not fit in the day.
    """
    booked = list(booked)  # iterated once per slot, so materialise it
    open_, close = operating_window(day)
    slots = []
    start = open_
    while start + duration <= close:
        end = start + duration
        slots.append((start, end, not has_conflict(start, end, booked)))
        start += SLOT_STEP
    return slots
