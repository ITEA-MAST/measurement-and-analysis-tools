"""The export to `portal/data/*.json`.

The portal reads a file. It makes no query and no network request.
ARCHITECTURE.md, section *The portal*.

**One file for each panel, and one file for each country.** The first export of
2026-09-17 wrote one `daily.json` of 13 MB for every country. A browser must not
read 13 MB to draw a map. So the export writes a small file for each view:

    meta.json          the sources, the countries, the counts
    monthly.json       country x source x month
    latest.json        the newest value of each country
    health.json        the run table and the coverage, for the Raw data tab
    register.json      the source register and the zone model
    daily_all.json     every country x day, the last 400 days
    hours.json         every country x hour, the last 30 days
    profile.json       every country x month x hour of the day
    forecast.json      the newest forward curve of each country
    pairs.json         two publishers of one country, hour against hour
    daily/<ISO>.json   country x source x day
    recent/<ISO>.json  the last 14 days at the native step

The size of each file is in REFERENCE.md, section 8. A size goes stale at each
backfill, so this file gives none. `atlas export` writes the total and the
largest file to the log at INFO level on each run.

**Three files hold every country at one time.** A panel that ranks 33 countries
must not read 33 files. `daily_all`, `hours` and `profile` hold one dense array
for each country, so the portal reads one file and indexes into it. A dense
array also costs less than a row list: it carries no country code and no
timestamp. `daily/<ISO>` and `recent/<ISO>` stay per country, because only the
selected country needs them.

⚠ **Those three files are keyed by source first, and by country second.**
`sources[<source_id>][<ISO>]`. Two publishers give a different number for the
same hour of the same country, and that difference is the measurement this
program exists for. A query that groups by country alone averages the two into
one cell, and the difference disappears in silence. **No query in this file
averages a value across sources.** The two country-level roll-ups in `_meta`
group by country alone, but they count rows and timestamps only.

⚠ **The unit belongs to the source, and not to the file.** energy-charts and
Elia give gCO2eq/kWh. NESO, RTE and Energinet give gCO2/kWh. A file that can
hold the rows of more than one source writes no `unit` key of its own, because
a scalar key there is a false statement about half the rows. `meta.json` gives
the unit of each source in `sources[].unit`, and the unit and the granularity
of each country and source pair in `countries[].sources[<source_id>]`. A panel
must read the unit and the granularity there, for the source that it draws.

⚠ The mean in these files is a **time mean**, and not a load-weighted mean. A
time mean answers "what was the mean intensity of the day". The carbon of a day
of work needs the load-weighted mean. The load series arrives with the
`/public_power` collector. Until then the field name says `mean_unweighted`, so
no panel can use it by mistake. `sources/zones.json` gives the same rule for the
roll-up, and `REFERENCE.md` section 1 gives the reason.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import analyse, config, log
from .collectors import ALL as COLLECTORS

# The last days that the portal shows at the native step of the publisher.
RECENT_DAYS_IN_EXPORT = 14

# The last days that `daily_all.json` holds for every country. The portal
# offers an analysis window of up to 365 days, and the file must cover it.
DAILY_ALL_DAYS = 400

# The last days that `hours.json` holds for every country. The workload
# calculator compares every country at every hour, so it needs this file.
HOURS_ALL_DAYS = 30

# `latest.json` keeps every country, and marks the old rows. A country gets
# `stale = true` when its newest record is more than this many hours behind
# the newest record **of the same source**. The store holds a value of 2017
# for Cyprus, and a file called `latest` must not offer it as the grid of
# today.
#
# The size of the window: REFERENCE.md section 2 measures the normal lag. At
# the newest hour of the store 1 country of 33 has a record, and 5 hours
# before it 29 of 33 have one. The measured spread across the countries of
# energy-charts on 2026-09-22 was 9.2 hours. So a lag of some hours is normal
# inside one source, and a lag of a full day is not.
LATEST_STALE_HOURS = 24


def _write(name: str, body: dict) -> Path:
    """Write one file, and replace the old one in one step.

    `atlas daily` writes these files while `atlas serve` gives them to a
    browser. Neither process takes a lock on the other. A plain write
    truncates the file first, so a reader in that moment gets a part of a
    file and a parse error. So the export writes a temporary file beside the
    target and then renames it. `os.replace` is one step on NTFS, so a reader
    gets the old file or the new file, and nothing between the two.
    """
    path = config.PORTAL_DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(body, separators=(",", ":"), default=str), encoding="utf-8")
    os.replace(temporary, path)
    return path


def run(store) -> list[Path]:
    """Write every portal file. It returns the paths."""
    logger = log.get("atlas.export")
    config.ensure_dirs()

    countries = [row[0] for row in store.query(
        "SELECT DISTINCT country FROM record_current ORDER BY country"
    )]

    written = [
        _write("meta.json", _meta(store, countries)),
        _write("monthly.json", _monthly(store)),
        _write("latest.json", _latest(store)),
        _write("health.json", _health(store)),
        _write("register.json", _register()),
        _write("daily_all.json", _daily_all(store)),
        _write("hours.json", _hours_all(store)),
        _write("profile.json", _profile(store)),
        _write("forecast.json", _forecast(store)),
        # The discrepancy measurement. `atlas measure` prints the same table.
        # `atlas/analyse.py` holds the query and the reason for it.
        _write("pairs.json", analyse.pairs(store)),
    ]

    for iso in countries:
        written.append(_write(f"daily/{iso}.json", _daily(store, iso)))
        written.append(_write(f"recent/{iso}.json", _recent(store, iso)))

    # A country that leaves the store must not leave a stale file behind. The
    # sweep runs after the loop, and it removes only the files that this run
    # did not write. A sweep before the loop takes away files that the portal
    # still asks for, for as long as the export runs.
    keep = {f"{iso}.json" for iso in countries}
    for folder in ("daily", "recent"):
        directory = config.PORTAL_DATA_DIR / folder
        if not directory.is_dir():
            continue
        for stale in directory.iterdir():
            if stale.is_file() and stale.name not in keep:
                stale.unlink(missing_ok=True)

    total = sum(path.stat().st_size for path in written)
    largest = max(written, key=lambda path: path.stat().st_size)
    logger.info(
        "export %d file(s), %.1f MB, largest %s at %.0f kB",
        len(written), total / 1e6, largest.name, largest.stat().st_size / 1e3,
    )
    return written


def _meta(store, countries: list[str]) -> dict:
    rows = store.query(
        """
        SELECT source_id, count(*) AS rows, count(DISTINCT country) AS countries,
               min(ts_utc) AS first_ts, max(ts_utc) AS last_ts,
               string_agg(DISTINCT unit, ' / ') AS units
        FROM record_current
        WHERE kind = 'actual'
        GROUP BY source_id ORDER BY source_id
        """
    )
    sources = []
    for source_id, count, country_count, first_ts, last_ts, units in rows:
        entry = config.sources().get(source_id, {})
        sources.append(
            {
                "source_id": source_id,
                "name": entry.get("name", source_id),
                "operator": entry.get("operator"),
                "site_url": entry.get("site_url"),
                "docs_url": entry.get("docs_url"),
                "licence": entry.get("licence"),
                "attribution": entry.get("attribution"),
                "basis": (entry.get("methodology") or {}).get("basis"),
                "scope": (entry.get("methodology") or {}).get("scope"),
                # ⚠ The unit comes from the stored rows, and not from the
                # register. A panel that labels a chart must use the unit of
                # the value it draws. energy-charts gives gCO2eq/kWh, and NESO,
                # RTE and Energinet give gCO2/kWh. This key and the one in
                # `countries[].sources` are the only units the export writes.
                "unit": units,
                "rows": count,
                "countries": country_count,
                "first_ts_utc": first_ts,
                "last_ts_utc": last_ts,
            }
        )

    per_country = store.query(
        """
        SELECT country, count(*) AS rows, min(ts_utc) AS lo, max(ts_utc) AS hi
        FROM record_current WHERE kind = 'actual'
        GROUP BY country ORDER BY country
        """
    )
    # The same country, one line for each source. A panel that names a source
    # must never show the row count of another source.
    #
    # ⚠ The unit and the granularity come with the rows. A panel must not
    # assume `native`: Energinet gives DK1 and DK2, and the collector rolls the
    # two up, so Denmark is `aggregated`. REFERENCE.md section 1 gives the tags.
    per_country_source = store.query(
        """
        SELECT country, source_id, count(*) AS rows,
               min(ts_utc) AS lo, max(ts_utc) AS hi,
               string_agg(DISTINCT unit, ' / ') AS units,
               string_agg(DISTINCT granularity, ' / ') AS granularities
        FROM record_current WHERE kind = 'actual'
        GROUP BY country, source_id ORDER BY country, source_id
        """
    )
    by_country: dict[str, dict] = {}
    for iso, source_id, count, lo, hi, units, granularities in per_country_source:
        by_country.setdefault(iso, {})[source_id] = {
            "rows": count,
            "first_ts_utc": lo,
            "last_ts_utc": hi,
            "unit": units,
            "granularity": granularities,
        }
    names = {entry["iso"]: entry["name"] for entry in config.countries()}
    span = store.query(
        """
        SELECT min(ts_utc), max(ts_utc) FROM record_current
        WHERE metric = 'intensity' AND kind = 'actual'
        """
    )
    first_ts, last_ts = span[0] if span else (None, None)

    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "first_ts_utc": first_ts,
        "last_ts_utc": last_ts,
        "note": (
            "Every mean in these files is a time mean of the records in the "
            "period. It is not weighted by demand."
        ),
        "collectors": sorted(COLLECTORS),
        "sources": sources,
        "countries": [
            {
                "iso": iso,
                "name": names.get(iso, iso),
                "rows": count,
                "first_ts_utc": lo,
                "last_ts_utc": hi,
                "sources": by_country.get(iso, {}),
            }
            for iso, count, lo, hi in per_country
        ],
        "counts": store.counts(),
    }


def _monthly(store) -> dict:
    rows = store.query(
        """
        SELECT country, source_id, strftime(ts_utc, '%Y-%m') AS month,
               count(*) AS n,
               round(avg(value), 2) AS mean_unweighted,
               round(min(value), 2) AS lo,
               round(max(value), 2) AS hi,
               round(quantile_cont(value, 0.5), 2) AS median
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
        GROUP BY country, source_id, strftime(ts_utc, '%Y-%m')
        ORDER BY country, source_id, month
        """
    )
    return {
        "fields": ["country", "source_id", "month", "n", "mean_unweighted", "lo", "hi", "median"],
        "rows": [list(row) for row in rows],
    }


def _latest(store) -> dict:
    """The newest record of each country and source, with its age.

    ⚠ **A row here is the newest record of that country, and not a record of
    now.** A country that the source stopped to report keeps its last value for
    ever. The store holds 2017-06-10 for Cyprus and 2025-04-20 for Georgia,
    beside a record of this morning for Denmark. So the file keeps every row,
    and gives the age of each one. It drops nothing, because a reader must be
    able to see the gap.

    `age_hours` is the distance of the row behind the newest record **of the
    same source**, which `source_last_ts_utc` gives. `stale` is true when
    `age_hours` is more than `stale_after_hours`. A ranking must drop the stale
    rows first. REFERENCE.md section 2.

    ⚠ The age is relative to the source, so a source that stopped as a whole
    shows an age of 0 for all its countries. `health.json` and `last_ts_utc` in
    `meta.json` give the state of the collection itself.
    """
    rows = store.query(
        """
        SELECT country, source_id, ts_utc, value
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
        QUALIFY row_number() OVER (
          PARTITION BY country, source_id ORDER BY ts_utc DESC
        ) = 1
        ORDER BY country, source_id
        """
    )
    reference = {
        source_id: last
        for source_id, last in store.query(
            """
            SELECT source_id, max(ts_utc) FROM record_current
            WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
            GROUP BY source_id
            """
        )
    }
    out = []
    for country, source_id, ts_utc, value in rows:
        last = reference.get(source_id)
        if last is None or ts_utc is None:
            age = None
            stale = None
        else:
            age = round((last - ts_utc).total_seconds() / 3600, 1)
            stale = age > LATEST_STALE_HOURS
        out.append([country, source_id, ts_utc, value, age, stale])
    return {
        "source_last_ts_utc": reference,
        "stale_after_hours": LATEST_STALE_HOURS,
        "fields": ["country", "source_id", "ts_utc", "value", "age_hours", "stale"],
        "rows": out,
    }


def _daily(store, iso: str) -> dict:
    rows = store.query(
        """
        SELECT source_id, CAST(ts_utc AS DATE) AS day,
               count(*) AS n,
               round(avg(value), 2) AS mean_unweighted,
               round(min(value), 2) AS lo,
               round(max(value), 2) AS hi
        FROM record_current
        WHERE country = ? AND metric = 'intensity' AND kind = 'actual'
          AND value IS NOT NULL
        GROUP BY source_id, CAST(ts_utc AS DATE)
        ORDER BY source_id, day
        """,
        [iso],
    )
    return {
        "country": iso,
        "fields": ["source_id", "day", "n", "mean_unweighted", "lo", "hi"],
        "rows": [list(row) for row in rows],
    }


def _recent(store, iso: str) -> dict:
    """The last RECENT_DAYS_IN_EXPORT days of one country, at the native step.

    ⚠ The window ends at the newest **actual** record of the country, and not
    at the newest record. `atlas snap` stores a forward curve that reaches days
    into the future. A window that ends there starts in the future too, and the
    file then holds fewer days than the `days` key declares.
    """
    rows = store.query(
        f"""
        SELECT source_id, ts_utc, value
        FROM record_current
        WHERE country = ? AND metric = 'intensity' AND kind = 'actual'
          AND value IS NOT NULL
          AND ts_utc >= (
            SELECT max(ts_utc) FROM record_current
            WHERE country = ? AND metric = 'intensity' AND kind = 'actual'
          ) - INTERVAL {RECENT_DAYS_IN_EXPORT} DAY
        ORDER BY source_id, ts_utc
        """,
        [iso, iso],
    )
    return {
        "country": iso,
        "days": RECENT_DAYS_IN_EXPORT,
        "fields": ["source_id", "ts_utc", "value"],
        "rows": [list(row) for row in rows],
    }


# --- health.json, and the coverage model --------------------------------------

# The per-day shape of every actual series. One scan gives the count, the step,
# the first and the last record of the day, and the widest interval that ends
# in the day.
#
# ⚠ `lag` partitions by the series and not by the day, so the interval of the
# first record of a day reaches back to the last record of the day before. A
# hole that crosses midnight is therefore one interval and not two.
_COVERAGE_SQL = """
WITH base AS (
  SELECT source_id, country, ts_utc, CAST(ts_utc AS DATE) AS day
  FROM record_current
  WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
), stepped AS (
  SELECT source_id, country, day, ts_utc,
         date_diff('minute', lag(ts_utc) OVER w, ts_utc) AS step
  FROM base
  WINDOW w AS (PARTITION BY source_id, country ORDER BY ts_utc)
)
SELECT source_id, country, day,
       count(*)                       AS n,
       mode(step) FILTER (step > 0)   AS step_minutes,
       min(ts_utc)                    AS first_ts,
       max(ts_utc)                    AS last_ts,
       max(step)                      AS widest,
       arg_max(ts_utc, step)          AS widest_end
FROM stepped
GROUP BY source_id, country, day
ORDER BY source_id, country, day
"""

# A day step above this is a hole and not a step. The guard stops one day with
# one record after a long hole from becoming the step of the days that follow.
_MINUTES_IN_DAY = 1440


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time())


def _series_coverage(days: list[tuple]) -> dict:
    """The coverage of one series, from the rows of `_COVERAGE_SQL`.

    Each row is (day, records, step_minutes, first_ts, last_ts, widest,
    widest_end), in day order.

    ⚠ The expected count uses the step that the data shows, day by day. It
    never uses `resolution_minutes_observed` from the register. 14 energy-charts
    countries changed their step inside their span: NL on 2016-01-03, RO on
    2022-01-02, ES on 2023-01-01, FI on 2023-12-31, CZ, HR and PL on 2024-12-29,
    and DK, EE, FR, IT, LT, NO and SE on 2025-12-28. RTE FR went from 30 to 15
    minutes on 2026-06-30, and CY ran at 30 minutes and now runs at 60. The
    register value is right for today and wrong for the history. On 2026-09-23
    the fixed-step model reports 35.35 % absence across the store, and this
    model reports 219,700 of 6,805,707, which is 3.23 %.

    The expected count runs from the first record to the last one, and not from
    the first day to the last day. A part day at each end therefore costs
    nothing, because the publisher never held those periods.

    ⚠ `absent` can hold a small negative number. The day of a step change holds
    both steps, and the modal step of that day then expects fewer periods than
    the day holds. On 2026-09-23 there are two: NL at −2 and PL at −3. A
    negative figure marks a step change, and it is not a surplus of records.
    On the same day AT, BE, DE, MD and PT read 0, and they are complete against
    their own step.
    """
    records = sum(row[1] for row in days)
    first_ts = days[0][3]
    last_ts = days[-1][4]

    # The step of a day is the modal interval between its records. The step of
    # the series weights each day by its records, so a series that ran 10 years
    # at 60 minutes and one month at 30 reports 60.
    step_of_day = {
        row[0]: row[2] for row in days if row[2] and 0 < row[2] <= _MINUTES_IN_DAY
    }
    weight: dict[int, int] = {}
    for row in days:
        if row[0] in step_of_day:
            weight[row[2]] = weight.get(row[2], 0) + row[1]
    modal = max(weight, key=lambda step: (weight[step], -step)) if weight else None

    widest = 0
    widest_end = None
    for row in days:
        if row[5] and row[5] > widest:
            widest, widest_end = row[5], row[6]

    out = {
        "records": records,
        "expected": None,
        "absent": None,
        "step_minutes": modal,
        "hole_from": None,
        "hole_to": None,
        "hole_hours": None,
    }
    if widest_end is not None:
        out["hole_from"] = widest_end - timedelta(minutes=widest)
        out["hole_to"] = widest_end
        out["hole_hours"] = round(widest / 60, 1)
    if modal is None:
        return out  # One record. There is no interval, so there is no model.

    expected = 0
    step = modal
    end_day = last_ts.date()
    day = first_ts.date()
    while day <= end_day:
        step = step_of_day.get(day, step)
        start = first_ts if day == first_ts.date() else _midnight(day)
        stop = last_ts if day == end_day else _midnight(day + timedelta(days=1))
        minutes = int((stop - start).total_seconds() // 60)
        if day == end_day:
            expected += minutes // step + 1     # the last record holds a slot
        else:
            expected += -(-minutes // step)     # up to midnight, and not past
        day += timedelta(days=1)

    out["expected"] = expected
    out["absent"] = expected - records
    return out


def _health(store) -> dict:
    """The run table, the records against the expected records, and the hole.

    ⚠ A row of days counts request-days, and it states no shortfall. MEASURED
    2026-09-23, from this file: Energinet DK reads `days_ok` 3,554 with
    `days_empty` 0 and `days_fail` 0, and it is short by 904 stamps. CY reads
    `first_day` 2015-07-27 and `last_day` 2026-09-23, and it holds a hole of
    more than 9 years between the two. So this file also carries the records,
    the expected records at the observed step, the shortfall and the widest
    hole. DK now reads 1,022,132 of 1,023,036, and CY 27,925 of 194,962.

    `hole_from` and `hole_to` are the two records that stand on each side of
    the widest hole, and `hole_hours` is the distance between them. A series
    with no hole reports its own step there, so a reader compares `hole_hours`
    against `step_minutes`.

    The coverage model runs for `kind = 'actual'` only. A forecast series
    holds many runs of one timestamp, so a step and an expected count mean
    nothing there. Those rows carry the record count and nothing else.

    ⚠ `an_error` keeps its rule: it names a day that failed. A dropped point
    sits on a run row with the status `ok`, so it never reaches that column.
    The Elia zeros and the Energinet stamps with no weight are dropped points.
    `a_note` carries the newest message of a run row that did not fail, so the
    two live defects of the store are visible in the file that reports health.
    A dropped point writes a message there. A day that the publisher answered
    with no content writes one too, and `energy-charts-co2eq` MD forecast shows
    `HTTP 404` in that column.
    """
    rows = store.query(
        """
        WITH last AS (
          SELECT source_id, country, day, kind, status, rows, error, finished_at
          FROM run
          QUALIFY row_number() OVER (
            PARTITION BY source_id, country, day, kind ORDER BY finished_at DESC
          ) = 1
        )
        SELECT source_id, country, kind,
               count(*) FILTER (status = 'ok')    AS days_ok,
               count(*) FILTER (status = 'empty') AS days_empty,
               count(*) FILTER (status = 'fail')  AS days_fail,
               min(day) FILTER (status = 'ok')    AS first_day,
               max(day) FILTER (status = 'ok')    AS last_day,
               max(finished_at)                   AS last_run_at,
               any_value(error) FILTER (status = 'fail') AS an_error,
               arg_max(error, finished_at)
                 FILTER (status <> 'fail' AND error IS NOT NULL) AS a_note
        FROM last
        GROUP BY source_id, country, kind
        ORDER BY source_id, country, kind
        """
    )

    held = {
        (source_id, iso, kind): count
        for source_id, iso, kind, count in store.query(
            """
            SELECT source_id, country, kind, count(*)
            FROM record_current
            WHERE metric = 'intensity' AND value IS NOT NULL
            GROUP BY source_id, country, kind
            """
        )
    }

    per_series: dict[tuple[str, str], list[tuple]] = {}
    for source_id, iso, *rest in store.query(_COVERAGE_SQL):
        per_series.setdefault((source_id, iso), []).append(tuple(rest))
    coverage = {key: _series_coverage(days) for key, days in per_series.items()}

    out = []
    for row in rows:
        source_id, iso, kind = row[0], row[1], row[2]
        model = coverage.get((source_id, iso)) if kind == "actual" else None
        model = model or {}
        out.append(
            list(row)
            + [
                held.get((source_id, iso, kind), 0),
                model.get("expected"),
                model.get("absent"),
                model.get("step_minutes"),
                model.get("hole_from"),
                model.get("hole_to"),
                model.get("hole_hours"),
            ]
        )
    return {
        "note": (
            "`expected` counts the periods between the first record and the last "
            "one, at the step that the data shows day by day. `hole_from` and "
            "`hole_to` are the records on each side of the widest hole."
        ),
        "fields": [
            "source_id", "country", "kind", "days_ok", "days_empty", "days_fail",
            "first_day", "last_day", "last_run_at", "an_error", "a_note",
            "records", "expected", "absent", "step_minutes",
            "hole_from", "hole_to", "hole_hours",
        ],
        "rows": out,
    }


def _register() -> dict:
    """The source register and the zone model, copied whole.

    The portal must not read `sources/*.json` directly. A browser that opens
    the portal folder can not reach a file above it. So the export copies both
    registers. It copies them whole and changes nothing, because a distilled
    copy can drift from the file that the collectors read.
    """
    return {
        "sources": json.loads(config.SOURCES_JSON.read_text(encoding="utf-8")),
        "zones": json.loads(config.ZONES_JSON.read_text(encoding="utf-8")),
    }


def _last_actual_ts(store) -> datetime | None:
    rows = store.query(
        "SELECT max(ts_utc) FROM record_current WHERE metric = 'intensity' AND kind = 'actual'"
    )
    return rows[0][0] if rows else None


def _daily_all(store) -> dict:
    """Every country, one daily mean for each of the last DAILY_ALL_DAYS days.

    The value at index `i` is the day `start_day + i`. A day with no record
    holds null. The portal reads the array and does not search.

    ⚠ The file is keyed by source first: `sources[<source_id>][<ISO>]`. Do not
    put a key beside an ISO code, because a panel counts those keys to get the
    countries of a source.

    Each country holds a fourth array, `n`: the count of records that made the
    day. It is not in `series`, because it is a count and not a value. The last
    day of the store is always a part day, and a mean of 6 records can win an
    extreme against a full day of 96. A panel must read `n` before it calls a
    day the highest or the lowest. REFERENCE.md, section *A part day is not a
    day*.
    """
    last = _last_actual_ts(store)
    if last is None:
        return {
            "start_day": None,
            "end_day": None,
            "days": 0,
            "series": ["mean_unweighted", "lo", "hi"],
            "counts": "n",
            "sources": {},
        }

    end_day: date = last.date()
    start_day = end_day - timedelta(days=DAILY_ALL_DAYS - 1)
    rows = store.query(
        """
        SELECT source_id, country, CAST(ts_utc AS DATE) AS day,
               round(avg(value), 1) AS mean_unweighted,
               round(min(value), 1) AS lo,
               round(max(value), 1) AS hi,
               count(*) AS n
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
          AND CAST(ts_utc AS DATE) >= ?
        GROUP BY source_id, country, CAST(ts_utc AS DATE)
        """,
        [start_day],
    )
    out: dict[str, dict] = {}
    for source_id, iso, day, mean, lo, hi, count in rows:
        index = (day - start_day).days
        if not (0 <= index < DAILY_ALL_DAYS):
            continue
        series = out.setdefault(source_id, {}).setdefault(
            iso,
            {
                "mean_unweighted": [None] * DAILY_ALL_DAYS,
                "lo": [None] * DAILY_ALL_DAYS,
                "hi": [None] * DAILY_ALL_DAYS,
                "n": [None] * DAILY_ALL_DAYS,
            },
        )
        series["mean_unweighted"][index] = mean
        series["lo"][index] = lo
        series["hi"][index] = hi
        series["n"][index] = count
    return {
        "start_day": start_day.isoformat(),
        "end_day": end_day.isoformat(),
        "days": DAILY_ALL_DAYS,
        "series": ["mean_unweighted", "lo", "hi"],
        "counts": "n",
        "sources": out,
    }


def _hours_all(store) -> dict:
    """Every country, one mean for each hour of the last HOURS_ALL_DAYS days.

    The workload calculator moves a run between countries hour by hour, so it
    needs every country at one time. The value at index `i` is the hour
    `start_hour + i`, in UTC.
    """
    last = _last_actual_ts(store)
    if last is None:
        return {
            "start_hour_utc": None,
            "end_hour_utc": None,
            "hours": 0,
            "days": HOURS_ALL_DAYS,
            "sources": {},
        }

    count = HOURS_ALL_DAYS * 24
    end_hour = last.replace(minute=0, second=0, microsecond=0)
    start_hour = end_hour - timedelta(hours=count - 1)
    rows = store.query(
        """
        SELECT source_id, country, date_trunc('hour', ts_utc) AS hour,
               round(avg(value), 1)
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
          AND ts_utc >= ?
        GROUP BY source_id, country, date_trunc('hour', ts_utc)
        """,
        [start_hour],
    )
    out: dict[str, dict] = {}
    for source_id, iso, hour, mean in rows:
        index = int((hour - start_hour).total_seconds() // 3600)
        if 0 <= index < count:
            out.setdefault(source_id, {}).setdefault(iso, [None] * count)[index] = mean
    return {
        "start_hour_utc": start_hour.isoformat(sep=" "),
        "end_hour_utc": end_hour.isoformat(sep=" "),
        "hours": count,
        "days": HOURS_ALL_DAYS,
        "sources": out,
    }


def _profile(store) -> dict:
    """Every country, the mean of each hour of the day in each month.

    This is the shape of the year and the shape of the day in one table. It
    uses all the history in the store, so the depth of a month is the history
    of that source. `first_ts_utc` in `meta.json` gives that depth.
    `grid[month - 1][hour]` is the mean. `records[month - 1]` is the number of
    records that made the month.

    ⚠ The hour is UTC. A country that is 2 hours ahead of UTC in the summer
    has its solar dip near 10:00 in this grid, and not near 12:00.
    """
    rows = store.query(
        """
        SELECT source_id, country, month(ts_utc) AS m, hour(ts_utc) AS h,
               round(avg(value), 1), count(*)
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
        GROUP BY source_id, country, month(ts_utc), hour(ts_utc)
        """
    )
    out: dict[str, dict] = {}
    for source_id, iso, month, hour, mean, count in rows:
        entry = out.setdefault(source_id, {}).setdefault(
            iso, {"grid": [[None] * 24 for _ in range(12)], "records": [0] * 12}
        )
        entry["grid"][month - 1][hour] = mean
        entry["records"][month - 1] += count
    return {
        "hour_basis": "UTC",
        "note": (
            "The mean of every record of that hour and that month, across all the "
            "years in the store. The hour is UTC and not local time."
        ),
        "sources": out,
    }


def _forecast(store) -> dict:
    """The newest forward curve of each country.

    A publisher replaces its forecast with the next run and keeps no history,
    so the store holds each run that `atlas snap` captured. This file holds the
    newest run of each country. FORECASTS.md, section 3.
    """
    rows = store.query(
        """
        SELECT country, source_id, run_at, ts_utc, value, horizon_min
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'forecast' AND value IS NOT NULL
        QUALIFY dense_rank() OVER (
          PARTITION BY country, source_id ORDER BY run_at DESC
        ) = 1
        ORDER BY country, source_id, ts_utc
        """
    )
    runs = store.query(
        """
        SELECT source_id, count(DISTINCT run_at) AS runs, count(*) AS points,
               min(run_at) AS first_run, max(run_at) AS last_run
        FROM record_current
        WHERE metric = 'intensity' AND kind = 'forecast'
        GROUP BY source_id ORDER BY source_id
        """
    )
    return {
        "note": (
            "The newest captured run of each country. A score against the "
            "measurement needs more than one run."
        ),
        "fields": ["country", "source_id", "run_at", "ts_utc", "value", "horizon_min"],
        "rows": [list(row) for row in rows],
        "runs_in_store": {
            "fields": ["source_id", "runs", "points", "first_run", "last_run"],
            "rows": [list(row) for row in runs],
        },
    }
