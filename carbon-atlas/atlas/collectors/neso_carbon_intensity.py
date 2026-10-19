"""NESO Carbon Intensity API — Great Britain.

Register entry: `neso-carbon-intensity` in `sources/sources.json`.

    GET /intensity/{from}/{to}     ISO 8601, `2026-09-10T00:00Z`

The response holds one object for each half hour:

    {"from": "2026-09-09T23:30Z",
     "to":   "2026-09-10T00:00Z",
     "intensity": {"forecast": 162, "actual": 151, "index": "moderate"}}

⚠ The unit is gCO2/kWh, and the scope is direct combustion. It is not the
lifecycle gCO2eq/kWh of energy-charts. A probe of 2026-09-16 read the published
methodology: nuclear, wind, solar and hydro are zero rated, and the factors are
combustion factors. So a NESO number is 20 to 40 g below a lifecycle number for
the same hour. The two are not comparable, and the store keeps the unit and the
scope in every row for that reason. `SOURCES.md` section 1.2.

⚠ `actual` and `forecast` are two different columns of the same object. The
program never collapses them with an `or`. This collector reads `actual` in a
measurement run, and `forecast` in a snapshot run.

⚠ `actual` is null for the newest periods, and it stays null for about an hour
after the period ends. A null is not a zero. The parser skips it, so a day that
the program collects too early holds fewer periods than the day has, and the
run row still says `ok`. `atlas daily` reads the last `config.RECENT_DAYS` days
again whatever their status, and that run fills the periods. A backfill does
not, because it passes 0 for that count.

⚠ A value of exactly 0.0 is an outage, and not a clean half hour. MEASURED
2026-09-23, with a query on the store of 152,154 GB records:

- 6 records hold 0.0: 2023-01-31 01:00, 2023-06-07 at 09:30, 10:00, 10:30 and
  11:00, and 2026-08-06 11:00. They are the only 0.0 records in the store.
- The smallest value above zero that this publisher gives is 14.0.
- The half hour before 2023-01-31 01:00 holds 103 and the one after holds 91.
  energy-charts gives 133.0 for the same half hour.
- The four zeros of 2023-06-07 sit where energy-charts gives 335.7 to 375.4,
  which is the dirtiest part of that morning.
- 2026-08-06 11:00 sits between 34 and 41.

GB burns gas in every hour of this record, so a direct-combustion zero is not
physical. The zero marks a half hour that the publisher did not compute. Guard
2 takes it, because `INTENSITY_MIN` is 0.0. So this collector calls
`zero_guard()` from `base.py`, and the run row names every dropped half hour.
The guard holds for the forecast column too, because the same publisher writes
both columns.

⚠ The guard works on what the program collects next. The 6 records above stay
in the store. A dropped point writes no row, and the store runs no `UPDATE`, so
`record_current` keeps a stored 0.0 whatever a later run does. `REFERENCE.md`,
section *6 records hold 0.0, and all 6 are NESO GB*, states the same rule: a
query that ranks GB by the lowest value must exclude 0.0.

Probe of 2026-09-18:

    2026-08-01 to 2026-08-31   HTTP 200, 1441 half hours in one request
    2018-01-01                 HTTP 200, actual 155
    2017-01-01                 HTTP 200, `data` is empty

So the first day of the series is in 2018. 1441 half hours is 30 days of 48
periods, plus the period that starts at the closing instant, which is the span
that `max_span_days` holds. A 31-day month therefore takes two windows.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .. import config
from ..model import ParseError, Record
from .base import ParseContext, check_zero_share, dedupe, field_hash, zero_guard

SOURCE_ID = "neso-carbon-intensity"

# The sentence that the run row carries for a dropped zero. It states the
# reason of this publisher, and the module docstring holds the measurement.
ZERO_REASON = (
    "This publisher writes 0.0 for a half hour that it did not compute. GB "
    "burns gas in every hour of this record, and the smallest value above zero "
    "that it gives is 14.0, so the half hour gets no record."
)

# What `check_zero_share` tells the operator when a payload is mostly zeros.
ZERO_MEASURED = "The measured share is 6 of 152,154 on 2026-09-23."

# Guard 1: the field set of one period, and of the nested intensity object.
EXPECTED_FIELDS = ("from", "to", "intensity")
EXPECTED_FIELD_HASH = field_hash(EXPECTED_FIELDS)
# The names inside `intensity`. A period may hold fewer of them, and it may
# hold no name that this tuple does not carry. See `parse`.
EXPECTED_INTENSITY = ("actual", "forecast", "index")

# Guard 3: the time column. This API gives one time base, and it is UTC.
TIME_FIELD = "from"


class NesoCarbonIntensity:
    source_id = SOURCE_ID
    metric = "intensity"

    # ⚠ Not gCO2eq. See the module docstring.
    unit = "gCO2/kWh"

    # Probe of 2026-09-18: 2018-01-01 gives values, 2017-01-01 gives an empty
    # list. The publisher states that the series starts in 2018.
    available_from = date(2018, 1, 1)

    # A 30-day request returned 1441 half hours on 2026-09-18, which is the
    # whole span. The publisher documents a limit of 14 days for some
    # endpoints. ⚠ A range limit arrives as a 4xx, and `runner.SPLIT_STATUS`
    # holds 500, 502, 503 and 504 only, so such a window fails and does not
    # split. 30 days is measured to work on this endpoint.
    max_span_days = 30

    # This API answers 200 with an empty list for a window it does not serve.
    # The runner writes an `empty` row from the record count, so no status code
    # is needed here.
    empty_http_status = ()

    has_forecast_curve = True

    # The published forward curve reaches 48 hours. The snapshot asks for 3
    # days, so the whole curve is inside the window.
    snap_days_ahead = 3

    def __init__(self) -> None:
        entry = config.source(SOURCE_ID)
        self.url = entry["api_base"] + entry["endpoints"][0]["path"]
        method = entry.get("methodology", {})
        self.basis = method.get("basis")
        self.scope = method.get("scope")

    def countries(self) -> list[str]:
        """The ISO codes of the zone model that this source serves.

        The register names the zones. A country is in the list when the zone
        model holds it, so a change of the country list changes nothing here.
        """
        zones = set(config.source(SOURCE_ID).get("coverage", {}).get("zones", []))
        return [c["iso"] for c in config.countries() if c["iso"] in zones]

    def fetch(
        self, http, iso: str, start: date, end: date, tries: int | None = None
    ) -> tuple[int, bytes]:
        """One request for one window.

        The path carries the window, so there is no query string. `to` is the
        start of the day after the last day, because the API counts the period
        that starts inside the window.
        """
        first = f"{start.isoformat()}T00:00Z"
        last = f"{(end + timedelta(days=1)).isoformat()}T00:00Z"
        return http.get(SOURCE_ID, f"{self.url}/{first}/{last}", None, tries=tries)

    def parse(self, payload: bytes, iso: str, context: ParseContext) -> list[Record]:
        try:
            body = json.loads(payload)
        except ValueError as error:
            raise ParseError(f"the payload is not JSON: {error}") from None
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ParseError("the payload holds no `data` list")

        periods = body["data"]
        column = "forecast" if context.kind == "forecast" else "actual"
        run_at = context.run_at
        records: list[Record] = []
        offered = 0
        absurd = 0
        zeros = 0
        # The first absurd point, and not `context.dropped[0]`. That list also
        # holds a conflict of Guard 4 and a dropped zero, so its first line can
        # name a point that the message below is not about.
        first_absurd = ""

        # ⚠ Guard 4. MEASURED 2026-09-18: this publisher gives one half hour
        # two times with two different values. `2021-04-19T19:00Z` came back
        # with actual 303 and actual 295 in one answer. A 30-day window must
        # not be lost for one bad half hour, so the conflict goes and the rest
        # of the answer stays. `dedupe` holds the rule.
        pairs = [
            (p.get(TIME_FIELD), (p.get("intensity") or {}).get(column))
            for p in periods
            if isinstance(p, dict) and isinstance(p.get("intensity"), dict)
        ]
        repeated = dedupe(pairs, context)
        stamps = {stamp for stamp, _ in pairs}
        if len(repeated) > max(1, len(stamps) * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {len(repeated)} of {len(stamps)} timestamps carry two "
                f"different values. That is not one bad period. Check the API."
            )

        seen: set[datetime] = set()

        for period in periods:
            if not isinstance(period, dict):
                raise ParseError(f"a period is a {type(period).__name__}, not an object")

            # Guard 1: the field set, outside and inside.
            if field_hash(period.keys()) != EXPECTED_FIELD_HASH:
                raise ParseError(
                    f"the field set changed. Expected {sorted(EXPECTED_FIELDS)}, "
                    f"got {sorted(period)}. Check the API, then update the collector."
                )
            intensity = period.get("intensity")
            if not isinstance(intensity, dict):
                raise ParseError("`intensity` is not an object")
            # ⚠ MEASURED 2026-09-18: a period can carry `actual` and `index`
            # and no `forecast` at all. 17 of the 1,441 periods of one 30-day
            # window of 2025 do.
            # The publisher had no forecast for those half hours. A column
            # that is absent is not a format change, and it must not lose the
            # measurement of a month. A name that this collector does not know
            # is a format change, and it stops the parse.
            unknown = set(intensity) - set(EXPECTED_INTENSITY)
            if unknown:
                raise ParseError(
                    f"the intensity object holds {sorted(unknown)}, which this "
                    f"collector does not know. Expected {sorted(EXPECTED_INTENSITY)}."
                )

            if period.get(TIME_FIELD) in repeated:
                continue  # Guard 4. The reason is already in `dropped`.

            value = intensity.get(column)
            if value is None:
                continue  # ⚠ A null is not a zero. See the module docstring.
            offered += 1

            # Guard 3: the UTC column.
            stamp = period.get(TIME_FIELD)
            if not isinstance(stamp, str) or not stamp.endswith("Z"):
                raise ParseError(
                    f"`{TIME_FIELD}` is {stamp!r}, so the time base is not stated as UTC"
                )
            ts_utc = datetime.strptime(stamp, "%Y-%m-%dT%H:%MZ")
            number = float(value)

            # ⚠ The zero guard. It runs before Guard 2, because 0.0 is inside
            # the store band. The module docstring holds the measurement, and
            # `base.py` holds the rule.
            if zero_guard(number, ts_utc, context, column, ZERO_REASON):
                zeros += 1
                continue

            # Guard 2, band 1: the store band.
            if not (config.INTENSITY_MIN <= number <= config.INTENSITY_MAX):
                context.dropped.append(
                    f"{value} {self.unit} at {ts_utc.isoformat()} is outside "
                    f"{config.INTENSITY_MIN} to {config.INTENSITY_MAX}"
                )
                # Guard 2, band 2: the absurd band.
                if not (config.INTENSITY_ABSURD_LOW <= number <= config.INTENSITY_ABSURD_HIGH):
                    absurd += 1
                    first_absurd = first_absurd or context.dropped[-1]
                continue

            if ts_utc in seen:
                continue            # an equal copy. `dedupe` allows one only.
            seen.add(ts_utc)

            horizon = None
            if context.kind == "forecast" and run_at is not None:
                horizon = int((ts_utc - run_at).total_seconds() // 60)
                if horizon < 0:
                    continue  # The curve starts before the fetch. That is an actual.

            records.append(
                Record(
                    country=iso,
                    source_id=SOURCE_ID,
                    metric=self.metric,
                    ts_utc=ts_utc,
                    value=number,
                    unit=self.unit,
                    granularity="native",
                    kind=context.kind,
                    basis=self.basis,
                    scope=self.scope,
                    run_at=run_at,
                    horizon_min=horizon,
                    collected_at=context.collected_at,
                    raw_ref=context.raw_ref,
                )
            )

        # A few zeros are the known defect, and the guard above drops them one
        # by one. A payload that is mostly zeros is a change at the publisher,
        # and it stops here.
        check_zero_share(iso, zeros, offered, ZERO_MEASURED)

        if absurd > max(1, offered * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {absurd} of {offered} values are outside "
                f"{config.INTENSITY_ABSURD_LOW} to {config.INTENSITY_ABSURD_HIGH}. "
                f"Check the unit and the factor table. First: {first_absurd}"
            )

        return records

    def snap_window(self, today: date) -> tuple[date, date]:
        return (today, today + timedelta(days=self.snap_days_ahead))


COLLECTOR = NesoCarbonIntensity()
