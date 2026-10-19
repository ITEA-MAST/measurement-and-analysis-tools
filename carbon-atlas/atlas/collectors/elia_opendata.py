"""Elia Open Data — Belgium. Two accounting bases from one publisher.

Register entries: `elia-co2-production` and `elia-co2-consumption` in
`sources/sources.json`.

    GET /ods192/exports/json?where=...&select=datetime,production,consumption

One dataset holds two series. The publisher writes, in the field annotations
read on 2026-09-18:

    production    "the amount of carbon dioxide equivalents emitted per unit of
                   generated electricity ... Cross-border flows are not taken
                   into account"                          unit gCO2eq/kWh
    consumption   "the amount of carbon dioxide equivalents emitted per unit of
                   consumed electricity ... Cross-border flows are taken into
                   account"                               unit gCO2eq/kWh

This is the only source in the register that publishes both bases. One
country, one hour, one unit, one factor table, one publisher. The difference
between the two columns is the accounting basis and nothing else. Every other
pair in the store moves the basis, the scope and the factor table together, so
no other pair can separate them.

⚠ The two columns are two sources, and not two columns of one source. The
key of the record table is (country, source_id, metric, fuel, ts_utc, kind,
run_at), and `basis` is not in that key. Two values of one hour under one
source id collide, and the second one writes a revision of the first. A
revision means "the publisher corrected the number", which is false here. So
each column gets its own source id, its own register entry and its own request.
The portal then shows them as two sources, and it never averages them.

⚠ A value of exactly 0.0 is an outage, and not a clean hour. MEASURED
2026-09-18 across the whole series of 15,279 hours:

- 326 rows carry 0.0 in one column or both. 284 carry 0.0 in `production`.
- The zeros come in blocks, and the blocks repeat at 18:00 to 21:00 UTC on
  days that follow each other. That is the evening peak, when Belgium burns
  the most gas.
- energy-charts reports a mean of 218.5 gCO2eq/kWh for those same 284 hours,
  and it never reports below 82.4. The mean of energy-charts across the whole
  period is 203.9, so the zero hours are dirtier than the mean.
- The smallest value that Elia publishes above zero is 17.4 gCO2eq/kWh.

A zero therefore marks an hour that the publisher did not compute. It does not
mark a grid with no emissions. Guard 2 accepts it, because `INTENSITY_MIN` is
0.0 and a true zero is possible for a different country. So this collector
drops a zero and writes the reason in the run row.

⚠ The zero is worse than a gap. A gap shows as "no record" on the portal.
A zero becomes the cleanest hour of the day, in the hours when the grid is
dirtiest. It moves the daily mean down, and it moves the answer of the
workload calculator to the wrong hour.

⚠ The series has holes. MEASURED 2026-09-18: 15,279 hours of the 17,204
between the first and the last record. The largest hole runs from
2025-12-10T18:00Z to 2026-02-18T23:00Z, which is 70 days. A second hole runs
10 days from 2025-10-30. The run table records those days as `empty`, and the
portal shows "no record".

⚠ The history is short. The first record is 2024-09-30T22:00Z. This source
gives 2 years, and energy-charts gives 11. A comparison of the two must use the
period that both hold.

The dataset `ods191` carries the same title, 0 records and no declared fields.
Probed 2026-09-18. So this collector uses `ods192`, which holds the records and
reaches the hour before the day of the fetch.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from .. import config
from ..model import ParseError, Record
from .base import ParseContext, dedupe, field_hash

PRODUCTION_ID = "elia-co2-production"
CONSUMPTION_ID = "elia-co2-consumption"

DATASET = "ods192"

# The fields this collector asks for. OpenDataSoft answers HTTP 400 for a field
# that does not exist, so a renamed field stops the fetch and not the parse.
SELECT = ("datetime", "production", "consumption")

# Guard 1: the field set of one row.
EXPECTED_FIELD_HASH = field_hash(SELECT)

# Guard 3: the time column. The platform gives it with an explicit UTC offset.
TIME_FIELD = "datetime"

# A payload with more zeros than this share is not an outage of a working
# series. It is a change at the publisher, and it stops the parse. The measured
# share across 2 years is 2.1 %.
ZERO_SHARE_LIMIT = 0.5


class EliaCo2:
    """One column of `ods192`. Two objects of this class serve two source ids."""

    metric = "intensity"

    # The publisher states the unit in the field annotation of each column.
    unit = "gCO2eq/kWh"

    # Probe of 2026-09-18: the oldest record is 2024-09-30T22:00Z.
    available_from = date(2024, 9, 30)

    # Measured on 2026-09-18: the whole series of 15,279 rows is 1.3 MB and one
    # request. A window of 400 days keeps a backfill at 2 requests.
    max_span_days = 400

    empty_http_status = ()
    has_forecast_curve = False

    def __init__(self, source_id: str, column: str) -> None:
        self.source_id = source_id
        self.column = column
        entry = config.source(source_id)
        self.base = entry["api_base"]
        method = entry.get("methodology", {})
        self.basis = method.get("basis")
        self.scope = method.get("scope")

    def countries(self) -> list[str]:
        zones = set(config.source(self.source_id).get("coverage", {}).get("zones", []))
        return [c["iso"] for c in config.countries() if c["iso"] in zones]

    def fetch(
        self, http, iso: str, start: date, end: date, tries: int | None = None
    ) -> tuple[int, bytes]:
        """One request. It returns the answer of the platform, unchanged.

        Each source id makes its own request, so the raw file of each one holds
        the evidence of its own number. The two files hold the same bytes, and
        the cost of that copy is 1.3 MB for the whole history.
        """
        stop = end + timedelta(days=1)
        where = (
            f"{TIME_FIELD} >= date'{start.isoformat()}' and "
            f"{TIME_FIELD} < date'{stop.isoformat()}'"
        )
        params = {"where": where, "select": ",".join(SELECT), "order_by": TIME_FIELD}
        return http.get(
            self.source_id, f"{self.base}/{DATASET}/exports/json", params, tries=tries
        )

    def parse(self, payload: bytes, iso: str, context: ParseContext) -> list[Record]:
        if context.kind != "actual":
            return []  # This source publishes no forecast. FORECASTS.md.

        try:
            rows = json.loads(payload)
        except ValueError as error:
            raise ParseError(f"the payload is not JSON: {error}") from None
        if not isinstance(rows, list):
            raise ParseError(
                f"the answer is a {type(rows).__name__}, not a list. {str(rows)[:200]}"
            )

        # Guard 4. The platform gives an explicit offset, so the two local
        # labels of the autumn time change give two different UTC instants. No
        # duplicate was measured across the 15,279 rows of 2026-09-18. The
        # guard stays, because a publisher can change the column at any time.
        pairs = [
            (r.get(TIME_FIELD), r.get(self.column)) for r in rows if isinstance(r, dict)
        ]
        conflict = dedupe(pairs, context, name=f"{DATASET}: ")
        if conflict and len(conflict) > max(1, len(pairs) * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{len(conflict)} timestamps carry two different values. That is not "
                f"the time change. Check the API."
            )

        records: list[Record] = []
        seen: set[datetime] = set()
        offered = 0
        zeros = 0
        absurd = 0

        for row in rows:
            if not isinstance(row, dict):
                raise ParseError(f"a row is a {type(row).__name__}, not an object")

            # Guard 1: the field set.
            if field_hash(row.keys()) != EXPECTED_FIELD_HASH:
                raise ParseError(
                    f"the field set changed. Expected {sorted(SELECT)}, got "
                    f"{sorted(row)}. Check the API, then update the collector."
                )

            if row.get(TIME_FIELD) in conflict:
                continue  # Guard 4. The reason is already in `dropped`.

            value = row.get(self.column)
            if value is None:
                continue  # The publisher gives no value for this hour.
            offered += 1

            # Guard 3: the UTC column.
            stamp = row.get(TIME_FIELD)
            if not isinstance(stamp, str):
                raise ParseError(f"`{TIME_FIELD}` is {stamp!r}, and not a string")
            try:
                moment = datetime.fromisoformat(stamp)
            except ValueError:
                raise ParseError(f"`{TIME_FIELD}` is {stamp!r}") from None
            if moment.utcoffset() is None:
                raise ParseError(
                    f"`{TIME_FIELD}` {stamp!r} carries no offset, so the time base is "
                    f"not known"
                )
            ts_utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
            number = float(value)

            # ⚠ The zero guard. The docstring of this module holds the
            # measurement that made it. A zero is an hour that the publisher
            # did not compute, and Guard 2 accepts it.
            if number == 0.0:
                zeros += 1
                context.dropped.append(
                    f"{self.column} is 0.0 at {ts_utc.isoformat()}. This publisher "
                    f"writes 0.0 for an hour that it did not compute, so the hour "
                    f"gets no record."
                )
                continue

            # Guard 2, band 1: the store band.
            if not (config.INTENSITY_MIN <= number <= config.INTENSITY_MAX):
                context.dropped.append(
                    f"{value} {self.unit} at {ts_utc.isoformat()} is outside "
                    f"{config.INTENSITY_MIN} to {config.INTENSITY_MAX}"
                )
                if not (
                    config.INTENSITY_ABSURD_LOW <= number <= config.INTENSITY_ABSURD_HIGH
                ):
                    absurd += 1
                continue

            # Guard 4, the equal repeat. `dedupe` above names the conflicts
            # only, so one instant that carries one value two times arrives
            # here two times. One copy stays, which is the answer of `base.py`.
            # The store holds no key that stops the second copy, so this guard
            # is the only one. The key is the UTC instant and not the text,
            # because two spellings of one instant are one record.
            if ts_utc in seen:
                continue
            seen.add(ts_utc)

            records.append(
                Record(
                    country=iso,
                    source_id=self.source_id,
                    metric=self.metric,
                    ts_utc=ts_utc,
                    value=number,
                    unit=self.unit,
                    granularity="native",
                    kind="actual",
                    basis=self.basis,
                    scope=self.scope,
                    collected_at=context.collected_at,
                    raw_ref=context.raw_ref,
                )
            )

        # A few zeros are the known defect, and the program drops them one by
        # one. A payload that is mostly zeros is a different thing, and it
        # stops here.
        if offered and zeros > offered * ZERO_SHARE_LIMIT:
            raise ParseError(
                f"{iso}: {zeros} of {offered} values are 0.0. The measured share is "
                f"2.1 %. Check the dataset at the publisher."
            )

        if absurd > max(1, offered * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {absurd} of {offered} values are outside "
                f"{config.INTENSITY_ABSURD_LOW} to {config.INTENSITY_ABSURD_HIGH}. "
                f"Check the unit. First: {context.dropped[0]}"
            )

        return records


PRODUCTION = EliaCo2(PRODUCTION_ID, "production")
CONSUMPTION = EliaCo2(CONSUMPTION_ID, "consumption")
