"""The shared runner.

It owns everything that is the same for every source: the to-do list, the
request windows, the raw write, the parse call, the duplicate check and the
run rows. A collector module holds only `fetch` and `parse`.
REFERENCE.md sections 5 and 6.

`atlas backfill` and `atlas daily` call the same function with a different
date range. The run table makes both of them idempotent and restartable.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from . import log
from .collectors.base import ParseContext
from .model import FetchError, ParseError, RunRow
from .raw import write as write_raw

DAY = timedelta(days=1)

# A window that gets one of these status codes splits in two, and each half
# goes again. The measurement of 2026-09-17: energy-charts answers HTTP 500 for
# some periods of Cyprus, Denmark, Estonia, Georgia, Moldova and Kosovo, and
# HTTP 200 for other periods of the same country. One request for 11 years
# therefore loses the whole country. A split keeps the good years.
SPLIT_STATUS = (500, 502, 503, 504)

# The number of extra requests that one window can use for the splits. A
# country that fails everywhere stops after this count, and the days get a
# `fail` row. Without a budget, a bisection to single days needs 4,127
# requests, which is 34 hours at 2 requests each minute.
SPLIT_BUDGET = 12

# A window of this many days or fewer does not split again.
MIN_SPLIT_DAYS = 8


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def group_days(days: list[date], max_span: int) -> list[tuple[date, date]]:
    """Make request windows from a list of days.

    Days that follow each other go in one window. A window never holds more
    than `max_span` days.
    """
    windows: list[tuple[date, date]] = []
    if not days:
        return windows
    first = previous = days[0]
    for day in days[1:]:
        follows = day == previous + DAY
        room = (day - first).days + 1 <= max_span
        if follows and room:
            previous = day
            continue
        windows.append((first, previous))
        first = previous = day
    windows.append((first, previous))
    return windows


def _dropped_note(context) -> str | None:
    """The run-row text for the points that a guard refused. See `base.py`."""
    if not context.dropped:
        return None
    text = f"{len(context.dropped)} point(s) dropped. First: {context.dropped[0]}"
    return text[:500]


def _can_split(error, window: tuple[date, date], budget: list[int]) -> bool:
    """True when a failed window goes again as two halves."""
    if error.http_status not in SPLIT_STATUS:
        return False
    if (window[1] - window[0]).days + 1 <= MIN_SPLIT_DAYS:
        return False
    return budget[0] >= 2


def _split(store, http, collector, iso, window, logger, budget) -> dict:
    """Cut a window in two, and collect each half.

    The two halves take 2 from the budget of the top window. A country that
    answers with a server error for every period runs out of budget, and the
    days get a `fail` row. A country with one bad year keeps the other years.
    """
    budget[0] -= 2
    span = (window[1] - window[0]).days + 1
    middle = window[0] + timedelta(days=span // 2)
    halves = ((window[0], middle - DAY), (middle, window[1]))
    logger.warning(
        "%s %s %s..%s: the server failed. The window splits into %s..%s and %s..%s.",
        collector.source_id, iso, window[0], window[1],
        halves[0][0], halves[0][1], halves[1][0], halves[1][1],
    )

    total = {"new": 0, "revisions": 0, "fail": 0, "empty": 0}
    for half in halves:
        outcome = _one_window(store, http, collector, iso, half, logger, budget)
        for key in total:
            total[key] += outcome.get(key, 0)
    return total


def _runs_for_window(
    source_id: str,
    iso: str,
    kind: str,
    window: tuple[date, date],
    per_day: Counter,
    status: str,
    started: datetime,
    finished: datetime,
    http_status: int | None = None,
    error: str | None = None,
    raw_ref: str | None = None,
) -> list[RunRow]:
    """One run row for each day in the window."""
    rows = []
    day = window[0]
    while day <= window[1]:
        count = per_day.get(day, 0)
        rows.append(
            RunRow(
                source_id=source_id,
                country=iso,
                day=day,
                kind=kind,
                status=status if status != "ok" else ("ok" if count else "empty"),
                rows=count,
                http_status=http_status,
                error=error,
                raw_ref=raw_ref,
                started_at=started,
                finished_at=finished,
            )
        )
        day += DAY
    return rows


def collect_measurements(
    store,
    http,
    collector,
    isos: list[str],
    start: date,
    end: date,
    force_recent_days: int = 0,
    retry_fail_days: int = 1_000_000,
) -> dict:
    """Collect the actual series of one source, for a list of countries."""
    logger = log.get("atlas.runner")
    source_id = collector.source_id
    first_day = max(start, collector.available_from)
    summary = {"windows": 0, "new": 0, "revisions": 0, "fail": 0, "empty": 0}

    for iso in isos:
        days = store.days_to_collect(
            source_id,
            iso,
            "actual",
            first_day,
            end + DAY,  # `range` in DuckDB stops before the end value
            force_recent_days=force_recent_days,
            retry_fail_days=retry_fail_days,
        )
        days = [day for day in days if first_day <= day <= end]
        windows = group_days(days, collector.max_span_days)
        if not windows:
            logger.info("%s %s: nothing to collect", source_id, iso)
            continue

        logger.info(
            "%s %s: %d day(s) in %d window(s)", source_id, iso, len(days), len(windows)
        )
        for window in windows:
            summary["windows"] += 1
            budget = [SPLIT_BUDGET]
            outcome = _one_window(store, http, collector, iso, window, logger, budget)
            for key in ("new", "revisions", "fail", "empty"):
                summary[key] += outcome.get(key, 0)

    return summary


def _one_window(store, http, collector, iso, window, logger, budget=None) -> dict:
    """One request, one raw file, one parse, one insert, and the run rows.

    A server error splits the window. See `_split`.
    """
    source_id = collector.source_id
    started = _now()
    # `new` and `revisions` count records. `fail` and `empty` count days.
    result = {"new": 0, "revisions": 0, "fail": 0, "empty": 0}
    if budget is None:
        budget = [SPLIT_BUDGET]

    # A window that the runner can split gets one try. A split answers a server
    # error better than a second try of the same big question.
    span = (window[1] - window[0]).days + 1
    splittable = span > MIN_SPLIT_DAYS and budget[0] >= 2

    try:
        status, payload = collector.fetch(
            http, iso, window[0], window[1], tries=1 if splittable else None
        )
    except FetchError as error:
        empty = error.http_status in getattr(collector, "empty_http_status", ())
        if not empty and _can_split(error, window, budget):
            return _split(store, http, collector, iso, window, logger, budget)

        finished = _now()
        state = "empty" if empty else "fail"
        level = logger.info if empty else logger.error
        level("%s %s %s..%s: %s", source_id, iso, window[0], window[1], error)
        store.write_runs(
            _runs_for_window(
                source_id, iso, "actual", window, Counter(), state, started, finished,
                http_status=error.http_status, error=str(error)[:500],
            )
        )
        result["empty" if empty else "fail"] = (window[1] - window[0]).days + 1
        return result

    collected_at = _now()
    raw_ref = write_raw(source_id, iso, payload, collected_at)

    context = ParseContext(kind="actual", collected_at=collected_at, raw_ref=raw_ref)
    try:
        records = collector.parse(payload, iso, context)
    except ParseError as error:
        finished = _now()
        logger.error("%s %s %s..%s: %s", source_id, iso, window[0], window[1], error)
        store.write_runs(
            _runs_for_window(
                source_id, iso, "actual", window, Counter(), "fail", started, finished,
                http_status=status, error=str(error)[:500], raw_ref=raw_ref,
            )
        )
        result["fail"] = (window[1] - window[0]).days + 1
        return result

    # A payload can reach past the window that the runner asked for. Only the
    # days of the window get a run row, but every record goes in the store.
    per_day = Counter(record.ts_utc.date() for record in records)
    new, revisions = store.insert_records(records)
    finished = _now()

    note = _dropped_note(context)
    if note:
        logger.warning("%s %s %s..%s: %s", source_id, iso, window[0], window[1], note)

    # The run rows are the single count of the days. `_runs_for_window` turns a
    # day with no record into an `empty` row, so the summary reads the rows
    # back instead of counting the days a second time here.
    rows = _runs_for_window(
        source_id, iso, "actual", window, per_day, "ok", started, finished,
        http_status=status, raw_ref=raw_ref, error=note,
    )
    store.write_runs(rows)
    logger.info(
        "%s %s %s..%s: %d record(s), %d new, %d revision(s)",
        source_id, iso, window[0], window[1], len(records), new, revisions,
    )
    result["new"] = new
    result["revisions"] = revisions
    result["empty"] = sum(1 for row in rows if row.status == "empty")
    return result


def snap_forecasts(store, http, collector, isos: list[str]) -> dict:
    """Capture the forward forecast curve of one source, for each country.

    `run_at` comes from the clock of this process, and not from the schedule.
    So a late snapshot still gives an exact horizon. RUNNING.md §3.
    """
    logger = log.get("atlas.runner")
    source_id = collector.source_id
    summary = {"countries": 0, "new": 0, "fail": 0, "empty": 0}

    if not getattr(collector, "has_forecast_curve", False):
        logger.info("%s publishes no forward curve. The snapshot skips it.", source_id)
        return summary

    run_at = _now()
    today = run_at.date()
    start, end = collector.snap_window(today)

    for iso in isos:
        summary["countries"] += 1
        started = _now()
        try:
            status, payload = collector.fetch(http, iso, start, end)
        except FetchError as error:
            # The same rule as `_one_window`: a status code that the collector
            # names as "no content" is an `empty` day, and not a failure.
            # energy-charts answers 404 for a country with no forward curve.
            empty = error.http_status in getattr(collector, "empty_http_status", ())
            state = "empty" if empty else "fail"
            level = logger.info if empty else logger.error
            level("%s %s snapshot: %s", source_id, iso, error)
            store.write_runs([
                RunRow(
                    source_id=source_id, country=iso, day=today, kind="forecast",
                    run_at=run_at, status=state, started_at=started, finished_at=_now(),
                    http_status=error.http_status, error=str(error)[:500],
                )
            ])
            summary[state] += 1
            continue

        collected_at = _now()
        # The snapshot goes under the source id of the collector, and the file
        # name carries `-snap`. So every directory in `store/raw/` is a source
        # id that `config.source()` knows.
        raw_ref = write_raw(source_id, iso + "-snap", payload, collected_at)
        context = ParseContext(
            kind="forecast", collected_at=collected_at, raw_ref=raw_ref, run_at=run_at
        )
        try:
            records = collector.parse(payload, iso, context)
        except ParseError as error:
            logger.error("%s %s snapshot: %s", source_id, iso, error)
            store.write_runs([
                RunRow(
                    source_id=source_id, country=iso, day=today, kind="forecast",
                    run_at=run_at, status="fail", started_at=started, finished_at=_now(),
                    http_status=status, error=str(error)[:500], raw_ref=raw_ref,
                )
            ])
            summary["fail"] += 1
            continue

        new, _revisions = store.insert_records(records)
        note = _dropped_note(context)
        if note:
            logger.warning("%s %s snapshot: %s", source_id, iso, note)
        state = "ok" if records else "empty"
        store.write_runs([
            RunRow(
                source_id=source_id, country=iso, day=today, kind="forecast",
                run_at=run_at, status=state,
                rows=len(records), started_at=started, finished_at=_now(),
                http_status=status, raw_ref=raw_ref, error=note,
            )
        ])
        logger.info("%s %s snapshot: %d forecast point(s)", source_id, iso, len(records))
        summary["new"] += new
        if state == "empty":
            summary["empty"] += 1

    return summary
