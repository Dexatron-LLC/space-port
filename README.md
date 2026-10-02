# Spaceport Charter System

This is my submission for the Spaceport Charter System take-home. The original brief is in
[`ASSIGNMENT.md`](ASSIGNMENT.md). It is a FastAPI + SQLite back end and a React + TypeScript
front end with the two screens the brief asks for: **Charter a Ship** (pick a ship, date and
duration, see which start times are unavailable, book one) and the **Fleet Dashboard** (every
booking, grouped by ship). The server enforces every booking rule. The browser has no booking-rule
logic of its own.

## Quick start

Prerequisites:

- Python 3.11 or newer (the back-end tests pass on 3.11 and 3.13)
- [uv](https://docs.astral.sh/uv/) (`pip install uv` if you don't have it)
- Node 20.19+ or 22.12+, which Vite 8 requires (I used Node 24)

From the repo root:

```bash
python seed.py > seed.json
cd back-end
uv sync
uv run python load_seed.py ../seed.json
uv run uvicorn main:app --reload --port 8000

# second terminal, from the repo root
cd front-end
npm install
npm run dev        # open http://localhost:5173
```

- The loader prints what it loaded, e.g. `Loaded 5 ships and 3000 bookings, 2025-10-02 to 2026-06-06 (Central)`.
  It replaces the contents of `back-end/spaceport.db`, so you can re-run it at any time to reset the data.
- FastAPI serves interactive API docs at <http://127.0.0.1:8000/docs>.
- The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so the back end has to run on port 8000.

**Windows:** in Windows PowerShell 5.1, `>` writes UTF-16. Use
`python seed.py | Out-File -Encoding utf8 seed.json` instead. That writes a UTF-8 byte-order mark,
which the loader accepts. If `python seed.py` fails with `ZoneInfoNotFoundError`, your Python has no
time-zone database, so run `pip install tzdata` first. The back end already depends on `tzdata`.

## Project structure

```text
ASSIGNMENT.md            the original brief, unchanged
seed.py                  the provided seed generator, unchanged
back-end/
  rules.py               the booking rules: pure functions, standard library only
  schemas.py             Pydantic models: the JSON contract and stateless validation
  db.py                  SQLite schema and the API's queries (raw aiosqlite, no ORM)
  main.py                FastAPI app: the four endpoints
  load_seed.py           CLI that validates a seed file and loads it into SQLite
  tests/test_rules.py    unit tests for rules.py
  tests/test_api.py      API tests against a fresh temp database per test
front-end/
  vite.config.ts         React plugin and the /api proxy
  src/main.tsx           entry point
  src/App.tsx            header, tab navigation, current screen
  src/CharterScreen.tsx  the Charter a Ship screen
  src/FleetScreen.tsx    the Fleet Dashboard screen
  src/api.ts             typed API client (the only file that calls fetch)
  src/time.ts            Central Time display helpers (the only file that names the zone)
  src/index.css          global styles and design tokens
```

## Seed data

- I use `seed.py` unchanged. It generates 600 bookings per ship (3,000 in total), starting 365 days
  before the day you run it. All start and end times fall on the hour or half hour, between 06:00 and
  22:00 Central, with at least the 30-minute refuel gap between bookings.
- The dates are relative to the run day, so the loader prints the range it loaded. A seed generated on
  2026-10-02 runs from 2025-10-02 to 2026-06-06.
- **The provided seed contains no future bookings.** Each ship hits its 600 bookings about 8 months
  into the "year". The Charter screen opens on today's date, which is after the last seeded booking.
  To see real unavailable slots, pick a date inside the range the loader printed. Later dates stay
  empty until you book them.
- I loaded the seed as-is and did not alter the provided data to add future bookings.
- The loader validates every seed row with the same Pydantic model (`BookingCreate`) that validates
  `POST /api/bookings`: timestamps must have an offset, end must be after start, the booking must fall
  within operating hours, and the pilot name must be 1 to 100 characters after trimming. If any row
  fails, the loader raises before touching the database. It does not check seed bookings against
  each other for conflicts. The generator already spaces them at least 30 minutes apart.

## API

All JSON is camelCase. Times are ISO-8601. Responses always use Central Time with that date's offset
(`-05:00` in CDT, `-06:00` in CST). Requests can use any offset, including `Z`, but must include one.
The examples come from `back-end/tests/test_api.py`. Its fixture seeds three ships and gives Nostromo
(id 2) a booking on 2026-10-05 from 14:00 to 16:00.

| Endpoint | Returns | Status codes |
|---|---|---|
| `GET /api/ships` | all ships, by id | 200 |
| `GET /api/ships/{id}/availability?date=YYYY-MM-DD&durationMinutes=N` | every candidate start time that Central day, each flagged available or not | 200, 404 unknown ship, 422 bad or missing parameters |
| `POST /api/bookings` | the created booking | 201, 404, 409, 422 |
| `GET /api/fleet` | every ship with all of its bookings, newest first | 200 |

### `GET /api/ships`

```json
[{"id": 1, "name": "USS Wanderer"}, {"id": 2, "name": "Nostromo"}, {"id": 3, "name": "Serenity"}]
```

### `GET /api/ships/{id}/availability`

`GET /api/ships/2/availability?date=2026-10-05&durationMinutes=60` returns 31 slots, one every
30 minutes from 06:00, and stops at the last slot that ends by 22:00. `durationMinutes` must be
between 1 and 1440. Excerpt:

```json
[
  {"start": "2026-10-05T06:00:00-05:00", "end": "2026-10-05T07:00:00-05:00", "available": true},
  {"start": "2026-10-05T06:30:00-05:00", "end": "2026-10-05T07:30:00-05:00", "available": true},
  ...
  {"start": "2026-10-05T12:30:00-05:00", "end": "2026-10-05T13:30:00-05:00", "available": true},
  {"start": "2026-10-05T13:00:00-05:00", "end": "2026-10-05T14:00:00-05:00", "available": false},
  ...
]
```

The starts from 13:00 through 16:00 are unavailable because each would overlap the 14:00–16:00 booking
or leave less than 30 minutes before or after it. The 12:30 and 16:30 starts leave exactly 30 minutes,
so they are available. Unavailable slots are included in the response so the screen can show them.

### `POST /api/bookings`

```json
{"shipId": 2, "pilotName": "Ellen Ripley", "startTime": "2026-10-05T18:00:00-05:00", "endTime": "2026-10-05T19:00:00-05:00"}
```

returns `201` with the stored booking:

```json
{"id": 4, "shipId": 2, "pilotName": "Ellen Ripley", "startTime": "2026-10-05T18:00:00-05:00", "endTime": "2026-10-05T19:00:00-05:00"}
```

| Status | Meaning | Example |
|---|---|---|
| 201 | Booked. | above |
| 422 | The request is invalid regardless of what is stored: a missing field, a timestamp without an offset, an end that is not after the start, a booking outside 06:00–22:00 Central or across midnight, or a pilot name that is blank after trimming or longer than 100 characters. Pydantic rejects these before the endpoint code runs. | 21:30–22:30 gives `{"detail": [{"type": "value_error", "loc": ["body"], "msg": "Value error, Bookings must start and end between 06:00 and 22:00 Central Time on the same day", ...}]}` |
| 404 | `shipId` does not exist. | `{"detail": "Ship 99 not found"}` |
| 409 | The request is valid but conflicts with the ship's existing bookings: it overlaps one or falls inside its 30-minute refuel buffer. | 15:00–17:00 gives `{"detail": "Nostromo is not available then: it overlaps another booking or its 30-minute refuel buffer."}` |

The checks run in that order: 422, then 404, then 409. The API does not require a start on the
30-minute grid. Any start and end that pass the rules are accepted.

### `GET /api/fleet`

```json
[
  {"id": 1, "name": "USS Wanderer", "bookings": [
    {"id": 3, "shipId": 1, "pilotName": "Leia Organa", "startTime": "2026-10-05T08:00:00-05:00", "endTime": "2026-10-05T09:00:00-05:00"},
    {"id": 2, "shipId": 1, "pilotName": "Han Solo", "startTime": "2026-10-04T08:00:00-05:00", "endTime": "2026-10-04T09:00:00-05:00"}
  ]},
  {"id": 2, "name": "Nostromo", "bookings": [
    {"id": 1, "shipId": 2, "pilotName": "Ellen Ripley", "startTime": "2026-10-05T14:00:00-05:00", "endTime": "2026-10-05T16:00:00-05:00"}
  ]},
  {"id": 3, "name": "Serenity", "bookings": []}
]
```

Ships with no bookings are included with an empty list.

## How the rules are enforced

**One rules module.** `back-end/rules.py` holds the rules as pure functions with no I/O or framework
imports. The availability endpoint uses `day_slots`, and booking creation uses `has_conflict` and
`within_operating_hours` (through the Pydantic validator). Both endpoints call the same conflict test,
so the UI can never offer a slot that the server would reject. The one exception is someone else
booking it first, in which case the POST returns 409 and the screen refreshes the slots.

**One inequality for overlap and the refuel buffer.** A proposed booking conflicts with an existing
one when

```python
start < booked_end + BUFFER and booked_start < end + BUFFER
```

Padding each booking's end by `BUFFER` (30 minutes) turns "no overlap, and at least 30 minutes between
bookings" into a single interval-overlap test. That test covers partial overlap, containment, touching,
and a short gap on either side. The comparisons are strict, so two bookings exactly 30 minutes apart are
allowed. The tests cover that boundary and one minute inside it, on both sides.

**Operating hours per Central calendar day.** `operating_window(day)` builds 06:00 and 22:00 as Central
wall-clock times for that date with `zoneinfo` (`America/Chicago`) and converts them to UTC
immediately. All comparisons are in UTC. This makes the window correct on DST days: on 2026-11-01 the
spaceport opens at 12:00Z, and on the day before it opens at 11:00Z. DST switches happen at 02:00,
outside opening hours, so every operating day is 16 hours. A booking is checked against the window of
the Central day it starts on, so it cannot run past midnight. A booking may end exactly at 22:00 even
though its refuel buffer runs past closing. The rule limits bookings, not refuelling, and the seed
contains such bookings.

**Storage.** SQLite has no time-zone type, so times are stored as fixed-width UTC text
(`2026-10-05T19:00:00.000000+00:00`). Text order then equals time order, and there is an index on
`(ship_id, start_time)`. The seed's raw strings mix `-05:00` and `-06:00` offsets and would not sort
correctly as text. The availability endpoint and POST load only the bookings within one buffer of the
day or the request.

**Concurrency.** `POST /api/bookings` runs the conflict check and the insert inside `BEGIN IMMEDIATE`.
That statement takes SQLite's write lock *before* the check. A second request for the same slot waits
for the lock (the sqlite3 busy timeout, 5 s by default), then sees the first booking and gets a 409.
`test_concurrent_bookings_cannot_double_book` sends two identical requests at once and expects exactly
one 201 and one 409. To see it live, run this in bash while the back end is running. It sends five
identical POSTs at once for 2027-01-15, a future date with no seed bookings:

```bash
seq 5 | xargs -P5 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d '{"shipId":2,"pilotName":"Race","startTime":"2027-01-15T10:00:00-06:00","endTime":"2027-01-15T11:00:00-06:00"}' \
  http://127.0.0.1:8000/api/bookings | sort | uniq -c
```

It counts one 201 and four 409s. Running it again gives five 409s, because the slot is now taken.
Double-booking is always caught. If a request ever waited longer than the 5-second timeout, it would
fail with a 500 rather than book.

## Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| FastAPI + Pydantic v2 | Typed models give validation and OpenAPI docs with little code. What Pydantic does here: `CamelModel` keeps Python snake_case and JSON camelCase. `AwareDatetime` rejects timestamps without an offset. The `check_times` validator on `BookingCreate` serves both the API and the seed loader. `CentralTime` converts every outgoing time to Central. | Validation errors use FastAPI's default 422 format, which is verbose. |
| SQLite + raw `aiosqlite`, no ORM | Nothing to set up (the database is one file), and every query is easy to read. `db.py` has five queries plus the schema, and the loader adds its table drops and a ships insert. | One writer at a time. No time-zone type, so I store UTC text. No migrations. |
| Slots computed on the server | The brief requires it. Availability returns every candidate start with an `available` flag. The client has no booking-rule logic and posts the chosen slot's own `start`/`end` strings back unchanged, so it never builds a timestamp. | One request each time the ship, date or duration changes. |
| 30-minute start grid plus a duration (30 min to 4 h in the UI) | It matches the seed, where every time is on the hour or half hour. POST does not require grid alignment because the rules work on continuous time. | The UI offers no free-form start times. |
| Any date is bookable, including past dates | The brief doesn't forbid past dates. Blocking them would be one more 422 check. | You can book yesterday. |
| React + TypeScript + plain CSS, no router or state library | There are only two screens, and one `useState` picks the tab. | No deep links to a screen. |
| Vite dev proxy instead of CORS | The browser only calls same-origin `/api/...`, so the API needs no CORS setup. | A deployment would need the same-origin setup, or CORS added. |
| UI designed before building | The screens were designed first in Claude Design, and I approved the mockups before any front-end code was written. The components follow those artboards. | More time up front. |
| Dashboard shows all bookings per ship, newest first, no pagination | About 3,000 rows is small. Each ship is a collapsible section with a scrolling table. | The payload grows with every booking. A date filter and pagination are next (below). |

## Testing

```bash
cd back-end
uv run pytest
```

51 tests:

- `tests/test_rules.py` covers the pure rules: the operating window on ordinary days and on both 2026–27
  DST change days (and the days before them), operating-hours edge cases (exactly at open and close, a
  UTC evening time that crosses UTC midnight, spanning midnight, zero length), conflicts including the
  exact-30-minute boundary and one minute inside it on each side, and the shape of the slot grid.
- `tests/test_api.py` runs each test against a fresh SQLite file loaded through the real loader. It
  covers the API contract and JSON shapes, 404/409/422 cases, two concurrent POSTs for the same slot
  (one 201, one 409), the fleet's grouping and newest-first order including a ship with no bookings,
  and the loader rejecting an out-of-hours seed row.

```bash
cd front-end
npm run build      # tsc type-check, then Vite production build
npm run lint       # oxlint
```

The front end has no unit tests. Instead I drove the running app in Chrome: a booked slot and its 30-minute
buffer became unavailable, an exactly-30-minute gap was accepted, the 409 banner showed, the 2026-11-01
(DST) grid started at 6:00 AM CST, the dashboard showed new bookings newest first, the Charter screen never
requested `/api/fleet`, and the console had no errors. A fresh clone built and tested green. No automated E2E suite yet.

## What I'd do next

- Block bookings in the past (a 422 in the same validator).
- Cancel and edit bookings.
- Add a date filter and pagination to the dashboard, with upcoming and past bookings separated.
- Move to Postgres and let the database enforce no-overlap-plus-buffer itself with an exclusion
  constraint. As I understand it, that would need the `btree_gist` extension (to combine
  `ship_id WITH =` with range overlap). The buffer also has to go into the range, and
  `timestamptz + interval` isn't immutable, so it can't be used directly in the constraint. One way
  is a stored `ready_at = end + buffer` column. Another is to store UTC `timestamp` values, where
  `+ interval` is immutable and can go straight into the range expression. I haven't built or tested
  this.
- A migration tool instead of `CREATE TABLE IF NOT EXISTS` (e.g. Alembic, alongside the Postgres move).
- CI that runs `pytest`, the front-end build and the linter.
- Playwright end-to-end tests for the booking flow.
- Show *why* a slot is unavailable: booked, or inside a refuel buffer.
- An idempotency key on `POST /api/bookings`, so a retry after a network error can't book twice.
- One-command start: serve the built front end from FastAPI, or use docker compose.
- Make the seed loader's drop-and-recreate atomic. Today it recreates the tables before its insert
  transaction. A seed that passes validation but fails a foreign key would leave an empty database.

## AI usage

The brief says AI tools are permitted and expected. I built this with Claude Code (Anthropic) as an AI
pair programmer. I made the product and design decisions: the deliberately small scope, the booking UX
(a start slot plus a duration), loading the seed as-is, and approving the UI mockup before it was
built. The AI drafted code against a written plan, one task at a time. The back-end tasks each came
with their own tests. Every task was reviewed separately against its brief, with the front end checked
by build, lint and an end-to-end run in a real browser. I reviewed the results. I can walk through and
justify every line.
