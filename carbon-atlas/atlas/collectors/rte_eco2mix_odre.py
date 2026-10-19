"""RTE eCO2mix through ODRE — France.

Register entry: `rte-eco2mix-odre` in `sources/sources.json`.

    GET /{dataset}/exports/json?where=...&select=...&order_by=date_heure

Two datasets hold one series between them. Probe of 2026-09-18:

    eco2mix-national-cons-def   2011-12-31T23:00Z .. 2026-06-30T21:30Z
    eco2mix-national-tr         2026-06-30T22:00Z .. now

They meet, and they do not overlap. So a window near the boundary needs both,
and this collector always asks both. The raw file keeps the two answers under
their own dataset name, so the evidence of each request stays separate.

⚠ The step of the CO2 column is not the step of the rows. Both datasets
give one row every 15 minutes. `taux_co2` is filled on every row in the
real-time dataset, and only at :00 and :30 in the definitive dataset. Measured
on 2026-09-18 for 2015-03-01, 2020-06-01 and 2024-06-01: 96 rows and 48 values.
The parser stores the values it gets and never fills a gap.

⚠ The unit is g/kWh, and the publisher does not state a scope. The field
label is `Taux de CO2 (g/kWh)` and the description is "Estimation des émissions
de carbone générées par la production d'électricité en France". That is
production-based. It does not say lifecycle, and it does not say direct
combustion. The register says `not stated`, and no panel may call this number
comparable with a lifecycle series.

⚠ A definitive value supersedes a real-time value. When one timestamp
arrives from both datasets in one payload, the parser keeps the definitive one.
A later run that finds a changed value writes a revision, and the store keeps
both. `REFERENCE.md` section 4.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from .. import config
from ..model import FetchError, ParseError, Record
from .base import ParseContext, dedupe, field_hash

SOURCE_ID = "rte-eco2mix-odre"

# The datasets, in the order of trust. The first one wins a timestamp.
DEFINITIVE = "eco2mix-national-cons-def"
REALTIME = "eco2mix-national-tr"
DATASETS = (DEFINITIVE, REALTIME)

# The fields this collector asks for. ODRE answers HTTP 400 for a field that
# does not exist, so a renamed field stops the fetch and not the parse.
SELECT = ("date_heure", "taux_co2", "consommation", "nature", "perimetre")

# Guard 1: the field set of one row.
EXPECTED_FIELD_HASH = field_hash(SELECT)

# Guard 3: the time column. ODRE gives it with an explicit UTC offset.
TIME_FIELD = "date_heure"

# The national dataset covers one perimeter. Another value is a change.
PERIMETER = "France"


class RteEco2mixOdre:
    source_id = SOURCE_ID
    metric = "intensity"

    # ⚠ Not gCO2eq. The publisher states g/kWh and no scope.
    unit = "gCO2/kWh"

    # Probe of 2026-09-18: the oldest record of the definitive dataset is
    # 2011-12-31T23:00Z, which is 2012-01-01 in local time.
    available_from = date(2011, 12, 31)

    # Measured on 2026-09-18: one year of the definitive dataset is 35,136
    # rows, 2.1 MB and 5.7 seconds in one request.
    max_span_days = 365

    empty_http_status = ()
    has_forecast_curve = False

    def __init__(self) -> None:
        entry = config.source(SOURCE_ID)
        self.base = entry["api_base"]
        method = entry.get("methodology", {})
        self.basis = method.get("basis")
        self.scope = method.get("scope")

    def countries(self) -> list[str]:
        zones = set(config.source(SOURCE_ID).get("coverage", {}).get("zones", []))
        return [c["iso"] for c in config.countries() if c["iso"] in zones]

    def fetch(
        self, http, iso: str, start: date, end: date, tries: int | None = None
    ) -> tuple[int, bytes]:
        """Two requests, one for each dataset, and one payload.

        The runner stores what this returns, so the payload keeps each answer
        under its own dataset name. Nothing is merged before the store.

        ⚠ This function must build one payload from two answers, so it reads
        each answer here. A bad answer raises `FetchError` and not
        `ParseError`, because the runner catches `FetchError` around `fetch`
        and `ParseError` around `parse`. A `ParseError` here would leave the
        window with no run row.
        """
        stop = end + timedelta(days=1)
        where = (
            f"{TIME_FIELD} >= date'{start.isoformat()}' and "
            f"{TIME_FIELD} < date'{stop.isoformat()}'"
        )
        params = {"where": where, "select": ",".join(SELECT), "order_by": TIME_FIELD}

        answers: dict[str, list] = {}
        status = 200
        for dataset in DATASETS:
            status, payload = http.get(
                SOURCE_ID, f"{self.base}/{dataset}/exports/json", params, tries=tries
            )
            try:
                body = json.loads(payload)
            except ValueError as error:
                raise FetchError(
                    f"{dataset}: the answer is not JSON: {error}", status
                ) from None
            if not isinstance(body, list):
                raise FetchError(
                    f"{dataset}: the answer is a {type(body).__name__}, not a list. "
                    f"{str(body)[:200]}",
                    status,
                )
            answers[dataset] = body
        return status, json.dumps({"datasets": answers}).encode("utf-8")

    def parse(self, payload: bytes, iso: str, context: ParseContext) -> list[Record]:
        if context.kind != "actual":
            return []  # This source publishes no CO2 forecast. FORECASTS.md.

        try:
            body = json.loads(payload)
        except ValueError as error:
            raise ParseError(f"the payload is not JSON: {error}") from None
        answers = body.get("datasets") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            raise ParseError("the payload holds no `datasets` object")

        records: list[Record] = []
        taken: dict[datetime, str] = {}
        offered = 0
        absurd = 0

        for dataset in DATASETS:              # the definitive dataset comes first
            rows = answers.get(dataset)
            if rows is None:
                raise ParseError(f"the payload holds no answer for {dataset}")
            if not isinstance(rows, list):
                raise ParseError(f"{dataset}: the answer is not a list")

            # ⚠ Guard 4. MEASURED 2026-09-18: the hour of the spring time
            # change carries two local labels, 02:00 and 03:00, for one UTC
            # instant. Both rows hold the same number, so one copy stays. A
            # timestamp with two different numbers goes. `dedupe` holds the
            # rule, and `base.py` gives the reason.
            pairs = [
                (r.get(TIME_FIELD), r.get("taux_co2"))
                for r in rows if isinstance(r, dict)
            ]
            conflict = dedupe(pairs, context, name=f"{dataset}: ")
            if conflict and len(conflict) > max(1, len(pairs) * config.OUT_OF_RANGE_LIMIT):
                raise ParseError(
                    f"{dataset}: {len(conflict)} timestamps carry two different "
                    f"values. That is not the time change. Check the API."
                )

            for row in rows:
                if not isinstance(row, dict):
                    raise ParseError(f"{dataset}: a row is a {type(row).__name__}")

                # Guard 1: the field set.
                if field_hash(row.keys()) != EXPECTED_FIELD_HASH:
                    raise ParseError(
                        f"{dataset}: the field set changed. Expected {sorted(SELECT)}, "
                        f"got {sorted(row)}. Check the API, then update the collector."
                    )
                if row.get("perimetre") != PERIMETER:
                    raise ParseError(
                        f"{dataset}: the perimeter is {row.get('perimetre')!r} and not "
                        f"{PERIMETER!r}. This is the national dataset."
                    )

                if row.get(TIME_FIELD) in conflict:
                    continue  # Guard 4. The reason is already in `dropped`.

                value = row.get("taux_co2")
                if value is None:
                    continue  # ⚠ The CO2 column is filled on some rows only.
                offered += 1

                # Guard 3: the UTC column.
                stamp = row.get(TIME_FIELD)
                if not isinstance(stamp, str):
                    raise ParseError(f"{dataset}: `{TIME_FIELD}` is {stamp!r}")
                try:
                    moment = datetime.fromisoformat(stamp)
                except ValueError:
                    raise ParseError(f"{dataset}: `{TIME_FIELD}` is {stamp!r}") from None
                if moment.utcoffset() is None:
                    raise ParseError(
                        f"{dataset}: `{TIME_FIELD}` {stamp!r} carries no offset, so the "
                        f"time base is not known"
                    )
                ts_utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
                number = float(value)

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

                # One timestamp gives one record. An equal copy inside one
                # dataset is dropped here, and a timestamp that both datasets
                # hold stays with the definitive one, which is read first.
                if ts_utc in taken:
                    continue
                taken[ts_utc] = dataset

                records.append(
                    Record(
                        country=iso,
                        source_id=SOURCE_ID,
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

        if absurd > max(1, offered * config.OUT_OF_RANGE_LIMIT):
            raise ParseError(
                f"{iso}: {absurd} of {offered} values are outside "
                f"{config.INTENSITY_ABSURD_LOW} to {config.INTENSITY_ABSURD_HIGH}. "
                f"Check the unit. First: {context.dropped[0]}"
            )

        return records


COLLECTOR = RteEco2mixOdre()
