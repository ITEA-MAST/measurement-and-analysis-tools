"""Energinet Energi Data Service — Denmark.

Register entry: `energinet-eds` in `sources/sources.json`.

    GET /dataset/CO2Emis?start=..&end=..&limit=0
        Minutes5UTC, Minutes5DK, PriceArea, CO2Emission      5 minutes, g/kWh

    GET /dataset/GenerationProdTypeExchange?...&columns=TimeUTC,PriceArea,GrossCon
        TimeUTC, PriceArea, GrossCon                         1 hour, MWh

⚠ Denmark is two price areas, and a country value needs a weight. DK1 and
DK2 are separate grids that meet only through the Great Belt link, and they do
not carry the same intensity. A probe on 2026-09-18 read DK1 57 g and DK2 24 g
at one instant, a factor of 2.4. The mean of the two areas is not the value of
the country, because DK1 carries more load than DK2. So this collector reads
the gross consumption of each area in the same hour and writes

    intensity(DK) = (I1 * L1 + I2 * L2) / (L1 + L2)

That is the `aggregated` granularity of `sources/zones.json`, and the record
names the two zones it came from. When either area has no value, or when the
hour has no load, the roll-up writes nothing. It never falls back to a plain
mean, because a plain mean is a different number with the same name.

⚠ The load comes from the new dataset. `ElectricityBalanceNonv` also holds
a load column, and the publisher discontinued it on 2026-01-06 and will delete
it. `GenerationProdTypeExchange` replaces it and starts on 2015-01-01.

⚠ The basis is consumption, and not production. The publisher writes: "the
CO2 emission from electricity consumed in Denmark measured in g/kWh". So this
series counts the emissions of an import, and energy-charts does not. The two
differ for that reason alone, before any factor table.

⚠ The publisher does not correct its own errors. The dataset comment says
"Errors will occur, and will generally not be corrected." The store keeps every
revision, and this source gives few.

⚠ The rate limit is not published as a number. A probe on 2026-09-18 got
HTTP 429 with "Try again in 277 seconds" after about 6 fast requests. The
register asks for 12 requests each minute, and `net.py` honours `Retry-After`.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .. import config
from ..model import FetchError, ParseError, Record
from .base import ParseContext, field_hash

SOURCE_ID = "energinet-eds"

CO2_DATASET = "CO2Emis"
LOAD_DATASET = "GenerationProdTypeExchange"

# Guard 1: the field set of one row of each dataset.
CO2_FIELDS = ("Minutes5UTC", "Minutes5DK", "PriceArea", "CO2Emission")
CO2_FIELD_HASH = field_hash(CO2_FIELDS)
LOAD_FIELDS = ("TimeUTC", "PriceArea", "GrossCon")
LOAD_FIELD_HASH = field_hash(LOAD_FIELDS)

# Guard 3: the UTC column of each dataset. The publisher gives a local column
# beside it, and this collector never reads that one.
CO2_TIME = "Minutes5UTC"
LOAD_TIME = "TimeUTC"

ZONES = ("DK1", "DK2")


class EnerginetEds:
    source_id = SOURCE_ID
    metric = "intensity"

    # ⚠ Not gCO2eq. The publisher states g/kWh and no scope.
    unit = "gCO2/kWh"

    # Probe of 2026-09-18: the oldest record is 2016-12-31T23:00Z, which is
    # 2017-01-01 in Danish local time.
    available_from = date(2016, 12, 31)

    # Measured on 2026-09-18: one year of CO2Emis is 210,792 rows and 24 MB.
    # 180 days keeps one payload near 12 MB.
    max_span_days = 180

    empty_http_status = ()
    has_forecast_curve = False   # `CO2EmisProg` holds it. It is not collected yet.

    def __init__(self) -> None:
        entry = config.source(SOURCE_ID)
        self.base = entry["api_base"]
        method = entry.get("methodology", {})
        self.basis = method.get("basis")
        self.scope = method.get("scope")

    def countries(self) -> list[str]:
        """Denmark, from the zone model. The two price areas are not
        countries, so they never appear in this list."""
        return [c["iso"] for c in config.countries() if c.get("national", {})
                and (c.get("national") or {}).get("source_id") == SOURCE_ID]

    def fetch(
        self, http, iso: str, start: date, end: date, tries: int | None = None
    ) -> tuple[int, bytes]:
        """Two requests: the intensity of each area, and the load of each area.

        ⚠ This function must build one payload from two answers, so it reads
        each answer here. A bad answer raises `FetchError` and not
        `ParseError`, because the runner catches `FetchError` around `fetch`
        and `ParseError` around `parse`. A `ParseError` here would leave the
        window with no run row.
        """
        stop = (end + timedelta(days=1)).isoformat()
        window = {"start": f"{start.isoformat()}T00:00", "end": f"{stop}T00:00", "limit": "0"}

        status, payload = http.get(
            SOURCE_ID, f"{self.base}/{CO2_DATASET}", dict(window), tries=tries
        )
        co2 = self._records_of(payload, CO2_DATASET, status)

        load_params = dict(window)
        load_params["columns"] = ",".join(LOAD_FIELDS)
        status, payload = http.get(
            SOURCE_ID, f"{self.base}/{LOAD_DATASET}", load_params, tries=tries
        )
        load = self._records_of(payload, LOAD_DATASET, status)

        return status, json.dumps({CO2_DATASET: co2, LOAD_DATASET: load}).encode("utf-8")

    @staticmethod
    def _records_of(payload: bytes, dataset: str, status: int) -> list:
        try:
            body = json.loads(payload)
        except ValueError as error:
            raise FetchError(
                f"{dataset}: the answer is not JSON: {error}", status
            ) from None
        rows = body.get("records") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise FetchError(f"{dataset}: the answer holds no `records` list", status)
        return rows

    def parse(self, payload: bytes, iso: str, context: ParseContext) -> list[Record]:
        if context.kind != "actual":
            return []

        try:
            body = json.loads(payload)
        except ValueError as error:
            raise ParseError(f"the payload is not JSON: {error}") from None
        if not isinstance(body, dict):
            raise ParseError("the payload is not an object")

        load = self._load_index(body.get(LOAD_DATASET))
        rows = body.get(CO2_DATASET)
        if not isinstance(rows, list):
            raise ParseError(f"the payload holds no {CO2_DATASET} list")

        # The intensity of each area, at each 5-minute stamp.
        by_stamp: dict[str, dict[str, float]] = {}
        offered = 0
        absurd = 0
        conflict_rows = 0
        for row in rows:
            if not isinstance(row, dict):
                raise ParseError(f"{CO2_DATASET}: a row is a {type(row).__name__}")
            if field_hash(row.keys()) != CO2_FIELD_HASH:
                raise ParseError(
                    f"{CO2_DATASET}: the field set changed. Expected "
                    f"{sorted(CO2_FIELDS)}, got {sorted(row)}."
                )
            area = row.get("PriceArea")
            if area not in ZONES:
                raise ParseError(
                    f"{CO2_DATASET}: the price area is {area!r}. The register names {ZONES}."
                )
            value = row.get("CO2Emission")
            if value is None:
                continue
            offered += 1
            number = float(value)

            stamp = row.get(CO2_TIME)
            if not isinstance(stamp, str):
                raise ParseError(f"{CO2_DATASET}: `{CO2_TIME}` is {stamp!r}")

            # Guard 2, band 1: the store band, on the area value.
            if not (config.INTENSITY_MIN <= number <= config.INTENSITY_MAX):
                context.dropped.append(
                    f"{area} {value} {self.unit} at {stamp} is outside "
                    f"{config.INTENSITY_MIN} to {config.INTENSITY_MAX}"
                )
                if not (config.INTENSITY_ABSURD_LOW <= number <= config.INTENSITY_ABSURD_HIGH):
                    absurd += 1
                continue

            seen = by_stamp.setdefault(stamp, {})
            if area in seen:
                if seen[area] is None:
                    continue  # Guard 4. The reason is already in `dropped`.
                if seen[area] != number:
                    # Guard 4, the conflict case. One area, one stamp, two
                    # numbers. The branch above takes a third row of that
                    # area, so the run row gets one line for each conflict and
                    # it never names the `None` as a published value.
                    conflict_rows += 1
                    context.dropped.append(
                        f"{CO2_DATASET}: {area} at {stamp} carries {seen[area]} and "
                        f"{number}. No rule chooses one, so the program stores none."
                    )
                    seen[area] = None       # the stamp can not be rolled up
                    continue
            seen[area] = number

        if absurd > max(1, offered * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {absurd} of {offered} values are outside "
                f"{config.INTENSITY_ABSURD_LOW} to {config.INTENSITY_ABSURD_HIGH}. "
                f"Check the unit. First: {context.dropped[0]}"
            )

        # Guard 4 keeps the same ceiling as the other collectors. Without it, a
        # payload where every stamp conflicts writes no record and the run row
        # says `empty`, which reads as "the publisher has no data".
        if conflict_rows > max(1, offered * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {conflict_rows} of {offered} values carry two different "
                f"numbers for one price area and one stamp. That is not one bad "
                f"reading. Check the API."
            )

        records: list[Record] = []
        no_pair = 0
        no_load = 0
        conflict_stamps = 0
        for stamp, areas in sorted(by_stamp.items()):
            if any(zone not in areas for zone in ZONES):
                no_pair += 1
                continue
            if any(areas[zone] is None for zone in ZONES):
                conflict_stamps += 1   # Guard 4 poisoned an area of this stamp.
                continue
            ts_utc = self._utc_stamp(stamp, CO2_DATASET, CO2_TIME)
            hour = ts_utc.replace(minute=0, second=0, microsecond=0)
            weights = [load.get((zone, hour)) for zone in ZONES]
            if any(weight is None for weight in weights) or sum(weights) <= 0:
                no_load += 1
                continue

            value = sum(areas[zone] * weight for zone, weight in zip(ZONES, weights))
            value /= sum(weights)

            records.append(
                Record(
                    country=iso,
                    source_id=SOURCE_ID,
                    metric=self.metric,
                    ts_utc=ts_utc,
                    value=round(value, 3),
                    unit=self.unit,
                    granularity="aggregated",
                    zones=",".join(ZONES),
                    kind="actual",
                    basis=self.basis,
                    scope=self.scope,
                    collected_at=context.collected_at,
                    raw_ref=context.raw_ref,
                )
            )

        if no_pair:
            context.dropped.append(
                f"{no_pair} stamp(s) hold one price area only, so no country value "
                f"was computed for them."
            )
        if conflict_stamps:
            context.dropped.append(
                f"{conflict_stamps} stamp(s) hold two different values for one "
                f"price area, so no country value was computed for them."
            )
        if no_load:
            context.dropped.append(
                f"{no_load} stamp(s) have no gross consumption for the hour, so the "
                f"roll-up weight is not known and no country value was computed."
            )
        return records

    @staticmethod
    def _utc_stamp(stamp: str, dataset: str, field: str) -> datetime:
        """Guard 3. The UTC column of one row, as a datetime with no zone.

        Both datasets state that this column is UTC, so an offset is a change
        at the publisher. One helper serves both datasets. ⚠ A second copy of
        this check drifts away from the first one: the load column carried no
        check at all, and an offset there made every roll-up lose its weight
        and write no record.
        """
        try:
            moment = datetime.fromisoformat(stamp)
        except ValueError:
            raise ParseError(f"{dataset}: `{field}` is {stamp!r}") from None
        if moment.tzinfo is not None:
            raise ParseError(
                f"{dataset}: `{field}` {stamp!r} carries an offset. The publisher "
                f"states this column is UTC."
            )
        return moment

    def _load_index(self, rows) -> dict:
        """(area, hour) -> gross consumption, from the load dataset."""
        if not isinstance(rows, list):
            raise ParseError(f"the payload holds no {LOAD_DATASET} list")
        index: dict[tuple[str, datetime], float] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ParseError(f"{LOAD_DATASET}: a row is a {type(row).__name__}")
            if field_hash(row.keys()) != LOAD_FIELD_HASH:
                raise ParseError(
                    f"{LOAD_DATASET}: the field set changed. Expected "
                    f"{sorted(LOAD_FIELDS)}, got {sorted(row)}."
                )
            area = row.get("PriceArea")
            if area not in ZONES:
                continue
            value = row.get("GrossCon")
            stamp = row.get(LOAD_TIME)
            if value is None or not isinstance(stamp, str):
                continue
            hour = self._utc_stamp(stamp, LOAD_DATASET, LOAD_TIME).replace(
                minute=0, second=0, microsecond=0
            )
            weight = float(value)
            if weight <= 0:
                continue
            # The publisher gives an initial row and a settled row for one
            # hour. The last one in the answer is the newer one.
            index[(area, hour)] = weight
        return index


COLLECTOR = EnerginetEds()
