"""The collector contract.

A collector module holds two functions and some declarations. It holds no
rate limit, no try loop, no disk write and no database call. The runner owns
all of those. REFERENCE.md section 6.

    fetch(http, iso, start, end)   one HTTP request. It returns (status, bytes).
    parse(payload, iso, context)   it returns records.

Three guards live in `parse`:

1. The field set. A change in the field names stops the parse.
2. The range. An intensity outside 0 to 1500 g/kWh does not go in the store.
3. UTC only. The parser takes the UTC column, and it fails if that column
   is absent.

A fourth guard runs in every collector: one timestamp gives one value in one
payload. A publisher breaks that rule in two different ways, and the two need
different answers. Both were measured on 2026-09-18:

1. The same value two times. RTE labels the spring-forward hour with two local
   hours, 02:00 and 03:00, and both rows carry one UTC instant and equal
   numbers. That is one measurement written two times, so every collector keeps
   one copy and continues.
2. Two different values. NESO returned `2021-04-19T19:00Z` with actual 303 and
   actual 295 in one answer. No rule says which one is right, so the program
   stores neither, and it writes the reason in the run row.

`dedupe()` below finds the conflicting timestamps and writes the reason for
each one. The caller drops those timestamps, and it stops the payload when the
conflicts are more than 1 % of the timestamps, because that share is not an
accident.

⚠ Two collectors do not call `dedupe()`, and a reader must not assume that all
six answer a conflict in one way:

- `energy_charts_co2eq.py` keeps one copy of an equal repeat, and it stops the
  payload at the first conflict. It measures no share. The time column of that
  API is a UTC epoch, so the two local labels of a time change can not make a
  repeat there, and a conflict is a format fault.
- `energinet_eds.py` keys the rule on (timestamp, price area), because a
  country value needs a value from both areas of one stamp. That module holds
  its own copy of the rule.

⚠ Guard 2 drops the point, and it stops the whole payload only when more than
1 % of the points are outside the band. energy-charts published −2.6 gCO2eq/kWh
for Lithuania on 2026-09-17. One bad point must not lose a whole forecast
curve, because a curve that the program does not capture is lost for ever. A
unit error or a new factor table moves most of the points, and that still stops
the payload. Every dropped point goes in the run row.

The zero guard stands beside the four guards, and it is not one of them.
`zero_guard()` and `check_zero_share()` below hold it. A publisher can write
0.0 for a period that it did not compute. Guard 2 takes that number, because
`INTENSITY_MIN` is 0.0 and a true zero is possible for a different grid.

⚠ A zero is worse than a hole. A hole shows as "no record" on the portal. A
zero becomes the cleanest period of the day, and it moves the daily mean down.

⚠ The guard is not automatic, and a reader must not assume that all six
collectors call it. Each collector decides, because the answer belongs to the
publisher. Two publishers are measured, both in the gap report of 2026-09-23:

- Elia BE writes 0.0 in the evening peak. Production holds 335 such hours and
  consumption holds 377. `elia_opendata.py` holds its own copy of this rule,
  and it does not call the two functions below.
- NESO GB holds 6 records at 0.0 of 152,154. They are the six lowest values in
  the 6.59 million records of the store, and the next value up is 3.0.
  `neso_carbon_intensity.py` calls the two functions below.

`energy_charts_co2eq.py`, `energinet_eds.py` and `rte_eco2mix_odre.py` call
neither function. A query of 2026-09-23 found no 0.0 record from those three
sources, so no measurement asks for a guard there yet.

A caller gives the reason of its own publisher, and the reason goes in the run
row. One generic sentence for every source would lose the measurement that made
the rule, and the operator would read no reason for the absent period.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from ..model import ParseError, Record

# The share of zeros that stops a whole payload. Below it the program drops the
# zeros one by one, and the run row names them. Above it the publisher changed
# something, and one payload must not write that change into the store. The
# measured share of Elia across 2 years is 2.1 %, and of NESO 6 in 152,154.
ZERO_SHARE_LIMIT = 0.5


@dataclass(slots=True)
class ParseContext:
    """What the runner gives the parser beside the payload.

    `dropped` goes the other way. A parser appends one line for each point that
    it refused. The runner writes those lines into the run row, and the run
    keeps the status `ok`. A point that the store does not hold must never be
    invisible.
    """

    kind: str  # actual | forecast
    collected_at: datetime
    raw_ref: str
    run_at: datetime | None = None
    dropped: list = field(default_factory=list)


class Collector(Protocol):
    source_id: str
    metric: str
    unit: str

    # The first day that the source serves.
    available_from: date

    # The largest window of one request, in days.
    max_span_days: int

    # A status code that means "this source has no data for this window".
    # The runner writes an `empty` row and does not try again.
    empty_http_status: tuple[int, ...]

    # True when the source publishes a forward curve for `atlas snap`.
    has_forecast_curve: bool

    def countries(self) -> list[str]:
        """The ISO codes that this collector covers, from the registers."""

    def fetch(
        self, http, iso: str, start: date, end: date, tries: int | None = None
    ) -> tuple[int, bytes]:
        """One request. It returns (http status, the bytes).

        `tries` makes the try count smaller for this call. The runner sets it
        to 1 for a window that it can split.
        """

    def parse(self, payload: bytes, iso: str, context: ParseContext) -> list[Record]:
        """The records in the payload."""


def field_hash(names) -> str:
    """A short hash of a field-name set. Guard 1 compares this."""
    joined = "|".join(sorted(names))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def dedupe(pairs, context, name: str = "") -> set:
    """Guard 4. It returns the timestamps that no record may use.

    `pairs` is a list of (timestamp, value). A timestamp that carries one value
    two times is one measurement written two times, and it stays. A timestamp
    that carries two different values is a conflict, and it goes. Every drop
    goes in the run row. The caller raises when the share of conflicts is too
    large for an accident.

    A null is an absence and not a value, so a pair with a null makes no
    conflict. NESO, RTE and Elia all publish a null in that column in normal
    operation, and each collector skips its own nulls after this guard.
    """
    values: dict = {}
    for stamp, value in pairs:
        if stamp is None or value is None:
            continue
        values.setdefault(stamp, set()).add(value)

    conflict = set()
    for stamp, found in sorted(values.items()):
        if len(found) > 1:
            conflict.add(stamp)
            context.dropped.append(
                f"{name}{stamp} carries {sorted(found)} in one answer. No rule "
                f"chooses one, so the program stores none of them."
            )
    return conflict


def zero_guard(number: float, ts_utc, context, label: str, reason: str) -> bool:
    """The zero guard. True when the caller must drop this point.

    `label` names the column or the series that holds the 0.0. `reason` is the
    sentence of that publisher, and it states why the zero is not a
    measurement. The two make one line in `context.dropped`, and the runner
    writes that line in the run row with the status `ok`. So the operator sees
    every period that the guard refused.

    ⚠ The caller counts the drops and calls `check_zero_share()` after the
    loop. This function drops one point, and it stops no payload.
    """
    if number != 0.0:
        return False
    context.dropped.append(f"{label} is 0.0 at {ts_utc.isoformat()}. {reason}")
    return True


def check_zero_share(
    iso: str, zeros: int, offered: int, measured: str, limit: float = ZERO_SHARE_LIMIT
) -> None:
    """It raises when the payload holds more zeros than a known defect gives.

    A few zeros are the measured defect of the publisher, and `zero_guard()`
    drops them one by one. A payload that is mostly zeros is a different event,
    and the program must not write it into the store. `measured` states the
    share that the source normally shows, so the message tells the operator
    what changed.
    """
    if offered and zeros > offered * limit:
        raise ParseError(
            f"{iso}: {zeros} of {offered} values are 0.0, which is more than "
            f"{limit:.0%}. {measured} Check the dataset at the publisher."
        )
