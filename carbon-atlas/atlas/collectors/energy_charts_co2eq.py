"""energy-charts `/co2eq` — carbon intensity, Fraunhofer ISE.

Register entry: `energy-charts-co2eq` in `sources/sources.json`.

The response holds 4 fields:

    unix_seconds      the timestamp of the interval start, UTC
    co2eq             the measurement, gCO2eq/kWh
    co2eq_forecast    the forward curve. It is empty on a past window.
    deprecated        a flag of the API

⚠ `co2eq_forecast` is empty for a past window. A probe on 2026-09-17 read 288
actual values and 0 forecast values across 2 days of March 2024. So the forecast
of this source lives only in the snapshots that `atlas snap` captures. A run
that the program does not capture is lost for ever. FORECASTS.md section 3.

⚠ The resolution is not the same in every country: 15 minutes in 18 countries,
30 in Great Britain (`uk` in this API), 60 in 15 others. The parser derives the
step from the `unix_seconds` array, and it never assumes one. `sources.json`
says the same.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from .. import config
from ..model import ParseError, Record
from .base import ParseContext, field_hash

SOURCE_ID = "energy-charts-co2eq"

# Guard 1: the field set of the payload. A change stops the parse.
EXPECTED_FIELDS = ("co2eq", "co2eq_forecast", "deprecated", "unix_seconds")
EXPECTED_FIELD_HASH = field_hash(EXPECTED_FIELDS)

# Guard 3: the UTC column. This API gives one time column, and it is UTC.
TIME_FIELD = "unix_seconds"


class EnergyChartsCo2eq:
    source_id = SOURCE_ID
    metric = "intensity"
    unit = "gCO2eq/kWh"

    # Probe of 2026-09-17: 2015-06-01 gives records, 2014-06-01 gives HTTP 404.
    # The exact first day of each country is not measured. A too-early window
    # gives 404, and the runner writes an `empty` row for those days.
    # The measured first day of each country is in REFERENCE.md section 2.
    available_from = date(2015, 6, 1)

    # One request carried 11 years in the probe: 375,644 points, 8.1 MB, 36 s.
    # So a full backfill of one country is one request.
    max_span_days = 4200

    empty_http_status = (404,)
    has_forecast_curve = True

    # ⚠ The forward curve is 8 h to 57 h ahead. The length is a property of the
    # country: AT gives 57.0 h, and several 60-minute countries give 8.2 h.
    # MEASURED 2026-09-17 across 34 countries. FORECASTS.md section 3. 2 days
    # alone does not hold a 57 h curve. `fetch` adds one day at each end, so
    # the request reaches about 78 h forward. Do not remove that padding.
    snap_days_ahead = 2

    def __init__(self) -> None:
        entry = config.source(SOURCE_ID)
        self.url = entry["api_base"] + entry["endpoints"][0]["path"]
        method = entry.get("methodology", {})
        self.basis = method.get("basis")
        self.scope = method.get("scope")
        self._codes = set(entry["coverage"]["countries_verified"])

    def countries(self) -> list[str]:
        """The ISO codes that this source serves, from the two registers.

        `sources.json` names 34 verified country codes. `zones.json` maps each
        ISO code to the code of this API. A country with no code, or with a
        code that the register does not verify, is not in the list.
        """
        result = []
        for entry in config.countries():
            code = entry.get("ec")
            if code and code in self._codes:
                result.append(entry["iso"])
        return result

    def api_code(self, iso: str) -> str:
        code = config.country(iso).get("ec")
        if not code:
            raise KeyError(f"{iso} has no energy-charts code in zones.json")
        return code

    def fetch(
        self, http, iso: str, start: date, end: date, tries: int | None = None
    ) -> tuple[int, bytes]:
        """One request for one country and one window.

        `start` and `end` are the first and the last UTC day to collect.

        ⚠ This API counts a day in the local time of the country, and the store
        counts a day in UTC. In Germany in summer, the local day starts at
        22:00 UTC of the day before. So a window that stops at the end date
        gives a last UTC day that is 2 hours short, and the runner marks that
        short day `ok`. The request adds one day at each end. The extra records
        go in the store, and they make no duplicate.

        ⚠ The day at the end has a second purpose. A snapshot asks for 2 days,
        and the forward curve of some countries is 57 h. The extra day holds
        the tail of that curve. See `snap_days_ahead`.
        """
        padded = max(start - timedelta(days=1), self.available_from)
        params = {
            "country": self.api_code(iso),
            "start": padded.isoformat(),
            "end": (end + timedelta(days=1)).isoformat(),
        }
        return http.get(SOURCE_ID, self.url, params, tries=tries)

    def parse(self, payload: bytes, iso: str, context: ParseContext) -> list[Record]:
        try:
            body = json.loads(payload)
        except ValueError as error:
            raise ParseError(f"the payload is not JSON: {error}") from None
        if not isinstance(body, dict):
            raise ParseError(f"the payload is a {type(body).__name__}, not an object")

        # Guard 1: the field set.
        if field_hash(body.keys()) != EXPECTED_FIELD_HASH:
            raise ParseError(
                f"the field set changed. Expected {sorted(EXPECTED_FIELDS)}, "
                f"got {sorted(body)}. Check the API, then update the collector."
            )

        # Guard 3: the UTC column.
        stamps = body.get(TIME_FIELD)
        if not isinstance(stamps, list):
            raise ParseError(f"{TIME_FIELD} is absent, so the time base is not known")

        field = "co2eq_forecast" if context.kind == "forecast" else "co2eq"
        values = body.get(field)
        if not isinstance(values, list):
            raise ParseError(f"{field} is not a list")
        if len(values) != len(stamps):
            raise ParseError(
                f"{field} has {len(values)} values and {TIME_FIELD} has {len(stamps)}"
            )

        run_at = context.run_at
        seen: dict[datetime, float] = {}
        records: list[Record] = []

        offered = 0
        absurd = 0

        for stamp, value in zip(stamps, values):
            if value is None:
                continue
            offered += 1
            ts_utc = datetime.fromtimestamp(int(stamp), tz=timezone.utc).replace(tzinfo=None)
            number = float(value)

            # Guard 2, band 1: the store band. The point goes out, and the
            # payload stays.
            if not (config.INTENSITY_MIN <= number <= config.INTENSITY_MAX):
                context.dropped.append(
                    f"{value} gCO2eq/kWh at {ts_utc.isoformat()} is outside "
                    f"{config.INTENSITY_MIN} to {config.INTENSITY_MAX}"
                )
                # Guard 2, band 2: the absurd band.
                if not (config.INTENSITY_ABSURD_LOW <= number <= config.INTENSITY_ABSURD_HIGH):
                    absurd += 1
                continue

            # Guard 4: one timestamp gives one value in one payload. An equal
            # repeat is one measurement written two times, and one copy stays,
            # which is the answer of `base.py`. ⚠ A repeat with two different
            # values stops the payload here, and this collector measures no
            # share. `unix_seconds` is a UTC epoch, so the two local labels of
            # a time change can not make a repeat, and a conflict is a format
            # fault. `base.py` names this collector as the exception.
            if ts_utc in seen:
                if seen[ts_utc] == number:
                    continue
                raise ParseError(
                    f"{iso}: {ts_utc.isoformat()} is in the payload two times, with "
                    f"{seen[ts_utc]} and {number}"
                )
            seen[ts_utc] = number

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
                    value=float(value),
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

        # A payload with many absurd points is a unit change or a new factor
        # table. The program must not guess, so it writes nothing.
        if absurd > max(1, offered * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {absurd} of {offered} values are outside "
                f"{config.INTENSITY_ABSURD_LOW} to {config.INTENSITY_ABSURD_HIGH}. "
                f"Check the unit and the factor table. First: {context.dropped[0]}"
            )

        return records

    def snap_window(self, today: date) -> tuple[date, date]:
        """The window of a forecast snapshot."""
        return (today, today + timedelta(days=self.snap_days_ahead))


COLLECTOR = EnergyChartsCo2eq()
