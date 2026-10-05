"""Tests for the pure booking rules (rules.py). Plain synchronous pytest."""

from datetime import UTC, date, datetime, timedelta

import pytest

from rules import (
    BUFFER,
    CLOSE,
    OPEN,
    SLOT_STEP,
    TZ,
    day_slots,
    has_conflict,
    operating_window,
    within_operating_hours,
)


def ct(y, m, d, h, mi=0):
    """Build an aware Central Time datetime."""
    return datetime(y, m, d, h, mi, tzinfo=TZ)


def utc(y, m, d, h, mi=0):
    """Build an aware UTC datetime."""
    return datetime(y, m, d, h, mi, tzinfo=UTC)


@pytest.mark.parametrize(
    "day, expected_open, expected_close",
    [
        (date(2026, 10, 5), utc(2026, 10, 5, 11), utc(2026, 10, 6, 3)),
        (date(2026, 10, 31), utc(2026, 10, 31, 11), utc(2026, 11, 1, 3)),
        (date(2026, 11, 1), utc(2026, 11, 1, 12), utc(2026, 11, 2, 4)),
        (date(2027, 3, 13), utc(2027, 3, 13, 12), utc(2027, 3, 14, 4)),
        (date(2027, 3, 14), utc(2027, 3, 14, 11), utc(2027, 3, 15, 3)),
    ],
    ids=["cdt", "day-before-dst-end", "dst-ends", "day-before-dst-start", "dst-starts"],
)
def test_operating_window(day, expected_open, expected_close):
    open_utc, close_utc = operating_window(day)
    assert open_utc == expected_open
    assert close_utc == expected_close
    assert close_utc - open_utc == timedelta(hours=16)


D = (2026, 10, 5)


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (ct(*D, OPEN.hour), ct(*D, OPEN.hour + 1), True),
        (ct(*D, CLOSE.hour - 1), ct(*D, CLOSE.hour), True),
        (ct(*D, OPEN.hour), ct(*D, CLOSE.hour), True),
        (utc(2026, 10, 5, 11), utc(2026, 10, 5, 12), True),
        (ct(2026, 11, 1, OPEN.hour), ct(2026, 11, 1, OPEN.hour + 1), True),
        (utc(2026, 10, 6, 2), utc(2026, 10, 6, 3), True),
        (ct(*D, OPEN.hour - 1, 59), ct(*D, OPEN.hour + 1), False),
        (ct(*D, CLOSE.hour - 1), ct(*D, CLOSE.hour, 1), False),
        (ct(*D, CLOSE.hour - 1), ct(2026, 10, 6, 1), False),
        (ct(*D, 10), ct(*D, 10), False),
        (ct(*D, 11), ct(*D, 10), False),
    ],
    ids=[
        "open-hour", "ends-at-close", "full-day", "utc-input-equals-open",
        "dst-day", "utc-evening-crosses-utc-midnight", "starts-before-open", "ends-after-close", "spans-midnight",
        "zero-length", "end-before-start",
    ],
)
def test_within_operating_hours(start, end, expected):
    assert within_operating_hours(start, end) is expected


EXISTING = (ct(*D, 10), ct(*D, 12))
ONE_MIN = timedelta(minutes=1)
HOUR = timedelta(hours=1)


@pytest.mark.parametrize(
    "start, end, booked, expected",
    [
        (EXISTING[1] + BUFFER, EXISTING[1] + BUFFER + HOUR, [EXISTING], False),
        (EXISTING[0] - BUFFER - HOUR, EXISTING[0] - BUFFER, [EXISTING], False),
        (ct(*D, 10), ct(*D, 12), [], False),
        (EXISTING[1] + BUFFER - ONE_MIN, EXISTING[1] + BUFFER + HOUR, [EXISTING], True),
        (EXISTING[0] - BUFFER - HOUR, EXISTING[0] - BUFFER + ONE_MIN, [EXISTING], True),
        (ct(*D, 11), ct(*D, 13), [EXISTING], True),
        (EXISTING[1], EXISTING[1] + HOUR, [EXISTING], True),
        (ct(*D, 10, 30), ct(*D, 11, 30), [EXISTING], True),
        (ct(*D, 9), ct(*D, 13), [EXISTING], True),
    ],
    ids=[
        "exact-buffer-after", "exact-buffer-before", "empty-booked",
        "one-minute-inside-buffer-after", "one-minute-inside-buffer-before",
        "partial-overlap", "touching", "contained", "containing",
    ],
)
def test_has_conflict(start, end, booked, expected):
    assert has_conflict(start, end, booked) is expected


@pytest.mark.parametrize(
    "duration, open_count",
    [(timedelta(minutes=60), 31), (timedelta(minutes=30), 32), (timedelta(hours=16, minutes=30), 0)],
    ids=["60min", "30min", "longer-than-day"],
)
def test_day_slots_grid(duration, open_count):
    # Every start from 06:00 to 22:00 is listed whatever the duration; only
    # those that end by closing are available.
    slots = day_slots(date(2026, 10, 5), duration, [])
    assert len(slots) == 33
    assert sum(s[2] for s in slots) == open_count


def test_day_slots_grid_shape():
    day = date(2026, 10, 5)
    open_, close = operating_window(day)
    slots = day_slots(day, timedelta(minutes=60), [])
    assert slots[0][0] == open_
    assert slots[-1][0] == close
    starts = [s[0] for s in slots]
    assert all(b - a == SLOT_STEP for a, b in zip(starts, starts[1:]))
    # The last available slot ends exactly at closing; the ones after run past it.
    assert [s[2] for s in slots[-3:]] == [True, False, False]
    assert slots[-3][1] == close


def test_day_slots_marks_booking_and_buffer():
    day = date(2026, 10, 5)
    slots = day_slots(day, timedelta(minutes=60), [(ct(*D, 14), ct(*D, 16))])
    unavailable = [s[0] for s in slots if not s[2]]
    expected = [ct(*D, 13), ct(*D, 13, 30), ct(*D, 14), ct(*D, 14, 30),
                ct(*D, 15), ct(*D, 15, 30), ct(*D, 16),
                ct(*D, 21, 30), ct(*D, 22)]  # would end past closing
    assert unavailable == [e.astimezone(UTC) for e in expected]
    available = {s[0] for s in slots if s[2]}
    assert ct(*D, 12, 30).astimezone(UTC) in available
    assert ct(*D, 16, 30).astimezone(UTC) in available

    # An evening booking the previous day must not block the next morning.
    prev = [(ct(2026, 10, 4, 20), ct(2026, 10, 4, 22))]
    slots = day_slots(day, timedelta(minutes=60), prev)
    assert slots[0][0] == ct(*D, 6).astimezone(UTC)
    assert slots[0][2] is True


def test_day_slots_dst_day():
    slots = day_slots(date(2026, 11, 1), timedelta(minutes=60), [])
    assert slots[0][0] == utc(2026, 11, 1, 12)
