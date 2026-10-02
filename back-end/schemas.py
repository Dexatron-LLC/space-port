"""Pydantic models: the API contract for the Spaceport Charter System.

JSON uses camelCase (as in the assignment's data model); Python uses snake_case.
"""

from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel

import rules


class CamelModel(BaseModel):
    """Base model: snake_case in Python, camelCase in JSON."""

    # Python stays snake_case while JSON is camelCase like the assignment's
    # data model; validate_by_name lets us also build models from snake_case
    # DB rows and keyword arguments.
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True)


def _to_central(dt: datetime) -> datetime:
    """Convert an aware datetime to the spaceport's Central Time zone."""
    # Times are stored and computed in UTC; they are only shown in Central
    # (with the right -05:00/-06:00 offset for that date) at the API edge.
    return dt.astimezone(rules.TZ)


CentralTime = Annotated[AwareDatetime, AfterValidator(_to_central)]
PilotName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Ship(CamelModel):
    """A charterable ship."""

    id: int
    name: str


class BookingCreate(CamelModel):
    """A request to book a ship; also the shape of each seed-file booking."""

    ship_id: int
    pilot_name: PilotName
    # AwareDatetime rejects timestamps without an offset: a naive time would
    # be ambiguous (which zone?) and could silently shift a booking by hours.
    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def check_times(self) -> Self:
        """Check the stateless time rules (reported as HTTP 422).

        Conflicts with existing bookings depend on stored state and are
        checked separately (HTTP 409).

        Raises:
            ValueError: If the end is not after the start, or the booking is
                outside operating hours.
        """
        if self.end_time <= self.start_time:
            raise ValueError("endTime must be after startTime")
        if not rules.within_operating_hours(self.start_time, self.end_time):
            raise ValueError(
                f"Bookings must start and end between {rules.OPEN:%H:%M} and "
                f"{rules.CLOSE:%H:%M} Central Time on the same day"
            )
        return self


class Slot(CamelModel):
    """One candidate start time for a charter, and whether it can be booked."""

    start: CentralTime
    end: CentralTime
    available: bool
