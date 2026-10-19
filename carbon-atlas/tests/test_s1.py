"""The offline tests of the atlas package. They make no network request.

    python tests/test_s1.py

Every test uses a temporary store, so it never touches `store/atlas.duckdb`.
A green run removes that temporary store again. A red run keeps it, so a
failed check can be opened in the DuckDB file.

⚠ How a failure gets out of this file. `check` counts a failed check and goes
on, so one run reports every failed check and not the first one only. The
`section` decorator then raises at the end of a section that holds a failed
check. `main` catches that and runs the next section, so the direct run still
does the whole file and prints one summary. pytest calls the sections itself,
so it sees the raise and reports that section red. A suite that cannot fail
is worse than no suite.

The sections, in the order that `main` runs them:

1.  the parse guards of energy-charts, and the duplicate guard
2.  the forecast parse: the horizon, and the drop of a negative horizon
3.  the revision rule: an equal value writes nothing, a different value writes
    revision + 1
4.  the to-do list: a `fail` day comes back, an old `empty` day does not
5.  the window grouping, and 5b the split of a window on HTTP 500
6.  the store lock: a second hold waits out, a lock file of a dead process is
    taken, a lock file of a live process stays
7.  the registers: the country list and the API code come from zones.json
8.  the export: a dense file carries an index and not a key, so a value in the
    wrong cell is silent. The tests read a known cell back. 8b: the window of
    `recent/<ISO>.json` ends at the newest actual, and not at a forecast.
    8c: the pair table of `atlas/analyse.py`, on a fixture that a reader can
    check by hand. 8d: the coverage model of `health.json`, which counts the
    expected periods at the step that the data shows
9.  the other collectors, one section each: 9 NESO, 9b RTE, 9c Energinet and
    9d Elia, each with the publisher defect that it must survive. 9e: the
    shared zero guard of `base.py`, which NESO calls and Elia copies
10. the `--redo-ok` repair: the flag that reads an `ok` day again. Section 10
    parses the command, pins the arithmetic of `force_recent_days`, and shows
    that the refusal without `--from` comes before the lock. 10b: the day of
    `days_to_collect` that the flag reaches, and the day that it does not
11. two more properties of the coverage model: a negative `absent` on the day
    of a step change, and `hole_hours` as the coarse early step
12. `atlas rebuild`, in three sections. 12: the refusals, and the one that
    matters most is `--into` a directory that already holds a store. 12b: a
    payload that fails its hash, a payload that fails to parse, and the exit
    code that a script reads. 12c: the rebuilt rows against the parse of the
    collector itself, the forecast horizon, the run table and the meta marks
"""

from __future__ import annotations

import contextlib
import functools
import gzip
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The store path must change before the package reads it.
TEMP = Path(tempfile.mkdtemp(prefix="atlas-test-"))
os.environ["ATLAS_STORE"] = str(TEMP)

from atlas import config, raw, rebuild, runner  # noqa: E402
from atlas.collectors.base import ParseContext  # noqa: E402
from atlas.collectors.energy_charts_co2eq import COLLECTOR  # noqa: E402
from atlas.model import ParseError, Record, RunRow  # noqa: E402
from atlas.store import Store  # noqa: E402

PASSED = 0
FAILED = 0
FAILURES: list[str] = []


class SectionFailed(AssertionError):
    """A section holds at least one failed check.

    It is an `AssertionError`, so pytest reports it like any other failed
    test. `main` catches it and goes on to the next section.
    """


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {name}")
    else:
        FAILED += 1
        FAILURES.append(f"{name} {detail}".strip())
        print(f"  FAIL  {name} {detail}")


def section(function):
    """Make a failed check stop the section that holds it.

    The body runs to the end first, so every check of the section reports
    itself. The wrapper raises after it. ⚠ Without this, `check` only counts,
    and pytest reports a green run for a file full of failed checks, because
    pytest reads the raise and never the counters.
    """

    @functools.wraps(function)
    def wrapper() -> None:
        first = len(FAILURES)
        function()
        broken = FAILURES[first:]
        if broken:
            raise SectionFailed(
                f"{len(broken)} check(s) failed in {function.__name__}: "
                + " | ".join(broken)
            )

    return wrapper


def expect_parse_error(name: str, body: dict, kind: str = "actual") -> None:
    context = ParseContext(kind=kind, collected_at=datetime(2026, 9, 17), raw_ref="x")
    try:
        COLLECTOR.parse(json.dumps(body).encode(), "DE", context)
    except ParseError as error:
        check(name, True)
        print(f"        {str(error)[:90]}")
        return
    check(name, False, "the parse did not stop")


# 1789423200 is 2026-09-14T22:00:00Z. energy-charts starts a day at midnight
# local time, so the first point of 2026-09-15 in Germany is 22:00 UTC of the
# day before. The parser keeps UTC, and it makes no local day.
FIRST_TS = 1789423200
FIRST_UTC = datetime(2026, 9, 14, 22, 0)


def good_payload(values=None, stamps=None) -> dict:
    stamps = stamps or [FIRST_TS, FIRST_TS + 900]
    values = values if values is not None else [400.0, 410.0]
    return {
        "unix_seconds": stamps,
        "co2eq": values,
        "co2eq_forecast": [None] * len(stamps),
        "deprecated": False,
    }


# --- 1. The parse guards -----------------------------------------------------


@section
def test_guards() -> None:
    print("\n1. the parse guards")
    context = ParseContext(kind="actual", collected_at=datetime(2026, 9, 17), raw_ref="x")

    records = COLLECTOR.parse(json.dumps(good_payload()).encode(), "DE", context)
    check("a good payload parses", len(records) == 2, f"got {len(records)}")
    check("the unit comes from the collector", records[0].unit == "gCO2eq/kWh")
    check("the granularity is native", records[0].granularity == "native")
    check(
        "the timestamp is UTC with no zone",
        records[0].ts_utc == FIRST_UTC and records[0].ts_utc.tzinfo is None,
        str(records[0].ts_utc),
    )

    body = good_payload()
    body["co2eq_new_name"] = body.pop("co2eq")
    expect_parse_error("guard 1: a new field set stops the parse", body)

    # Guard 2 drops the point. It stops the payload only when many points fail.
    stamps = [FIRST_TS + 900 * i for i in range(200)]
    values = [400.0] * 200
    values[7] = -2.6  # the real Lithuania value of 2026-09-17
    context = ParseContext(kind="actual", collected_at=datetime(2026, 9, 17), raw_ref="x")
    records = COLLECTOR.parse(
        json.dumps(good_payload(values=values, stamps=stamps)).encode(), "DE", context
    )
    check("guard 2: one bad point drops, the payload stays", len(records) == 199,
          f"got {len(records)}")
    check("guard 2: the dropped point is recorded", len(context.dropped) == 1,
          str(context.dropped))
    check("the run note names the value", "-2.6" in (context.dropped[0] if context.dropped else ""))

    # 8 small negatives, the real Lithuania case. The payload must stay.
    lt = [80.0] * 98
    for index, bad in enumerate([-14.6, -12.2, -11.3, -11.0, -9.1, -2.6, -1.6, -0.9]):
        lt[index] = bad
    lt_context = ParseContext(
        kind="actual", collected_at=datetime(2026, 9, 17), raw_ref="x"
    )
    lt_records = COLLECTOR.parse(
        json.dumps(good_payload(values=lt, stamps=stamps[:98])).encode(), "LT", lt_context
    )
    check("guard 2: 8 small negatives keep the other 90 points", len(lt_records) == 90,
          f"got {len(lt_records)}")
    check("guard 2: all 8 are recorded", len(lt_context.dropped) == 8,
          str(len(lt_context.dropped)))

    # A unit error lands outside the absurd band, and it stops the payload.
    many = [400.0] * 200
    for i in range(10):
        many[i] = 400000.0
    expect_parse_error(
        "guard 2: a unit error stops the payload",
        good_payload(values=many, stamps=stamps),
    )

    # The field set stays the same, so this reaches guard 3 and not guard 1.
    body = good_payload()
    body["unix_seconds"] = None
    expect_parse_error("guard 3: no UTC column stops the parse", body)

    # ⚠ Guard 4 gives two answers here, and the difference matters. One
    # instant with one value two times is one measurement written two times,
    # so one copy stays and the payload stays. One instant with two different
    # values stops this payload, because the time column of this API is a UTC
    # epoch: no time change can make a repeat, so a repeat is a format fault.
    repeat_context = ParseContext(
        kind="actual", collected_at=datetime(2026, 9, 17), raw_ref="x"
    )
    records = COLLECTOR.parse(
        json.dumps(
            good_payload(values=[400.0, 400.0, 410.0],
                         stamps=[FIRST_TS, FIRST_TS, FIRST_TS + 900])
        ).encode(),
        "DE",
        repeat_context,
    )
    check("guard 4: an equal repeat keeps one copy and the payload",
          [(r.ts_utc, r.value) for r in records]
          == [(FIRST_UTC, 400.0), (FIRST_UTC + timedelta(minutes=15), 410.0)],
          str([(str(r.ts_utc), r.value) for r in records]))

    body = good_payload(stamps=[FIRST_TS, FIRST_TS])
    expect_parse_error("guard 4: one timestamp with two values stops the parse", body)

    body = good_payload(values=[400.0])
    expect_parse_error("a short value list stops the parse", body)

    null_context = ParseContext(
        kind="actual", collected_at=datetime(2026, 9, 17), raw_ref="x"
    )
    records = COLLECTOR.parse(
        json.dumps(good_payload(values=[None, 410.0])).encode(), "DE", null_context
    )
    check("a null value makes no record", len(records) == 1, f"got {len(records)}")


@section
def test_forecast_parse() -> None:
    print("\n2. the forecast parse")
    run_at = datetime(2026, 9, 14, 21, 0)  # one hour before the first point
    body = {
        "unix_seconds": [FIRST_TS, FIRST_TS + 3600],  # 22:00 and 23:00 UTC
        "co2eq": [None, None],
        "co2eq_forecast": [300.0, 310.0],
        "deprecated": False,
    }
    context = ParseContext(
        kind="forecast", collected_at=run_at, raw_ref="x", run_at=run_at
    )
    records = COLLECTOR.parse(json.dumps(body).encode(), "DE", context)
    check("the forecast points parse", len(records) == 2, f"got {len(records)}")
    check("the horizon is exact", [r.horizon_min for r in records] == [60, 120],
          str([r.horizon_min for r in records]))
    check("run_at is on the record", records[0].run_at == run_at)

    # A curve that starts before the fetch holds no forecast for the past.
    later = datetime(2026, 9, 15, 0, 0)
    context = ParseContext(kind="forecast", collected_at=later, raw_ref="x", run_at=later)
    records = COLLECTOR.parse(json.dumps(body).encode(), "DE", context)
    check("a negative horizon is dropped", len(records) == 0, f"got {len(records)}")


# --- 3. The revision rule ----------------------------------------------------


def a_record(value: float, ts: datetime, collected: datetime) -> Record:
    return Record(
        country="DE", source_id="energy-charts-co2eq", metric="intensity",
        ts_utc=ts, value=value, unit="gCO2eq/kWh", granularity="native",
        kind="actual", collected_at=collected, raw_ref="test",
    )


@section
def test_revision() -> None:
    print("\n3. the revision rule")
    ts = datetime(2026, 9, 14, 10, 0)

    # `model.py` names the metrics, the kinds and the granularities. A record
    # outside that vocabulary must not reach the store, where a query that
    # filters on `kind = 'actual'` would pass over it in silence.
    try:
        Record(country="DE", source_id="energy-charts-co2eq", metric="intensity",
               ts_utc=ts, value=400.0, unit="gCO2eq/kWh", granularity="native",
               kind="past", collected_at=ts, raw_ref="test")
        check("a kind outside the vocabulary stops the record", False, "no error")
    except ParseError as error:
        check("a kind outside the vocabulary stops the record", True, str(error)[:60])

    with Store(path=TEMP / "revision.duckdb") as store:
        new, rev = store.insert_records([a_record(400.0, ts, datetime(2026, 9, 17, 8))])
        check("the first write makes a new row", (new, rev) == (1, 0), f"{new},{rev}")

        new, rev = store.insert_records([a_record(400.0, ts, datetime(2026, 9, 17, 9))])
        check("an equal value writes nothing", (new, rev) == (0, 0), f"{new},{rev}")

        new, rev = store.insert_records([a_record(401.0, ts, datetime(2026, 9, 17, 10))])
        check("a different value writes a revision", (new, rev) == (0, 1), f"{new},{rev}")

        rows = store.query("SELECT revision, value FROM record ORDER BY revision")
        check("both values stay in the store", rows == [(1, 400.0), (2, 401.0)], str(rows))

        current = store.query("SELECT revision, value FROM record_current")
        check("the view gives the newest revision", current == [(2, 401.0)], str(current))

        # ⚠ The table holds no unique key. One key two times in one batch used
        # to write two rows, and every correction after it joined against both
        # of them, so four corrections gave 30 rows and not 4.
        new, rev = store.insert_records([
            a_record(402.0, ts, datetime(2026, 9, 17, 11)),
            a_record(402.0, ts, datetime(2026, 9, 17, 11)),
        ])
        check("one key two times in one batch writes one row", (new, rev) == (0, 1),
              f"{new},{rev}")
        count = store.query("SELECT count(*) FROM record")[0][0]
        check("so the table holds one row for each revision", count == 3, str(count))
        check("and the store reports no duplicate key",
              store.duplicate_keys() == 0, str(store.duplicate_keys()))
        current = store.query("SELECT revision, value FROM record_current")
        check("the view still gives one row for the key",
              current == [(3, 402.0)], str(current))


# --- 4. The to-do list -------------------------------------------------------


@section
def test_todo() -> None:
    print("\n4. the to-do list")
    today = date(2026, 9, 17)
    with Store(path=TEMP / "todo.duckdb") as store:
        def mark(day: date, status: str) -> None:
            store.write_runs([
                RunRow(
                    source_id="s", country="DE", day=day, kind="actual", status=status,
                    started_at=datetime(2026, 9, 17), finished_at=datetime(2026, 9, 17),
                )
            ])

        mark(date(2026, 9, 10), "ok")
        mark(date(2026, 9, 11), "fail")
        mark(date(2026, 9, 12), "empty")   # young: it comes back
        mark(date(2026, 1, 5), "empty")    # old: it stays done

        days = store.days_to_collect(
            "s", "DE", "actual", date(2026, 1, 1), date(2026, 9, 13), today=today
        )
        check("an ok day does not come back", date(2026, 9, 10) not in days)
        check("a fail day comes back", date(2026, 9, 11) in days)
        check("a young empty day comes back", date(2026, 9, 12) in days)
        check("an old empty day stays done", date(2026, 1, 5) not in days)
        check("a day with no row comes back", date(2026, 9, 9) in days)

        forced = store.days_to_collect(
            "s", "DE", "actual", date(2026, 9, 1), date(2026, 9, 18),
            force_recent_days=2, today=today,
        )
        check("force_recent brings back an ok day", date(2026, 9, 16) in forced, str(forced[-4:]))

        mark(date(2026, 2, 3), "fail")  # old
        daily_days = store.days_to_collect(
            "s", "DE", "actual", date(2026, 1, 1), date(2026, 9, 13),
            retry_fail_days=30, today=today,
        )
        check("daily leaves an old fail day", date(2026, 2, 3) not in daily_days)
        check("daily takes a young fail day", date(2026, 9, 11) in daily_days)
        all_days = store.days_to_collect(
            "s", "DE", "actual", date(2026, 1, 1), date(2026, 9, 13), today=today
        )
        check("backfill takes an old fail day", date(2026, 2, 3) in all_days)


# --- 5. The window grouping --------------------------------------------------


@section
def test_windows() -> None:
    print("\n5. the window grouping")
    days = [date(2026, 9, d) for d in (1, 2, 3, 7, 8)]
    check(
        "days that follow each other make one window",
        runner.group_days(days, 400)
        == [(date(2026, 9, 1), date(2026, 9, 3)), (date(2026, 9, 7), date(2026, 9, 8))],
        str(runner.group_days(days, 400)),
    )
    long_run = [date(2026, 1, 1) + timedelta(days=n) for n in range(10)]
    check(
        "a window never holds more than max_span days",
        all((b - a).days + 1 <= 4 for a, b in runner.group_days(long_run, 4)),
    )
    check("no day makes no window", runner.group_days([], 10) == [])


@section
def test_split() -> None:
    """A server error cuts the window in two. It keeps the good years."""
    print("\n5b. the split on a server error")
    from atlas.model import FetchError

    window = (date(2016, 1, 1), date(2026, 1, 1))
    budget = [runner.SPLIT_BUDGET]
    check(
        "HTTP 500 on a long window splits it",
        runner._can_split(FetchError("x", 500), window, budget),
    )
    check(
        "HTTP 404 does not split",
        not runner._can_split(FetchError("x", 404), window, budget),
    )
    check(
        "a short window does not split",
        not runner._can_split(
            FetchError("x", 500), (date(2026, 1, 1), date(2026, 1, 4)), budget
        ),
    )
    check(
        "no budget means no split",
        not runner._can_split(FetchError("x", 500), window, [0]),
    )


# --- 6. The lock -------------------------------------------------------------


# A process id that can not be live. Windows gives out ids that divide by 4,
# and this one does not. Linux keeps `pid_max` far below it. So the stale
# branch runs with no second process, and no reused id can make the test flake.
DEAD_PID = 999999999


@section
def test_lock() -> None:
    print("\n6. the store lock")
    from atlas import lock

    path = config.LOCK_PATH
    with lock.hold("first", wait_seconds=1):
        check("the lock file is there", path.exists())
        try:
            with lock.hold("second", wait_seconds=1):
                check("a second hold in this process does not get in", False,
                      "it got the lock")
        except lock.LockBusy:
            check("a second hold in this process does not get in", True)
    check("the lock file goes away", not path.exists())

    check("a live process id reads as live", lock._process_is_alive(os.getpid()))
    check("a dead process id reads as dead", not lock._process_is_alive(DEAD_PID))
    check("a process id of 0 reads as dead", not lock._process_is_alive(0))

    # ⚠ The stale branch is the only one that removes a lock file that this
    # process did not make. Two holds in one interpreter never reach it,
    # because the id in the file is then this process, and it is always live.
    path.write_text(json.dumps({"pid": DEAD_PID, "holder": "ghost", "since": "x"}),
                    encoding="utf-8")
    with lock.hold("mine", wait_seconds=0):
        body = json.loads(path.read_text(encoding="utf-8"))
        check("a lock file of a dead process is taken", body["pid"] == os.getpid(),
              str(body))
    check("and the hold gives it back", not path.exists())

    # A holder makes the file first and writes the body after it. A waiter
    # that reads the file between the two steps must not remove it.
    path.write_text("", encoding="utf-8")
    try:
        with lock.hold("mine", wait_seconds=0):
            check("a lock file with no readable id counts as held", False,
                  "it got the lock")
    except lock.LockBusy:
        check("a lock file with no readable id counts as held", True)
    check("and that file stays", path.exists())

    older = time.time() - lock.UNREADABLE_GRACE_SECONDS - 60
    os.utime(path, (older, older))
    with lock.hold("mine", wait_seconds=0):
        body = json.loads(path.read_text(encoding="utf-8"))
        check("the same file is stale after the grace time",
              body["holder"] == "mine", str(body))

    # ⚠ Only the holder may remove the file. A waiter that removes the file of
    # the winner gives the store two writers.
    with lock.hold("mine", wait_seconds=0):
        path.write_text(
            json.dumps({"pid": os.getpid() + 1, "holder": "other", "since": "x"}),
            encoding="utf-8",
        )
    check("a lock file of another process stays after the release", path.exists())
    check("and it keeps its own body",
          json.loads(path.read_text(encoding="utf-8"))["holder"] == "other")
    path.unlink()


# --- 7. The registers --------------------------------------------------------


@section
def test_registers() -> None:
    print("\n7. the registers")
    isos = COLLECTOR.countries()
    check("the collector serves 34 countries", len(isos) == 34, f"got {len(isos)}")
    check("IE is not in the list", "IE" not in isos)
    check("DE is in the list", "DE" in isos)
    check("the API code comes from zones.json", COLLECTOR.api_code("DE") == "de")
    check("the basis comes from the register", bool(COLLECTOR.basis), COLLECTOR.basis or "")


# --- 8. The export -----------------------------------------------------------


EC = "energy-charts-co2eq"
NESO = "neso-carbon-intensity"
EDS = "energinet-eds"


def an_export_record(iso: str, ts: datetime, value: float, kind: str = "actual",
                     run_at: datetime | None = None, source_id: str = EC,
                     unit: str = "gCO2eq/kWh", granularity: str = "native") -> Record:
    return Record(
        country=iso, source_id=source_id, metric="intensity",
        ts_utc=ts, value=value, unit=unit, granularity=granularity,
        kind=kind, run_at=run_at, collected_at=datetime(2026, 3, 11, 6),
        raw_ref="test",
    )


@section
def test_export() -> None:
    """The dense files carry an index and not a key, so a value in the wrong
    cell is silent. These tests put a known value at a known time, and then
    read the cell back."""
    print("\n8. the export")
    from atlas import export

    # The test must not write over the real portal data.
    export_dir = TEMP / "portal-data"
    config.PORTAL_DATA_DIR = export_dir

    last = datetime(2026, 3, 11, 5)
    records = [
        an_export_record("DE", datetime(2026, 3, 10, 0), 100.0),
        an_export_record("DE", datetime(2026, 3, 10, 1), 200.0),
        an_export_record("DE", last, 300.0),
        an_export_record("FR", datetime(2026, 3, 10, 0), 10.0),
        # Two forecast runs of the same hour. Only the newest one is exported.
        an_export_record("DE", datetime(2026, 3, 11, 9), 55.0, "forecast",
                         datetime(2026, 3, 11, 4)),
        an_export_record("DE", datetime(2026, 3, 11, 9), 66.0, "forecast",
                         datetime(2026, 3, 11, 5)),
        # A second source for the same country and the same hours. The two
        # must never land in one cell. The values are far apart on purpose,
        # and the unit is the other one, because this publisher states
        # gCO2/kWh and energy-charts states gCO2eq/kWh.
        an_export_record("DE", datetime(2026, 3, 10, 0), 900.0, source_id=NESO,
                         unit="gCO2/kWh"),
        an_export_record("DE", last, 800.0, source_id=NESO, unit="gCO2/kWh"),
        # A roll-up of two price areas. The granularity of a record is not
        # always `native`, and the portal must read the one that it draws.
        an_export_record("DK", datetime(2026, 3, 10, 0), 120.0, source_id=EDS,
                         unit="gCO2/kWh", granularity="aggregated"),
    ]
    with Store(path=TEMP / "export.duckdb") as store:
        store.insert_records(records)
        export.run(store)

    def body(name: str) -> dict:
        return json.loads((export_dir / name).read_text(encoding="utf-8"))

    for name in ("meta.json", "monthly.json", "latest.json", "health.json",
                 "register.json", "daily_all.json", "hours.json",
                 "profile.json", "forecast.json", "pairs.json"):
        check(f"{name} is written", (export_dir / name).exists())
    check("a file for each country", (export_dir / "daily" / "DE.json").exists()
          and (export_dir / "recent" / "FR.json").exists())

    daily = body("daily_all.json")
    ec_day = daily["sources"][EC]
    check("daily_all ends on the newest day", daily["end_day"] == "2026-03-11", daily["end_day"])
    check("daily_all holds one array of the stated length",
          len(ec_day["DE"]["mean_unweighted"]) == daily["days"] == export.DAILY_ALL_DAYS)
    check("the newest day is the last cell",
          ec_day["DE"]["mean_unweighted"][-1] == 300.0,
          str(ec_day["DE"]["mean_unweighted"][-1]))
    check("the day before holds the mean of its two records",
          ec_day["DE"]["mean_unweighted"][-2] == 150.0,
          str(ec_day["DE"]["mean_unweighted"][-2]))
    check("the low and the high of that day are kept",
          (ec_day["DE"]["lo"][-2], ec_day["DE"]["hi"][-2]) == (100.0, 200.0))
    check("a day with no record is null",
          ec_day["FR"]["mean_unweighted"][-1] is None)

    # ⚠ The reason the file is keyed by source. A query that groups by country
    # alone would give (300 + 800) / 2 here, and the difference between the two
    # publishers would disappear without a trace.
    neso_day = daily["sources"][NESO]
    check("the second source keeps its own daily array",
          neso_day["DE"]["mean_unweighted"][-1] == 800.0,
          str(neso_day["DE"]["mean_unweighted"][-1]))
    check("the first source is not moved by the second",
          ec_day["DE"]["mean_unweighted"][-1] == 300.0)
    check("the second source holds only its own countries", list(neso_day) == ["DE"],
          str(list(neso_day)))

    hours = body("hours.json")
    ec_hour = hours["sources"][EC]
    offset = int((last - datetime(2026, 3, 10, 0)).total_seconds() // 3600)
    check("hours holds 30 days of cells", hours["hours"] == export.HOURS_ALL_DAYS * 24)
    check("the newest hour is the last cell", ec_hour["DE"][-1] == 300.0)
    check("an older hour lands on its own index",
          ec_hour["DE"][-1 - offset] == 100.0,
          str(ec_hour["DE"][-1 - offset]))
    check("the hour after it lands one cell later",
          ec_hour["DE"][-offset] == 200.0)
    check("a country with no record at that hour is null",
          ec_hour["FR"][-1] is None)
    check("the same hour of the second source is a separate cell",
          hours["sources"][NESO]["DE"][-1] == 800.0,
          str(hours["sources"][NESO]["DE"][-1]))

    profile = body("profile.json")
    grid = profile["sources"][EC]["DE"]["grid"]
    check("the profile grid is 12 months by 24 hours",
          len(grid) == 12 and all(len(row) == 24 for row in grid))
    check("March hour 00 holds the mean of that hour", grid[2][0] == 100.0, str(grid[2][0]))
    check("March hour 05 holds the newest value", grid[2][5] == 300.0, str(grid[2][5]))
    check("a month with no record is null", grid[0][0] is None)
    check("the record count of the month is kept",
          profile["sources"][EC]["DE"]["records"][2] == 3,
          str(profile["sources"][EC]["DE"]["records"][2]))
    check("the profile of the second source is its own grid",
          profile["sources"][NESO]["DE"]["grid"][2][0] == 900.0,
          str(profile["sources"][NESO]["DE"]["grid"][2][0]))

    monthly = body("monthly.json")
    march = {row[1]: row for row in monthly["rows"]
             if row[0] == "DE" and row[2] == "2026-03"}
    check("monthly holds the count, the mean, the band and the median",
          march.get(EC, [])[3:] == [3, 200.0, 100.0, 300.0, 200.0], str(march.get(EC)))
    check("the second source keeps its own month row",
          march.get(NESO, [])[3:] == [2, 850.0, 800.0, 900.0, 850.0],
          str(march.get(NESO)))

    latest = body("latest.json")
    check("latest names its six fields",
          latest["fields"] == ["country", "source_id", "ts_utc", "value",
                               "age_hours", "stale"], str(latest["fields"]))
    newest = {(row[0], row[1]): row for row in latest["rows"]}
    check("latest keeps one row for each source of a country",
          (newest[("DE", EC)][3], newest[("DE", NESO)][3]) == (300.0, 800.0),
          str([newest.get(("DE", EC)), newest.get(("DE", NESO))]))
    check("the newest row of a source is not stale",
          (newest[("DE", EC)][4], newest[("DE", EC)][5]) == (0.0, False),
          str(newest.get(("DE", EC))))
    # ⚠ A row is the newest record of that country, and not a record of now.
    # France stopped 29 hours behind the newest record of the same source, so
    # the row stays and it carries the age that says so.
    check("a country that stopped keeps its row, with its age",
          (newest[("FR", EC)][4], newest[("FR", EC)][5]) == (29.0, True),
          str(newest.get(("FR", EC))))
    check("the file names the newest record of each source",
          latest["source_last_ts_utc"][EC] == str(last),
          str(latest["source_last_ts_utc"]))

    meta = body("meta.json")
    de = [c for c in meta["countries"] if c["iso"] == "DE"][0]
    check("the country meta counts each source on its own",
          de["sources"][EC]["rows"] == 3 and de["sources"][NESO]["rows"] == 2,
          str(de["sources"]))

    # ⚠ Two publishers of one country give two units. A panel must take the
    # unit of the value that it draws, so the unit travels with the source.
    check("the country meta gives each source its own unit",
          (de["sources"][EC]["unit"], de["sources"][NESO]["unit"])
          == ("gCO2eq/kWh", "gCO2/kWh"), str(de["sources"]))
    by_source = {entry["source_id"]: entry for entry in meta["sources"]}
    check("the source meta takes the unit from the stored rows",
          by_source[NESO]["unit"] == "gCO2/kWh", str(by_source[NESO]["unit"]))
    danish = [c for c in meta["countries"] if c["iso"] == "DK"][0]
    check("a roll-up of two zones carries the granularity `aggregated`",
          danish["sources"][EDS]["granularity"] == "aggregated",
          str(danish["sources"][EDS]))
    check("a source that gives the country itself carries `native`",
          de["sources"][EC]["granularity"] == "native",
          str(de["sources"][EC]["granularity"]))

    # ⚠ meta.json is the only file that states a unit. A scalar `unit` on a
    # file that holds many sources says one unit for all of them, and two
    # publishers of this fixture give gCO2/kWh and not gCO2eq/kWh.
    many_sources = ("monthly.json", "latest.json", "daily_all.json", "hours.json",
                    "profile.json", "forecast.json", "daily/DE.json", "recent/DE.json")
    with_a_unit = [name for name in many_sources if "unit" in body(name)]
    check("no file of many sources states one unit for all of them",
          not with_a_unit, ", ".join(with_a_unit))

    forecast = body("forecast.json")
    values = [row[4] for row in forecast["rows"]]
    check("only the newest forecast run is exported", values == [66.0], str(values))
    check("the run count of the store is reported",
          forecast["runs_in_store"]["rows"][0][1] == 2,
          str(forecast["runs_in_store"]["rows"]))

    register = body("register.json")
    sources_on_disk = json.loads(config.SOURCES_JSON.read_text(encoding="utf-8"))
    zones_on_disk = json.loads(config.ZONES_JSON.read_text(encoding="utf-8"))
    check("the register carries both files whole",
          len(register["sources"]["sources"]) == len(sources_on_disk["sources"])
          and len(register["zones"]["countries"]) == len(zones_on_disk["countries"]),
          f'{len(register["sources"]["sources"])}, {len(register["zones"]["countries"])}')

    # A country points at a national source. If that source leaves the
    # register, the pointer must leave with it, or the portal shows an id
    # that no entry explains.
    known = {s["id"] for s in sources_on_disk["sources"]}
    dangling = [
        c["iso"] for c in zones_on_disk["countries"]
        if c.get("national") and c["national"]["source_id"] not in known
    ]
    check("every national source of the zone model is in the register",
          not dangling, ", ".join(dangling))


# --- 8b. The window of the recent file ---------------------------------------


@section
def test_recent_window() -> None:
    """⚠ `recent/<ISO>.json` declares a window of `RECENT_DAYS_IN_EXPORT`
    days. A stored forward curve reaches days into the future. A window that
    ends at the newest record of any kind therefore starts in the future too,
    and the file holds fewer days than the `days` key declares."""
    print("\n8b. the recent file")
    from atlas import export

    newest_actual = datetime(2026, 3, 11, 5)
    oldest = datetime(2026, 2, 26, 0)  # 13.2 days behind the newest actual
    forecast_ts = datetime(2026, 3, 14, 0)  # 3 days after it
    with Store(path=TEMP / "recent.duckdb") as store:
        store.insert_records([
            an_export_record("DE", oldest, 100.0),
            an_export_record("DE", newest_actual, 300.0),
            an_export_record("DE", forecast_ts, 55.0, "forecast",
                             datetime(2026, 3, 11, 5)),
        ])
        recent = export._recent(store, "DE")

    stamps = [str(row[1]) for row in recent["rows"]]
    check("the window ends at the newest actual",
          bool(stamps) and stamps[-1] == str(newest_actual), str(stamps))
    check("a forecast is not in the file", str(forecast_ts) not in stamps, str(stamps))
    # A window that ended at the forecast would start on 2026-02-28, and it
    # would lose this record and 3 of the 14 days that the file declares.
    check("the window holds the days that the file declares",
          str(oldest) in stamps, f'{recent["days"]} days, {stamps}')
    check("the values are the actual values",
          [row[2] for row in recent["rows"]] == [100.0, 300.0],
          str([row[2] for row in recent["rows"]]))


# --- 8c. The pair measurement ------------------------------------------------


ELIA_P = "elia-co2-production"
ELIA_C = "elia-co2-consumption"

# The fixture starts here, and every day of it is a full UTC day.
FIRST_DAY = datetime(2026, 3, 1)

# `analyse.MIN_HOURS` is 168, which is 7 days. The fixture gives 8 full days,
# so a pair clears the threshold and a one-day pair does not.
FIXTURE_DAYS = 8


def a_pair_record(iso: str, ts: datetime, value: float | None, source_id: str,
                  unit: str = "gCO2eq/kWh", basis: str | None = None,
                  scope: str | None = None) -> Record:
    return Record(
        country=iso, source_id=source_id, metric="intensity",
        ts_utc=ts, value=value, unit=unit, granularity="native",
        kind="actual", basis=basis, scope=scope,
        collected_at=datetime(2026, 3, 20, 6), raw_ref="test",
    )


def a_series(iso: str, source_id: str, value_of, days: int = FIXTURE_DAYS,
             hours_of=None, **fields) -> list[Record]:
    """One source of one country. `value_of(day, hour)` gives the value.

    `hours_of(day)` gives the hours of that day. The default is a full day.
    A value of `None` makes a record that the pair query must not count.
    """
    out = []
    for day in range(days):
        for hour in (hours_of(day) if hours_of else range(24)):
            out.append(a_pair_record(
                iso, FIRST_DAY + timedelta(days=day, hours=hour),
                value_of(day, hour), source_id, **fields,
            ))
    return out


@section
def test_pairs() -> None:
    """The pair table. Every number here is checkable by hand.

    ⚠ The headline of the project is a share, and a share needs a stated
    denominator. `gap_share_pct` divides by the larger of the two means, and
    not by `mean_a`, which is the mean of the alphabetically first source. XA
    holds the larger mean on side A and XE holds it on side B, so the two
    fixtures fix the denominator from both sides. A test that used only a pair
    with the larger source first would pass under either rule.
    """
    print("\n8c. the pair measurement")
    from atlas import analyse

    records: list[Record] = []

    # XA. The arithmetic, and the decision test.
    # energy-charts holds 200 g, and it dips to 100 g at hour 3 of every day.
    # NESO holds 100 g, and it dips to 50 g at an hour that moves.
    #   mean a = (23 x 200 + 100) / 24 = 195.8333
    #   mean b = (23 x 100 +  50) / 24 =  97.9166
    # The two sources name the same cleanest hour on 4 days of 8, and they
    # come within one hour on 6 of 8, because hour 4 is next to hour 3.
    neso_dip = {0: 3, 1: 3, 2: 3, 3: 3, 4: 4, 5: 4, 6: 10, 7: 10}
    # ⚠ NESO goes in the store first. `a` must still be energy-charts, because
    # the order is alphabetical and not the order of arrival.
    records += a_series(
        "XA", NESO, lambda day, hour: 50.0 if hour == neso_dip[day] else 100.0,
        unit="gCO2/kWh",
    )
    records += a_series(
        "XA", EC, lambda _day, hour: 100.0 if hour == 3 else 200.0,
    )

    # XB. The two Elia series: one publisher, one unit, one scope, two bases.
    # This is the only pair of kind `basis`. Its share is 9.0 %, which is
    # below every method pair, so a leak into `range` is visible.
    records += a_series(
        "XB", ELIA_C, lambda _day, hour: 100.0 + hour,
        basis="consumption-based", scope="not stated (CO2 equivalents)",
    )
    records += a_series(
        "XB", ELIA_P, lambda _day, hour: 90.0 + hour,
        basis="production-based", scope="not stated (CO2 equivalents)",
    )

    # XC. One day only. 24 shared hours is below `MIN_HOURS`, so the pair is
    # skipped, and the file names it.
    records += a_series("XC", EC, lambda _day, hour: 100.0 + hour, days=1)
    records += a_series("XC", NESO, lambda _day, hour: 200.0 + hour, days=1,
                        unit="gCO2/kWh")

    # XD. A null on one side. NESO reports no value at hour 5 of any day.
    # Those 8 hours must leave the join. A null counted as zero would put
    # mean b at (184 x 200) / 192 = 191.7 instead of 200.0.
    records += a_series("XD", EC, lambda _day, _hour: 100.0)
    records += a_series(
        "XD", NESO, lambda _day, hour: None if hour == 5 else 200.0,
        unit="gCO2/kWh",
    )

    # XE. The shape of the real Danish pair. `energinet-eds` sorts before
    # `energy-charts-co2eq`, and it holds the smaller mean.
    #   mean a = 100 + 11.5 = 111.5, mean b = 300 + 3 x 11.5 = 334.5
    #   share  = -223.0 / 334.5 x 100 = -66.7 over the larger mean
    #   the same gap over mean a gives -200.0, and that is the rule this
    #   fixture must rule out
    records += a_series("XE", EC, lambda _day, hour: 300.0 + 3 * hour)
    records += a_series("XE", EDS, lambda _day, hour: 100.0 + hour,
                        unit="gCO2/kWh")

    # XF. The day filter reads both sides. The ninth day holds 20 hours of
    # NESO and 24 of energy-charts, so it is not a day for the decision test,
    # and its 20 shared hours still count in the mean.
    records += a_series("XF", EC, lambda _day, hour: 100.0 + hour, days=9)
    records += a_series(
        "XF", NESO, lambda _day, hour: 200.0 + hour, days=9,
        hours_of=lambda day: range(20) if day == 8 else range(24),
        unit="gCO2/kWh",
    )

    # XG. Two hours of one day hold the same lowest value. energy-charts sits
    # at 100 g at hour 2 AND at hour 5, and NESO has one lowest hour, hour 2.
    # The earliest of the tied hours must win, so the two agree on every day.
    # A tie-break that took hour 5 would put the agreement at 0 %.
    records += a_series(
        "XG", EC, lambda _day, hour: 100.0 if hour in (2, 5) else 300.0,
    )
    records += a_series(
        "XG", NESO, lambda _day, hour: 50.0 if hour == 2 else 100.0,
        unit="gCO2/kWh",
    )

    with Store(path=TEMP / "pairs.duckdb") as store:
        batch: dict[tuple[str, str], list[Record]] = {}
        for item in records:
            batch.setdefault((item.country, item.source_id), []).append(item)
        for one in batch.values():
            store.insert_records(one)
        table = analyse.pairs(store)

    found = {row["country"]: row for row in table["pairs"]}
    skipped = {row["country"]: row for row in table["skipped"]}

    # --- the arithmetic ---
    xa = found.get("XA", {})
    check("XA holds every hour of the 8 days", xa.get("hours") == 192, str(xa.get("hours")))
    check("the mean of each side is the mean of the shared hours",
          (xa.get("mean_a"), xa.get("mean_b")) == (195.8, 97.9),
          f'{xa.get("mean_a")} / {xa.get("mean_b")}')
    check("mean_gap is mean_a minus mean_b", xa.get("mean_gap") == 97.9,
          str(xa.get("mean_gap")))
    check("ratio is mean_a over mean_b", xa.get("ratio") == 2.0, str(xa.get("ratio")))
    check("mean_abs_gap is the mean of the absolute gap",
          xa.get("mean_abs_gap") == 97.9, str(xa.get("mean_abs_gap")))
    # XA holds the larger mean on side A, so 97.9166 / 195.8333 is 50.0 under
    # either denominator. XE below is the fixture that separates the two.
    check("gap_share_pct is mean_gap over the larger mean",
          xa.get("gap_share_pct") == 50.0, str(xa.get("gap_share_pct")))
    check("abs_gap_share_pct is mean_abs_gap over the larger mean",
          xa.get("abs_gap_share_pct") == 50.0, str(xa.get("abs_gap_share_pct")))
    check("the first and the last shared hour are in the row",
          (xa.get("first_ts_utc"), xa.get("last_ts_utc"))
          == ("2026-03-01 00:00:00", "2026-03-08 23:00:00"),
          f'{xa.get("first_ts_utc")} .. {xa.get("last_ts_utc")}')

    # --- a and b are alphabetical, whatever the order of arrival ---
    check("a is the alphabetically first source, and not the first stored",
          (xa.get("a"), xa.get("b")) == (EC, NESO), f'{xa.get("a")} / {xa.get("b")}')
    xe = found.get("XE", {})
    check("a stays alphabetical when it holds the smaller mean",
          (xe.get("a"), xe.get("b")) == (EDS, EC), f'{xe.get("a")} / {xe.get("b")}')
    check("the sign of the gap follows a minus b",
          (xe.get("mean_a"), xe.get("mean_b"), xe.get("mean_gap"))
          == (111.5, 334.5, -223.0),
          f'{xe.get("mean_a")} / {xe.get("mean_b")} / {xe.get("mean_gap")}')
    # ⚠ The denominator, on the fixture whose two means differ most. One gap
    # of -223.0 g gives -66.7 % over the larger mean and -200.0 % over mean_a.
    # The real Danish pair has this shape, and it gives -52.7 % and -111.3 %.
    # The documents and `portal/data/pairs.json` must state one of the two.
    # This check holds the file to the larger mean, and it names the other one.
    over_larger = round(
        xe.get("mean_gap") / max(xe.get("mean_a"), xe.get("mean_b")) * 100, 1)
    over_mean_a = round(xe.get("mean_gap") / xe.get("mean_a") * 100, 1)
    check("the share divides by the larger mean, and not by mean_a",
          xe.get("gap_share_pct") == over_larger == -66.7 and over_mean_a == -200.0,
          f'{xe.get("gap_share_pct")}, larger {over_larger}, mean_a {over_mean_a}')
    check("the absolute share divides by the larger mean too",
          xe.get("abs_gap_share_pct") == 66.7, str(xe.get("abs_gap_share_pct")))
    check("no share of the table passes 100 %",
          all(abs(row["gap_share_pct"]) <= 100.0 for row in table["pairs"]
              if row["gap_share_pct"] is not None),
          str([row["gap_share_pct"] for row in table["pairs"]]))
    check("the file states the denominator of every share",
          table["denominator"] == analyse.DENOMINATOR == "larger mean of the pair",
          str(table.get("denominator")))
    # The other side of the same rule. XD holds mean_a 100.0 and mean_b 200.0,
    # so the larger mean halves both shares of that row.
    xd_share = found.get("XD", {})
    check("a gap over the larger mean is halved when b holds twice a",
          (xd_share.get("gap_share_pct"), xd_share.get("abs_gap_share_pct"))
          == (-50.0, 50.0),
          f'{xd_share.get("gap_share_pct")} / {xd_share.get("abs_gap_share_pct")}')
    check("correlation reads the shared hours", xe.get("correlation") == 1.0,
          str(xe.get("correlation")))

    # --- the day filter ---
    check("a day counts when both sources cover 24 hours",
          xa.get("days") == 8, str(xa.get("days")))
    check("same_hour_pct counts the days of one cleanest hour",
          xa.get("same_hour_pct") == 50.0, str(xa.get("same_hour_pct")))
    check("within_one_hour_pct takes the same-hour days in too",
          xa.get("within_one_hour_pct") == 75.0, str(xa.get("within_one_hour_pct")))
    xf = found.get("XF", {})
    check("a short day of either source is not a day",
          xf.get("days") == 8, str(xf.get("days")))
    check("the hours of that short day still count in the mean",
          xf.get("hours") == 212, str(xf.get("hours")))
    # ⚠ The tie-break is a part of the answer. `arg_min` picks a tied hour by
    # thread order, and it gave the Belgian method pair 68.53 %, then 68.36 %,
    # then 67.83 % on three runs over one store. The earliest hour wins now,
    # so two runs give one number.
    xg = found.get("XG", {})
    check("the earliest of two hours that tie at the lowest value wins",
          (xg.get("same_hour_pct"), xg.get("within_one_hour_pct")) == (100.0, 100.0),
          f'{xg.get("same_hour_pct")} / {xg.get("within_one_hour_pct")}')

    # --- the null, and the skip ---
    xd = found.get("XD", {})
    check("an hour with a null on one side leaves the join",
          xd.get("hours") == 184, str(xd.get("hours")))
    check("a null is not counted as a zero",
          (xd.get("mean_a"), xd.get("mean_b")) == (100.0, 200.0),
          f'{xd.get("mean_a")} / {xd.get("mean_b")}')
    check("a source of 23 hours a day gives no complete day",
          xd.get("days") == 0, str(xd.get("days")))
    check("an agreement rate with no day is null",
          xd.get("same_hour_pct") is None, str(xd.get("same_hour_pct")))
    # ⚠ DuckDB `corr` gives NaN here, and not NULL. `json.dumps` writes NaN as
    # a bare word that no strict JSON reader takes, so one flat series would
    # break the whole portal file and not one cell of it.
    check("a flat series gives no correlation",
          xd.get("correlation") is None, str(xd.get("correlation")))
    check("the table holds nothing that JSON cannot carry",
          "NaN" not in json.dumps(table) and "Infinity" not in json.dumps(table))
    check("a pair under MIN_HOURS is not measured", "XC" not in found)
    check("a skipped pair is named in the file, with its hours",
          skipped.get("XC", {}).get("hours") == 24, str(skipped.get("XC")))
    check("the file states the threshold", table["min_hours"] == analyse.MIN_HOURS)

    # --- the unit and the basis, read from the rows ---
    check("the unit of each side comes from the stored rows",
          (xa.get("unit_a"), xa.get("unit_b")) == ("gCO2eq/kWh", "gCO2/kWh"),
          f'{xa.get("unit_a")} / {xa.get("unit_b")}')
    # ⚠ The portal must be able to say that this pair compares two different
    # quantities. A pair that lost the unit would read as one measurement.
    check("same_unit is false when the two quantities differ",
          xa.get("same_unit") is False, str(xa.get("same_unit")))
    xb = found.get("XB", {})
    check("the basis of each side comes from the stored rows",
          (xb.get("basis_a"), xb.get("basis_b"))
          == ("consumption-based", "production-based"),
          f'{xb.get("basis_a")} / {xb.get("basis_b")}')
    check("same_basis is false and same_unit is true for the Elia pair",
          (xb.get("same_basis"), xb.get("same_unit")) == (False, True),
          f'{xb.get("same_basis")} / {xb.get("same_unit")}')

    # --- kind, and the range that it decides ---
    check("one publisher, one unit, one scope and two bases is a basis pair",
          xb.get("kind") == "basis", str(xb.get("kind")))
    check("every other pair is a method pair",
          {row["country"]: row["kind"] for row in table["pairs"] if row["country"] != "XB"}
          == {"XA": "method", "XD": "method", "XE": "method", "XF": "method",
              "XG": "method"},
          str({row["country"]: row["kind"] for row in table["pairs"]}))
    # The absolute method shares are 50.0 (XA), 50.0 (XD), 66.7 (XE), 47.3
    # (XF) and 65.4 (XG), all over the larger mean of each pair. The basis
    # pair is at 9.0, so it would take the low end if it leaked in.
    check("range covers the method pairs only",
          (table["range"]["lo_pct"], table["range"]["hi_pct"]) == (47.3, 66.7),
          str(table["range"]))
    check("range says what it is over", table["range"]["over"] == "method-pairs")
    check("the chance baseline is in the file",
          table["chance"] == {"same_hour_pct": 4.17, "within_one_hour_pct": 12.5},
          str(table["chance"]))
    check("the method names the query", "record_current" in table["method"]
          and "alphabetically first" in table["method"])
    # The ninth day of XF. energy-charts covers it to hour 23, and NESO stops
    # at hour 19, so the newest hour of the store is the energy-charts one.
    check("the file carries the newest hour of the store",
          table["store_last_ts_utc"] == "2026-03-09 23:00:00",
          str(table["store_last_ts_utc"]))

    # The terminal table must survive a null cell. XD holds two of them.
    printed = analyse.lines(table)
    check("the printed table holds one line for each pair",
          sum(1 for line in printed if line.startswith("X")) == 7,
          str([line[:4] for line in printed if line.startswith("X")]))
    # ⚠ A Windows console runs cp1252, and one character outside it stops the
    # command in the middle of the table.
    check("every printed line goes through a cp1252 console",
          all(line.encode("cp1252", errors="strict") for line in printed if line))


# --- 8d. The coverage model of health.json -----------------------------------


# The coverage fixture starts here. Every day of it is a full UTC day, so a
# reader counts the periods of each series by hand.
COVER_DAY = datetime(2026, 3, 1)

# One line of a run row that did not fail. `a_note` carries it, and that is how
# a dropped point reaches the file that reports health.
A_DROPPED_POINT = (
    "actual is 0.0 at 2026-03-01T18:00:00. This publisher writes 0.0 for a "
    "period that it did not compute."
)


def a_cover_series(iso: str, source_id: str, stamps: list[datetime]) -> list[Record]:
    """One actual series. The value is the same everywhere, because the
    coverage model counts records and reads no value."""
    return [an_export_record(iso, ts, 100.0, source_id=source_id) for ts in stamps]


def a_run_day(source_id: str, iso: str, day: int, kind: str = "actual",
              note: str | None = None, minute: int = 0) -> RunRow:
    """One `ok` day of the run table.

    `_health` reports a series only when the run table holds a row for it, so
    every series of the fixture needs its days here. `minute` moves
    `finished_at`, because the file keeps the newest row of each day.
    """
    moment = COVER_DAY + timedelta(days=day, minutes=minute)
    return RunRow(
        source_id=source_id, country=iso, day=(COVER_DAY + timedelta(days=day)).date(),
        kind=kind, status="ok", rows=1, error=note,
        started_at=COVER_DAY, finished_at=moment,
    )


@section
def test_coverage() -> None:
    """The expected count of `health.json`, and the widest hole as a date range.

    ⚠ The expected count must follow the step that the data shows, day by day.
    The register holds one step for one country, and 14 series changed their
    step inside their span. On 2026-09-23 the fixed-step model reported
    35.35 % absence across the store, and this model reported 3.23 %. A change
    that goes back to the register step puts a wrong headline in front of a
    reader. No number in the file says that it happened.
    """
    print("\n8d. the coverage model")
    from atlas import export

    # DE: two days at 60 minutes, and then two days at 30 minutes. The step
    # changes inside the span, and the series holds every period of both parts.
    de = [COVER_DAY + timedelta(hours=h) for h in range(48)]
    de += [COVER_DAY + timedelta(days=2, minutes=30 * k) for k in range(96)]
    # GB: one full day at 60 minutes, then no record for 3 days, then a part
    # day that starts at 12:00.
    gb = [COVER_DAY + timedelta(hours=h) for h in range(24)]
    gb += [COVER_DAY + timedelta(days=4, hours=h) for h in range(12, 24)]
    # DK: one full day at 60 minutes, with no hole in it.
    dk = [COVER_DAY + timedelta(hours=h) for h in range(24)]
    # FR: a full day, a part day of 12 hours, and a full day.
    fr = [COVER_DAY + timedelta(hours=h) for h in range(24)]
    fr += [COVER_DAY + timedelta(days=1, hours=h) for h in range(12)]
    fr += [COVER_DAY + timedelta(days=2, hours=h) for h in range(24)]

    records = (a_cover_series("DE", EC, de) + a_cover_series("GB", NESO, gb)
               + a_cover_series("DK", EDS, dk) + a_cover_series("FR", EC, fr))
    # A forecast of one of the series. The model must pass over it.
    records.append(an_export_record("DE", COVER_DAY + timedelta(days=4), 55.0,
                                    "forecast", COVER_DAY + timedelta(days=3, hours=23)))

    runs = [a_run_day(EC, "DE", day) for day in range(4)]
    runs += [a_run_day(NESO, "GB", day) for day in range(5)]
    runs += [a_run_day(EDS, "DK", 0)]
    runs += [a_run_day(EC, "FR", day) for day in range(3)]
    runs += [a_run_day(EC, "DE", 3, "forecast")]
    # The same GB day, one minute later, with a dropped point on it.
    runs += [a_run_day(NESO, "GB", 0, note=A_DROPPED_POINT, minute=1)]

    with Store(path=TEMP / "coverage.duckdb") as store:
        store.insert_records(records)
        store.write_runs(runs)
        health = export._health(store)

    fields = health["fields"]
    rows = {(row[0], row[1], row[2]): dict(zip(fields, row)) for row in health["rows"]}
    check("every row is as long as the field list",
          all(len(row) == len(fields) for row in health["rows"]),
          str([len(row) for row in health["rows"]]))
    model_fields = ("a_note", "records", "expected", "absent", "step_minutes",
                    "hole_from", "hole_to", "hole_hours")
    check("the file names the 8 fields of the coverage model",
          [name for name in model_fields if name not in fields] == [],
          str(fields))

    # --- the step that the data shows, and not the step of the register ---
    de_row = rows[(EC, "DE", "actual")]
    check("the series holds every record of both steps",
          de_row["records"] == 144, str(de_row["records"]))
    check("the expected count follows the step change inside the span",
          de_row["expected"] == 144, str(de_row["expected"]))
    check("so a series that changed its step reports no absence",
          de_row["absent"] == 0, str(de_row["absent"]))
    check("the step of the series is the step that most records ran at",
          de_row["step_minutes"] == 30, str(de_row["step_minutes"]))

    # ⚠ One step for the whole span gives a wrong headline. The span of this
    # fixture is 5,730 minutes. One fixed step of 30 minutes expects 192
    # periods and reports 48 absent. That is 25.0 % of a series that holds
    # every period its publisher ran.
    span = int((de[-1] - de[0]).total_seconds() // 60)
    fixed = span // 30 + 1
    check("a fixed step of the same span expects 192 periods and not 144",
          (span, fixed, fixed - de_row["records"]) == (5730, 192, 48),
          f"{span} {fixed}")
    check("and the model of the file reports none of that absence",
          de_row["expected"] != fixed and de_row["absent"] == 0,
          f'{de_row["expected"]} {de_row["absent"]}')

    # --- the widest hole, as a date range ---
    gb_row = rows[(NESO, "GB", "actual")]
    check("the widest hole is a date range and not a count",
          (gb_row["hole_from"], gb_row["hole_to"])
          == (datetime(2026, 3, 1, 23), datetime(2026, 3, 5, 12)),
          f'{gb_row["hole_from"]} to {gb_row["hole_to"]}')
    check("the range and the length of the hole agree",
          gb_row["hole_from"] is not None and gb_row["hole_to"] is not None
          and gb_row["hole_to"] - gb_row["hole_from"] == timedelta(hours=85)
          == timedelta(hours=gb_row["hole_hours"]),
          str(gb_row["hole_hours"]))
    check("the periods of the hole are counted as absent",
          (gb_row["records"], gb_row["expected"], gb_row["absent"]) == (36, 120, 84),
          f'{gb_row["records"]} {gb_row["expected"]} {gb_row["absent"]}')
    # ⚠ A dropped point sits on a run row with the status `ok`, so it never
    # reaches `an_error`. `a_note` is the only column that shows it.
    check("a dropped point is visible, and its day stays ok",
          (gb_row["days_ok"], gb_row["days_fail"], gb_row["an_error"],
           gb_row["a_note"]) == (5, 0, None, A_DROPPED_POINT),
          f'{gb_row["days_ok"]} {gb_row["a_note"]}')

    # --- a series with no hole ---
    dk_row = rows[(EDS, "DK", "actual")]
    check("a series with no hole reports its own step as the widest interval",
          (dk_row["hole_from"], dk_row["hole_to"])
          == (datetime(2026, 3, 1, 0), datetime(2026, 3, 1, 1))
          and dk_row["hole_hours"] == 1.0 and dk_row["step_minutes"] == 60,
          f'{dk_row["hole_from"]} to {dk_row["hole_to"]}, {dk_row["hole_hours"]}')
    check("and it holds every period between its first record and its last",
          (dk_row["records"], dk_row["expected"], dk_row["absent"]) == (24, 24, 0),
          f'{dk_row["records"]} {dk_row["expected"]} {dk_row["absent"]}')

    # --- a part day ---
    # ⚠ A row of days counts request-days, and it states no shortfall. Every
    # day of FR answered `ok`, and the middle day holds 12 of its 24 hours.
    fr_row = rows[(EC, "FR", "actual")]
    check("every day of the part-day series answered ok",
          (fr_row["days_ok"], fr_row["days_empty"], fr_row["days_fail"]) == (3, 0, 0),
          f'{fr_row["days_ok"]} {fr_row["days_empty"]} {fr_row["days_fail"]}')
    check("a day with some records and not a full day reads as an absence",
          (fr_row["records"], fr_row["expected"], fr_row["absent"]) == (60, 72, 12),
          f'{fr_row["records"]} {fr_row["expected"]} {fr_row["absent"]}')
    check("and the part day makes the widest hole of that series",
          (fr_row["hole_from"], fr_row["hole_to"], fr_row["hole_hours"])
          == (datetime(2026, 3, 2, 11), datetime(2026, 3, 3), 13.0),
          f'{fr_row["hole_from"]} to {fr_row["hole_to"]}')

    # --- a forecast series holds no model ---
    # A forecast holds many runs of one timestamp, so a step and an expected
    # count mean nothing there.
    forecast_row = rows[(EC, "DE", "forecast")]
    check("a forecast row carries its count and no coverage model",
          (forecast_row["records"], forecast_row["expected"],
           forecast_row["absent"], forecast_row["step_minutes"]) == (1, None, None, None),
          str([forecast_row[name] for name in model_fields[1:]]))
    check("and the forecast does not move the actual series of that country",
          de_row["records"] == 144, str(de_row["records"]))


# --- 9. The other collectors -------------------------------------------------


def a_context(kind: str = "actual") -> ParseContext:
    return ParseContext(kind=kind, collected_at=datetime(2026, 9, 18, 12), raw_ref="test")


@section
def test_neso() -> None:
    """NESO gives two defects that a strict guard would turn into a lost month.
    Both were measured on 2026-09-18."""
    print("\n9. the NESO collector")
    from atlas.collectors.neso_carbon_intensity import COLLECTOR as NESO_C

    def period(stamp, **intensity):
        return {"from": stamp, "to": stamp, "intensity": intensity}

    payload = json.dumps({"data": [
        period("2026-09-10T00:00Z", forecast=160, actual=150, index="moderate"),
        # ⚠ 17 of 1,441 periods of July 2025 carry no `forecast` key at all.
        period("2026-09-10T00:30Z", actual=140, index="moderate"),
        # ⚠ one half hour, two different values. Neither is stored.
        period("2026-09-10T01:00Z", forecast=200, actual=303, index="high"),
        period("2026-09-10T01:00Z", forecast=200, actual=295, index="high"),
        # an equal copy of one half hour. One record is stored.
        period("2026-09-10T01:30Z", forecast=100, actual=90, index="low"),
        period("2026-09-10T01:30Z", forecast=100, actual=90, index="low"),
        # `actual` is null until the publisher fills it in.
        period("2026-09-10T02:00Z", forecast=120, actual=None, index="low"),
    ]}).encode()

    context = a_context()
    records = NESO_C.parse(payload, "GB", context)
    stamps = [r.ts_utc.isoformat() for r in records]
    check("a period with no forecast key still gives the actual",
          "2026-09-10T00:30:00" in stamps, str(stamps))
    check("a timestamp with two different values is not stored",
          "2026-09-10T01:00:00" not in stamps, str(stamps))
    check("the drop is written down", any("303" in line for line in context.dropped),
          str(context.dropped))
    check("an equal copy gives one record", stamps.count("2026-09-10T01:30:00") == 1,
          str(stamps))
    check("a null actual is not a zero", "2026-09-10T02:00:00" not in stamps, str(stamps))
    check("the rest of the payload is kept", len(records) == 3, str(len(records)))
    check("the unit is the one the publisher states",
          records[0].unit == "gCO2/kWh", records[0].unit)

    # ⚠ A null beside a value at one timestamp. Guard 4 sorts the values of a
    # timestamp to write the reason down, and a null in that set stopped the
    # whole run with a TypeError. A null is an absence, so it makes no
    # conflict, and the value that the publisher gives stays.
    null_context = a_context()
    pair = json.dumps({"data": [
        period("2026-09-11T00:00Z", forecast=160, actual=None, index="moderate"),
        period("2026-09-11T00:00Z", forecast=160, actual=150, index="moderate"),
    ]}).encode()
    with_a_null = NESO_C.parse(pair, "GB", null_context)
    check("a null beside a value at one timestamp is not a conflict",
          [(r.ts_utc.isoformat(), r.value) for r in with_a_null]
          == [("2026-09-11T00:00:00", 150.0)],
          str([(r.ts_utc.isoformat(), r.value) for r in with_a_null]))
    check("and no drop is written down for it",
          not null_context.dropped, str(null_context.dropped))

    unknown = json.dumps({"data": [period("2026-09-10T00:00Z", actual=1, level="new")]}).encode()
    try:
        NESO_C.parse(unknown, "GB", a_context())
        check("an unknown intensity field stops the parse", False)
    except ParseError as error:
        check("an unknown intensity field stops the parse", "level" in str(error), str(error))

    forecast = NESO_C.parse(payload, "GB", a_context("forecast"))
    check("a forecast run reads the forecast column",
          {r.value for r in forecast} == {160.0, 200.0, 100.0, 120.0},
          str(sorted(r.value for r in forecast)))


@section
def test_rte() -> None:
    """RTE labels the spring-forward hour two times with equal values, and it
    gives one series from two datasets."""
    print("\n9b. the RTE collector")
    from atlas.collectors.rte_eco2mix_odre import COLLECTOR as RTE_C

    def row(stamp, value, hour="02:00"):
        return {"date_heure": stamp, "taux_co2": value, "consommation": 1,
                "nature": hour, "perimetre": "France"}

    payload = json.dumps({"datasets": {
        "eco2mix-national-cons-def": [
            row("2024-03-31T00:00:00+00:00", 25),
            # the time change: one instant, two local labels, equal values
            row("2024-03-31T01:00:00+00:00", 20, "02:00"),
            row("2024-03-31T01:00:00+00:00", 20, "03:00"),
            # the CO2 column is empty on the :15 and :45 rows
            row("2024-03-31T01:15:00+00:00", None),
            # this instant is also in the real-time answer
            row("2024-03-31T02:00:00+00:00", 30),
        ],
        "eco2mix-national-tr": [
            row("2024-03-31T02:00:00+00:00", 99),      # the definitive wins
            row("2024-03-31T02:15:00+00:00", 31),
        ],
    }}).encode()

    context = a_context()
    records = RTE_C.parse(payload, "FR", context)
    by_stamp = {r.ts_utc.isoformat(): r.value for r in records}
    check("the time change gives one record and not an error",
          by_stamp.get("2024-03-31T01:00:00") == 20.0, str(by_stamp))
    check("an empty CO2 cell is skipped", "2024-03-31T01:15:00" not in by_stamp, str(by_stamp))
    check("the definitive value wins over the real-time value",
          by_stamp.get("2024-03-31T02:00:00") == 30.0, str(by_stamp))
    check("the real-time dataset fills the rest",
          by_stamp.get("2024-03-31T02:15:00") == 31.0, str(by_stamp))
    check("the timestamp is UTC and without an offset",
          records[0].ts_utc.tzinfo is None)

    conflict = json.dumps({"datasets": {
        "eco2mix-national-cons-def": [row("2024-03-31T01:00:00+00:00", 20),
                                      row("2024-03-31T01:00:00+00:00", 45)],
        "eco2mix-national-tr": [],
    }}).encode()
    context = a_context()
    records = RTE_C.parse(conflict, "FR", context)
    check("two different values at one instant give no record", not records, str(records))
    check("and the reason is written down", bool(context.dropped), str(context.dropped))


@section
def test_energinet() -> None:
    """Denmark is two price areas. The country value is weighted by load, and
    it is never a plain mean."""
    print("\n9c. the Energinet collector")
    from atlas.collectors.energinet_eds import COLLECTOR as EDS_C

    def co2(stamp, area, value):
        return {"Minutes5UTC": stamp, "Minutes5DK": stamp, "PriceArea": area,
                "CO2Emission": value}

    def load(hour, area, value):
        return {"TimeUTC": hour, "PriceArea": area, "GrossCon": value}

    payload = json.dumps({
        "CO2Emis": [
            co2("2026-09-10T00:00:00", "DK1", 100.0),
            co2("2026-09-10T00:00:00", "DK2", 50.0),
            # one area only: no country value
            co2("2026-09-10T00:05:00", "DK1", 120.0),
            # the hour has no load: no country value
            co2("2026-09-10T01:00:00", "DK1", 100.0),
            co2("2026-09-10T01:00:00", "DK2", 50.0),
        ],
        "GenerationProdTypeExchange": [
            load("2026-09-10T00:00:00", "DK1", 300.0),
            load("2026-09-10T00:00:00", "DK2", 100.0),
        ],
    }).encode()

    context = a_context()
    records = EDS_C.parse(payload, "DK", context)
    check("one country value for one stamp", len(records) == 1, str(len(records)))
    # (100 * 300 + 50 * 100) / 400 = 87.5. A plain mean would give 75.
    check("the roll-up is weighted by load, and not a plain mean",
          records[0].value == 87.5, str(records[0].value))
    check("the record names the zones it came from",
          records[0].zones == "DK1,DK2" and records[0].granularity == "aggregated",
          f"{records[0].zones} {records[0].granularity}")
    check("a stamp with one price area gives no country value",
          all(r.ts_utc.minute != 5 for r in records))
    check("a stamp with no load gives no country value",
          all(r.ts_utc.hour != 1 for r in records))
    check("both gaps are written down", len(context.dropped) == 2, str(context.dropped))


@section
def test_elia() -> None:
    """Elia gives two accounting bases for one hour, and it writes 0.0 for an
    hour that it did not compute. Both were measured on 2026-09-18."""
    print("\n9d. the Elia collector")
    from atlas.collectors.elia_opendata import CONSUMPTION as ELIA_CB
    from atlas.collectors.elia_opendata import PRODUCTION as ELIA_PB

    def row(stamp, production, consumption):
        return {"datetime": stamp, "production": production, "consumption": consumption}

    payload = json.dumps([
        row("2026-09-16T17:00:00+00:00", 150.0, 160.0),
        # ⚠ the evening peak, written as 0.0 by the publisher
        row("2026-09-16T18:00:00+00:00", 0.0, 0.0),
        # only the consumption column is 0.0
        row("2026-09-16T19:00:00+00:00", 200.0, 0.0),
        row("2026-09-16T20:00:00+00:00", 210.0, 190.0),
    ]).encode()

    context = a_context()
    produced = ELIA_PB.parse(payload, "BE", context)
    by_stamp = {r.ts_utc.isoformat(): r.value for r in produced}
    check("a zero gives no record, because it is an outage and not a clean hour",
          "2026-09-16T18:00:00" not in by_stamp, str(by_stamp))
    check("and the reason names the hour",
          any("18:00" in line for line in context.dropped), str(context.dropped))
    check("a zero in the other column does not drop this one",
          by_stamp.get("2026-09-16T19:00:00") == 200.0, str(by_stamp))
    check("the production collector reads the production column",
          by_stamp.get("2026-09-16T20:00:00") == 210.0, str(by_stamp))
    check("the timestamp is UTC and without an offset",
          produced[0].ts_utc.tzinfo is None)

    context = a_context()
    consumed = ELIA_CB.parse(payload, "BE", context)
    by_stamp = {r.ts_utc.isoformat(): r.value for r in consumed}
    check("the consumption collector reads the consumption column",
          by_stamp.get("2026-09-16T20:00:00") == 190.0, str(by_stamp))
    check("a zero in the consumption column gives no record",
          "2026-09-16T19:00:00" not in by_stamp, str(by_stamp))

    # ⚠ The two columns must never land on one key. `basis` is not in the key
    # of the record table, so a shared source id would make the second value a
    # revision of the first.
    check("the two bases carry two source ids",
          ELIA_PB.source_id != ELIA_CB.source_id,
          f"{ELIA_PB.source_id} {ELIA_CB.source_id}")
    check("and the register gives each one its own basis",
          ELIA_PB.basis == "production-based" and ELIA_CB.basis == "consumption-based",
          f"{ELIA_PB.basis} / {ELIA_CB.basis}")
    check("the unit is the unit the publisher states",
          ELIA_PB.unit == "gCO2eq/kWh" == ELIA_CB.unit, ELIA_PB.unit)

    keys = {
        (r.country, r.source_id, r.metric, r.fuel, r.ts_utc, r.kind, r.run_at)
        for r in produced + consumed
    }
    check("so no record of one hour collides with the other basis",
          len(keys) == len(produced) + len(consumed), str(len(keys)))

    # ⚠ Guard 4, the equal repeat. The store holds no key that stops a second
    # copy of one instant, so this guard in the collector is the only one. The
    # key is the UTC instant and not the text of the stamp, because two
    # spellings of one instant are one record.
    twice = json.dumps([
        row("2026-09-16T17:00:00+00:00", 150.0, 160.0),
        row("2026-09-16T17:00:00Z", 150.0, 160.0),
        row("2026-09-16T20:00:00+00:00", 210.0, 190.0),
    ]).encode()
    repeated = ELIA_PB.parse(twice, "BE", a_context())
    check("one instant written two times gives one record",
          [(r.ts_utc.isoformat(), r.value) for r in repeated]
          == [("2026-09-16T17:00:00", 150.0), ("2026-09-16T20:00:00", 210.0)],
          str([(r.ts_utc.isoformat(), r.value) for r in repeated]))

    # A payload that is mostly zeros is a change at the publisher.
    broken = json.dumps([
        row("2026-09-16T17:00:00+00:00", 0.0, 0.0),
        row("2026-09-16T18:00:00+00:00", 0.0, 0.0),
        row("2026-09-16T19:00:00+00:00", 150.0, 150.0),
    ]).encode()
    try:
        ELIA_PB.parse(broken, "BE", a_context())
        check("a payload that is mostly zeros stops the parse", False, "no error")
    except ParseError as error:
        check("a payload that is mostly zeros stops the parse", True, str(error)[:60])

    # Guard 1: a renamed column stops the parse.
    renamed = json.dumps([
        {"datetime": "2026-09-16T17:00:00+00:00", "prod": 150.0, "consumption": 160.0}
    ]).encode()
    try:
        ELIA_PB.parse(renamed, "BE", a_context())
        check("a renamed field stops the parse", False, "no error")
    except ParseError as error:
        check("a renamed field stops the parse", True, str(error)[:60])


# --- 9e. The shared zero guard -----------------------------------------------


# The label and the reason of a caller. `base.py` takes both from the caller,
# because the answer belongs to the publisher and not to the contract.
A_LABEL = "actual"
A_REASON = "This publisher writes 0.0 for a period that it did not compute."


def zero_line_shape(line: str) -> tuple:
    """The three parts of a dropped-zero line: the label, the instant and the
    reason. A line that does not carry all three gives an empty tuple."""
    try:
        label, rest = line.split(" is 0.0 at ", 1)
        stamp, reason = rest.split(". ", 1)
        return bool(label), datetime.fromisoformat(stamp), bool(reason)
    except ValueError:
        return ()


@section
def test_zero_guard() -> None:
    """The zero guard of `base.py`. NESO calls it, and Elia holds its own copy.

    ⚠ A zero is worse than a hole. A hole shows as "no record" on the portal.
    A zero becomes the cleanest period of the day, and it moves the daily mean
    down. Guard 2 takes a 0.0, because `INTENSITY_MIN` is 0.0 and a true zero
    is possible for a different grid. So the zero needs its own guard.
    """
    print("\n9e. the shared zero guard")
    from atlas.collectors.base import ZERO_SHARE_LIMIT, check_zero_share, zero_guard
    from atlas.collectors.elia_opendata import PRODUCTION as ELIA_PB
    from atlas.collectors.neso_carbon_intensity import COLLECTOR as NESO_C
    from atlas.collectors.neso_carbon_intensity import ZERO_REASON

    stamp = datetime(2026, 9, 10, 18, 0)
    context = a_context()
    check("a 0.0 tells the caller to drop the point",
          zero_guard(0.0, stamp, context, A_LABEL, A_REASON) is True)
    check("and the run row keeps the label, the instant and the reason",
          context.dropped == [f"actual is 0.0 at 2026-09-10T18:00:00. {A_REASON}"],
          str(context.dropped))

    # ⚠ Test the boundary and not the zero alone. A publisher can report a
    # small value that is a measurement, and the guard must let it through.
    # NESO gives 14.0 as its smallest value above zero, and Elia gives 17.4.
    # No rule in the code names a floor, so the boundary is 0.0 itself.
    kept = a_context()
    small = [17.4, 14.0, 3.0, 0.1, 0.001, 1e-9, 5e-324]
    refused = [v for v in small if zero_guard(v, stamp, kept, A_LABEL, A_REASON)]
    check("a very small value above zero is a measurement, and it stays",
          not refused, str(refused))
    check("and no reason is written for a value that stays",
          not kept.dropped, str(kept.dropped))
    # -0.0 is a zero, and it must not become the cleanest period of the day.
    check("a negative zero is a zero", zero_guard(-0.0, stamp, kept, A_LABEL, A_REASON))

    # ⚠ A null is an absence and not a value. It has its own path in every
    # collector, and the zero guard must not take it.
    null_context = a_context()
    check("a null does not fire the guard",
          zero_guard(None, stamp, null_context, A_LABEL, A_REASON) is False)
    check("and a null writes no line, because it is a different case",
          not null_context.dropped, str(null_context.dropped))

    # The share limit stops a payload that is mostly zeros. The limit is the
    # count above the share, so the share itself still goes through.
    check("the shared limit is the one the module states", ZERO_SHARE_LIMIT == 0.5,
          str(ZERO_SHARE_LIMIT))
    try:
        check_zero_share("GB", 6, 12, "measured.")
        check("a payload at the limit goes through", True)
    except ParseError as error:
        check("a payload at the limit goes through", False, str(error)[:60])
    try:
        check_zero_share("GB", 7, 12, "The measured share is 6 of 152,154.")
        check("a payload above the limit stops the parse", False, "no error")
    except ParseError as error:
        check("a payload above the limit stops the parse",
              "7 of 12" in str(error) and "152,154" in str(error), str(error)[:80])
    try:
        check_zero_share("GB", 0, 0, "measured.")
        check("a payload with no value raises nothing", True)
    except ParseError as error:
        check("a payload with no value raises nothing", False, str(error)[:60])

    # --- the guard on the real path of NESO ---
    def period(stamp, **intensity):
        return {"from": stamp, "to": stamp, "intensity": intensity}

    payload = json.dumps({"data": [
        # ⚠ the publisher writes 0.0 for a half hour that it did not compute
        period("2026-09-10T18:00Z", forecast=200, actual=0, index="high"),
        # the next value up in the store. It is small, and it is a measurement.
        period("2026-09-10T18:30Z", forecast=200, actual=3.0, index="low"),
        # a null is an absence, and it takes the other path
        period("2026-09-10T19:00Z", forecast=200, actual=None, index="high"),
        period("2026-09-10T19:30Z", forecast=200, actual=150, index="moderate"),
    ]}).encode()

    context = a_context()
    records = NESO_C.parse(payload, "GB", context)
    by_stamp = {r.ts_utc.isoformat(): r.value for r in records}
    check("a zero gives no record on the real path",
          "2026-09-10T18:00:00" not in by_stamp, str(by_stamp))
    check("a small value above zero gives a record",
          by_stamp.get("2026-09-10T18:30:00") == 3.0, str(by_stamp))
    check("a null gives no record", "2026-09-10T19:00:00" not in by_stamp, str(by_stamp))
    check("the rest of the payload is kept",
          by_stamp.get("2026-09-10T19:30:00") == 150.0, str(by_stamp))
    check("one line goes in the run row, and the null adds none",
          context.dropped == [f"actual is 0.0 at 2026-09-10T18:00:00. {ZERO_REASON}"],
          str(context.dropped))

    # ⚠ The two implementations of one rule must write one shape of line, or
    # an operator reads two different messages for one kind of defect.
    elia_context = a_context()
    ELIA_PB.parse(json.dumps([
        {"datetime": "2026-09-16T18:00:00+00:00", "production": 0.0, "consumption": 0.0},
        {"datetime": "2026-09-16T19:00:00+00:00", "production": 210.0, "consumption": 190.0},
    ]).encode(), "BE", elia_context)
    elia_line = (elia_context.dropped or [""])[0]
    shared_line = (context.dropped or [""])[0]
    check("the Elia copy writes the line of the shared guard",
          zero_line_shape(elia_line) == (True, datetime(2026, 9, 16, 18), True)
          and zero_line_shape(shared_line) == (True, datetime(2026, 9, 10, 18), True),
          f"{elia_line} | {shared_line}")

    # A payload that is mostly zeros is a change at the publisher, and the
    # store must not take it. Two zeros of three values are above the limit.
    mostly = json.dumps({"data": [
        period("2026-09-10T18:00Z", actual=0, index="high"),
        period("2026-09-10T18:30Z", actual=0, index="high"),
        period("2026-09-10T19:00Z", actual=150, index="moderate"),
    ]}).encode()
    try:
        NESO_C.parse(mostly, "GB", a_context())
        check("a payload that is mostly zeros stops the parse", False, "no error")
    except ParseError as error:
        check("a payload that is mostly zeros stops the parse",
              "2 of 3" in str(error), str(error)[:80])


# --- 10. The --redo-ok repair -------------------------------------------------


# The frozen day of the store, and the day of the repair. On 2026-09-23 the
# command
#     python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18
# read 2026-09-18 again for Energinet DK, NESO GB and RTE FR, and it wrote 240
# records. Before the flag, no command asked for that day again, because the
# newest run row of the day said `ok`. RUNNING.md section 2.
FROZEN_DAY = date(2026, 9, 18)
REPAIR_DAY = date(2026, 9, 23)


class FixedToday(date):
    """`date` with a fixed `today`.

    ⚠ `cmd_backfill` computes `force_recent_days` from `date.today()`. A test
    that reads the clock of the machine gets a different number every day, so
    the arithmetic would never be pinned. This class holds the day of the
    repair, and the number that the tests below name is therefore stable.
    """

    @classmethod
    def today(cls) -> date:
        return REPAIR_DAY


class FakeCollector:
    """One source with one country. It makes no request."""

    source_id = EDS
    available_from = date(2020, 1, 1)
    max_span_days = 400

    @staticmethod
    def countries() -> list[str]:
        return ["DK"]


def call_cli(argv: list[str]) -> dict:
    """Run one command of `atlas/__main__.py` offline.

    The lock, the store, the HTTP client, the collection and the export are
    all replaced, so the command takes no lock file, opens no store and makes
    no network request. The helper gives back what the command did:

        events   "lock", "store", "http", "collect", "export", in order
        calls    the arguments of each `runner.collect_measurements`
        code     the exit code, or None when the command raised SystemExit
        refusal  the text of the SystemExit, or None

    The order of `events` is the safety property of this section. A command
    that stops on a mistake of the operator must stop before the lock.
    """
    from atlas import __main__ as cli
    from atlas import export as export_module
    from atlas import lock as lock_module
    from atlas import net as net_module
    from atlas import runner as runner_module

    events: list[str] = []
    calls: list[dict] = []

    @contextlib.contextmanager
    def fake_hold(_holder, wait_seconds=None):
        events.append("lock")
        yield

    class FakeStore:
        def __init__(self, *_args, **_kw):
            events.append("store")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class FakeHttp:
        def __init__(self, *_args, **_kw):
            events.append("http")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_collect(_store, _http, collector, isos, start, end, **kw):
        events.append("collect")
        calls.append(
            {
                "source_id": collector.source_id,
                "isos": list(isos),
                "start": start,
                "end": end,
                "force_recent_days": kw.get("force_recent_days", 0),
                "retry_fail_days": kw.get("retry_fail_days"),
            }
        )
        return {"windows": 1, "new": 0, "revisions": 0, "fail": 0, "empty": 0}

    def fake_export(_store):
        events.append("export")
        return []

    saved = [
        (cli, "date", cli.date),
        (cli, "Store", cli.Store),
        (cli, "_sources", cli._sources),
        (lock_module, "hold", lock_module.hold),
        (net_module, "Http", net_module.Http),
        (runner_module, "collect_measurements", runner_module.collect_measurements),
        (export_module, "run", export_module.run),
    ]
    cli.date = FixedToday
    cli.Store = FakeStore
    cli._sources = lambda _args: [FakeCollector]
    lock_module.hold = fake_hold
    net_module.Http = FakeHttp
    runner_module.collect_measurements = fake_collect
    export_module.run = fake_export

    outcome = {"events": events, "calls": calls, "code": None, "refusal": None}
    try:
        outcome["code"] = cli.main(argv)
    except SystemExit as error:
        outcome["refusal"] = str(error)
    finally:
        for target, name, value in saved:
            setattr(target, name, value)
    return outcome


@section
def test_redo_ok_cli() -> None:
    """The flag, the span that it computes, and the refusal that guards it."""
    print("\n10. the --redo-ok repair")
    from atlas import __main__ as cli

    parser = cli.build_parser()

    # --- the command line that the documents name as the one repair ---
    args = parser.parse_args(
        ["backfill", "--redo-ok", "--from", "2026-09-18", "--to", "2026-09-18",
         "--source", EDS, "--country", "DK"]
    )
    check("--redo-ok sets redo_ok", args.redo_ok is True, str(args.redo_ok))
    check("--from and --to parse to dates",
          (args.since, args.to) == (FROZEN_DAY, FROZEN_DAY),
          f"{args.since} {args.to}")
    check("the source and the country travel with the flag",
          (args.source, args.country) == (EDS, ["DK"]),
          f"{args.source} {args.country}")

    plain = parser.parse_args(["backfill"])
    check("backfill without the flag reads redo_ok False",
          plain.redo_ok is False, str(plain.redo_ok))
    check("and it names no window", (plain.since, plain.to) == (None, None),
          f"{plain.since} {plain.to}")

    with contextlib.redirect_stderr(io.StringIO()):
        try:
            parser.parse_args(["daily", "--redo-ok", "--from", "2026-09-18"])
            daily_took_it = True
        except SystemExit:
            daily_took_it = False
    check("only backfill takes --redo-ok", not daily_took_it)

    # --- force_recent_days = (today - start).days + 1 ---
    run = call_cli(
        ["backfill", "--redo-ok", "--from", "2026-09-18", "--to", "2026-09-18"]
    )
    check("the repair runs to the end",
          run["code"] == 0 and run["refusal"] is None,
          f'{run["code"]} {run["refusal"]}')
    check("it reaches the collection one time",
          len(run["calls"]) == 1, str(run["events"]))
    call = run["calls"][0] if run["calls"] else {}
    check("the window is the one day that the operator named",
          (call.get("start"), call.get("end")) == (FROZEN_DAY, FROZEN_DAY),
          f'{call.get("start")} {call.get("end")}')
    # ⚠ (2026-09-23 − 2026-09-18).days is 5, and `days_to_collect` keeps an
    # `ok` day only while `day > today - force_recent_days`. 5 therefore stops
    # one day short of 2026-09-18, and the 240 records of that day stay out of
    # reach. The `+ 1` is the whole repair. Section 10b holds the proof on a
    # store.
    check("force_recent_days is (today - start).days + 1, which is 6",
          call.get("force_recent_days") == 6, str(call.get("force_recent_days")))

    wide = call_cli(["backfill", "--redo-ok", "--from", "2026-09-01"])
    check("a wider window gives a wider span, and 22 days give 23",
          bool(wide["calls"]) and wide["calls"][0]["force_recent_days"] == 23,
          str(wide["calls"]))
    check("and without --to the command ends at today",
          bool(wide["calls"]) and wide["calls"][0]["end"] == REPAIR_DAY,
          str(wide["calls"]))

    # --- the refusal, and the order that makes it safe ---
    refused = call_cli(["backfill", "--redo-ok"])
    check("--redo-ok without --from stops the command",
          refused["refusal"] is not None, str(refused["code"]))
    check("the message names --from",
          "--from" in (refused["refusal"] or ""), (refused["refusal"] or "")[:60])
    # The order is the safety property, and not the exit alone. A waiter holds
    # for `config.LOCK_WAIT_SECONDS`, which is 600 s, and DuckDB gives the
    # store file to one process. A refusal after the lock would make a typo
    # cost that wait, and would shut out a run that is in the right.
    check("it refuses before the lock and before the store",
          refused["events"] == [], str(refused["events"]))

    refused_to = call_cli(["backfill", "--redo-ok", "--to", "2026-09-18"])
    check("--to alone does not stand in for --from",
          refused_to["refusal"] is not None and refused_to["events"] == [],
          f'{refused_to["refusal"]} {refused_to["events"]}')

    check("the accepted command takes the lock first, and the store after it",
          run["events"][:2] == ["lock", "store"], str(run["events"]))

    # --- the default behaviour does not move ---
    default = call_cli(["backfill", "--from", "2026-09-18", "--to", "2026-09-18"])
    check("backfill without the flag still passes 0",
          bool(default["calls"]) and default["calls"][0]["force_recent_days"] == 0,
          str(default["calls"]))
    check("and backfill writes no export",
          "export" not in default["events"], str(default["events"]))

    daily = call_cli(["daily", "--no-export"])
    check("daily still passes RECENT_DAYS",
          bool(daily["calls"])
          and daily["calls"][0]["force_recent_days"] == config.RECENT_DAYS,
          str(daily["calls"]))
    check("daily keeps its limit on an old fail day",
          bool(daily["calls"])
          and daily["calls"][0]["retry_fail_days"] == config.DAILY_RETRY_FAIL_DAYS,
          str(daily["calls"]))
    check("--no-export skips the export",
          "export" not in daily["events"], str(daily["events"]))

    daily_full = call_cli(["daily"])
    check("daily writes the export at the end",
          daily_full["events"][-1:] == ["export"], str(daily_full["events"]))


@section
def test_redo_ok_days() -> None:
    """The day that `--redo-ok` reaches, and the day that it does not.

    `days_to_collect` is the one gate between the command and the network, and
    it is the thing that `--redo-ok` changes. A day whose newest run row says
    `ok` passes that gate only while `day > today - force_recent_days`. This
    is the test that would have caught the defect.
    """
    print("\n10b. the day that --redo-ok reaches")
    stamp = datetime(2026, 9, 18, 23, 30)
    with Store(path=TEMP / "redo.duckdb") as store:
        def mark(day: date, status: str = "ok") -> None:
            store.write_runs([
                RunRow(
                    source_id=EDS, country="DK", day=day, kind="actual",
                    status=status, rows=288, started_at=stamp, finished_at=stamp,
                )
            ])

        def ask(force: int, start: date = FROZEN_DAY,
                end: date = FROZEN_DAY + timedelta(days=1)) -> list:
            # `days_to_collect` stops before `end`, so the caller adds 1 day.
            return store.days_to_collect(
                EDS, "DK", "actual", start, end,
                force_recent_days=force, today=REPAIR_DAY,
            )

        mark(FROZEN_DAY)
        check("a plain backfill withholds the frozen day", ask(0) == [], str(ask(0)))
        check("the daily window of 2 days withholds it too",
              ask(config.RECENT_DAYS) == [], str(ask(config.RECENT_DAYS)))
        # ⚠ 5 is `(today - start).days` with no `+ 1`. It stops one day short,
        # and the frozen day stays unreachable. 6 is the number that
        # `cmd_backfill` computes, and it is the number that works.
        check("a span of 5 days still withholds it", ask(5) == [], str(ask(5)))
        check("the span of 6 days that cmd_backfill computes brings it back",
              ask(6) == [FROZEN_DAY], str(ask(6)))

        mark(date(2026, 9, 17))
        window = ask(6, date(2026, 9, 17), date(2026, 9, 19))
        check("the span covers the first day of the window and no day before it",
              window == [FROZEN_DAY], str(window))

        open_day = ask(0, date(2026, 9, 17), date(2026, 9, 20))
        check("a day with no run row needs no flag",
              open_day == [date(2026, 9, 19)], str(open_day))


# --- 11. Two more properties of the coverage model ----------------------------


@section
def test_coverage_edges() -> None:
    """A negative `absent`, and `hole_hours` on a series that changed its step.

    Both are documented behaviour of `_series_coverage`, and neither had a
    test. A later change that reads either of them as a defect moves a
    headline number of the project, and no number in `health.json` says that
    it happened.
    """
    print("\n11. two more properties of the coverage model")
    from atlas import export

    # NL: one day that holds both steps. 18 records at 60 minutes from 00:00,
    # then 13 records at 30 minutes from 17:30. The modal step of the day is
    # 60, so the model expects 24 periods and the day holds 31.
    nl_stamps = [COVER_DAY + timedelta(hours=h) for h in range(18)]
    nl_stamps += [
        COVER_DAY + timedelta(hours=17, minutes=30 * (k + 1)) for k in range(13)
    ]
    # PL: a step change between two days. Day 1 runs at 60 minutes and day 2 at
    # 30, and the series holds every period of both parts.
    pl_stamps = [COVER_DAY + timedelta(hours=h) for h in range(24)]
    pl_stamps += [COVER_DAY + timedelta(days=1, minutes=30 * k) for k in range(48)]

    with Store(path=TEMP / "coverage-edges.duckdb") as store:
        store.insert_records(a_cover_series("NL", EC, nl_stamps))
        store.insert_records(a_cover_series("PL", EC, pl_stamps))
        store.write_runs(
            [a_run_day(EC, "NL", 0)] + [a_run_day(EC, "PL", day) for day in range(2)]
        )
        health = export._health(store)

    fields = health["fields"]
    rows = {(row[0], row[1], row[2]): dict(zip(fields, row)) for row in health["rows"]}

    # --- a negative absent ---
    nl_row = rows[(EC, "NL", "actual")]
    check("the day of a step change holds both steps",
          nl_row["records"] == 31, str(nl_row["records"]))
    check("the expected count follows the modal step of that day, which is 60",
          (nl_row["expected"], nl_row["step_minutes"]) == (24, 60),
          f'{nl_row["expected"]} {nl_row["step_minutes"]}')
    # ⚠ A clamp of `absent` to 0 reads as "this series is complete", and the
    # step change that made the figure negative then has no mark anywhere in
    # the file. On 2026-09-23 the store holds two of them: NL at −2 and PL
    # at −3.
    check("a negative absent is kept, and not clamped to zero",
          nl_row["absent"] == -7, str(nl_row["absent"]))
    check("a negative absent marks a step change, and not a surplus of records",
          nl_row["records"] > nl_row["expected"],
          f'{nl_row["records"]} {nl_row["expected"]}')

    # --- hole_hours on a series that changed its step ---
    pl_row = rows[(EC, "PL", "actual")]
    check("a series that changed its step holds every period of both parts",
          (pl_row["records"], pl_row["expected"], pl_row["absent"]) == (72, 72, 0),
          f'{pl_row["records"]} {pl_row["expected"]} {pl_row["absent"]}')
    check("the step of the series is the finer step that most records ran at",
          pl_row["step_minutes"] == 30, str(pl_row["step_minutes"]))
    # ⚠ `hole_hours` is the widest interval of the series. On a series that
    # changed its step, that interval is the coarse early step, and it is not a
    # hole. A reader who divides 1.0 hour by `step_minutes` 30 counts 2 absent
    # periods that do not exist, and `absent` is 0 on the same row.
    # energy-charts DE reads the same pair on 2026-09-23: `hole_hours` 1.0
    # against `step_minutes` 30.
    check("hole_hours reports the coarse early step, and not a hole",
          pl_row["hole_hours"] == 1.0, str(pl_row["hole_hours"]))
    check("the widest interval sits in the early part of the span",
          pl_row["hole_from"] is not None
          and COVER_DAY <= pl_row["hole_from"]
          and pl_row["hole_to"] < COVER_DAY + timedelta(days=1),
          f'{pl_row["hole_from"]} to {pl_row["hole_to"]}')
    check("so hole_hours above step_minutes states no absence by itself",
          pl_row["absent"] == 0 and pl_row["hole_hours"] * 60 > pl_row["step_minutes"],
          f'{pl_row["absent"]} {pl_row["hole_hours"]} {pl_row["step_minutes"]}')


# --- 12. The rebuild ----------------------------------------------------------


# The one source that these sections collect from. `energy_charts_co2eq.py` is
# the collector that sections 1 and 2 already parse with, so a rebuilt row can
# be compared with the record of a parse that those sections pin.
SOURCE = "energy-charts-co2eq"

# The collection stamps of the fixtures. Every one is in September 2026,
# because `--from` and `--to` count the COLLECTION day, and not the day of the
# data. `atlas/rebuild.py` section 5.
COLLECTED = datetime(2026, 9, 17, 10, 0)
COLLECTED_AGAIN = datetime(2026, 9, 18, 10, 0)
SNAPPED = datetime(2026, 9, 17, 11, 0)

# The snapshot instant of a collection run. `runner.snap_forecasts` reads the
# clock one time for every country of the run, so it is earlier than the stamp
# in the file name. 15 minutes here.
SNAP_RUN_AT = datetime(2026, 9, 17, 10, 45)

# The measurement fixture crosses this instant, so its records touch 2 UTC days.
MIDNIGHT = datetime(2026, 9, 15, 0, 0)

EPOCH = datetime(1970, 1, 1)

# The 12 columns that a rebuild must reproduce exactly. `atlas/rebuild.py`
# section 3 names them. `collected_at`, `raw_ref`, `run_at` and `horizon_min`
# are not in the list, and that section gives the reason for each one.
REBUILT_COLUMNS = (
    "country", "source_id", "metric", "fuel", "ts_utc", "value", "unit",
    "basis", "scope", "granularity", "zones", "kind",
)


def an_epoch(at: datetime) -> int:
    """The UTC epoch second of a UTC timestamp with no zone.

    `unix_seconds` of the energy-charts payload holds this number.
    """
    return int((at - EPOCH).total_seconds())


@contextlib.contextmanager
def a_raw_tree(name: str):
    """A fresh store directory with a `raw/` tree, and `config` put back after.

    `atlas rebuild` reads three paths of `config`: it walks `config.RAW_DIR`, it
    reads the expected hashes from `config.DB_PATH`, and it takes
    `config.LOCK_PATH`.

    ⚠ A test that leaves those paths at their values walks the real
    `store/raw/` of the machine, and it opens the real `store/atlas.duckdb`.
    The store is the evidence behind every published figure. So this block
    moves all 6 paths, and the `finally` puts all 6 back.
    """
    keys = ("STORE_DIR", "DB_PATH", "RAW_DIR", "LOG_DIR", "TMP_DIR", "LOCK_PATH")
    saved = {key: getattr(config, key) for key in keys}
    root = TEMP / name
    config.STORE_DIR = root
    config.DB_PATH = root / "atlas.duckdb"
    config.RAW_DIR = root / "raw"
    config.LOG_DIR = root / "log"
    config.TMP_DIR = root / "tmp"
    config.LOCK_PATH = root / "atlas.lock"
    config.ensure_dirs()
    try:
        yield root
    finally:
        for key, value in saved.items():
            setattr(config, key, value)


def a_body(stamps: list[datetime], values: list, forecast: list | None = None) -> bytes:
    """One energy-charts payload, in the 4 fields that the API serves."""
    return json.dumps(
        {
            "unix_seconds": [an_epoch(stamp) for stamp in stamps],
            "co2eq": values,
            "co2eq_forecast": forecast if forecast is not None else [None] * len(stamps),
            "deprecated": False,
        }
    ).encode()


def a_payload(iso: str, stamps: list[datetime], values: list, at: datetime,
              forecast: list | None = None, source_id: str = SOURCE,
              snap: bool = False) -> str:
    """Write one gzipped payload in the fixture tree. It gives the `raw_ref`.

    `raw.write` makes the directory and the name, so a fixture payload carries
    the shape of a collected one. `snap=True` writes the `-snap` file name that
    the current code makes. A `source_id` that ends in `-snap` writes the older
    directory form. `atlas/rebuild.py` section 5 holds both.
    """
    country = f"{iso}-snap" if snap else iso
    return raw.write(source_id, country, a_body(stamps, values, forecast), at)


def a_parse(ref: str, iso: str, at: datetime, kind: str = "actual",
            run_at: datetime | None = None) -> list:
    """The records that the collector itself makes from a payload on disk.

    This is the path that `atlas daily` runs, and it is the reference that the
    rebuilt rows must be equal to. `raw.read` compares the file with the hash
    in the `raw_ref`, so a fixture that changed stops here.
    """
    context = ParseContext(kind=kind, collected_at=at, raw_ref=ref, run_at=run_at)
    return COLLECTOR.parse(raw.read(ref), iso, context)


def a_shape(record) -> tuple:
    """The 12 columns of one record, in the order of `REBUILT_COLUMNS`."""
    return tuple(getattr(record, name) for name in REBUILT_COLUMNS)


def a_relative(ref: str) -> str:
    """The path part of a `raw_ref`. The report of the command prints this."""
    return ref.partition("#sha256:")[0]


def a_rebuild(into: Path, **flags) -> tuple[int, str]:
    """Run the command into `into`. It gives (exit code, the printed report).

    The command writes the reason of every skipped payload to the log as well.
    The logger of the command is quiet here, because the checks read the
    printed report, and 4 ERROR lines in a green run read like a failure.
    """
    logger = logging.getLogger("atlas.rebuild")
    level = logger.level
    logger.setLevel(logging.CRITICAL)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = rebuild.run(into=str(into), **flags)
    finally:
        logger.setLevel(level)
    return code, buffer.getvalue()


def refusal_of(into: Path) -> str:
    """The text of the `SystemExit` that a bad `--into` raises.

    It gives a line that starts with NO REFUSAL when the command ran instead,
    so a check that expects a refusal fails and prints what happened.
    """
    try:
        code, text = a_rebuild(into)
    except SystemExit as error:
        return str(error)
    return f"NO REFUSAL: exit {code}. {text[:120]}"


@section
def test_rebuild_refusals() -> None:
    """The refusals of `--into`, and the point in the run where they happen.

    ⚠ The refusal of a directory that already holds `atlas.duckdb` is the
    safety property of the command. The store is the evidence behind every
    published figure, and a rebuild that writes over one destroys it. No number
    in the portal says that it happened.
    """
    print("\n12. the rebuild refusals")
    from atlas import __main__ as cli
    from atlas import lock as lock_module

    with a_raw_tree("rebuild-refusals") as root:
        ref = a_payload("DE", [MIDNIGHT, MIDNIGHT + timedelta(minutes=15)],
                        [400.0, 410.0], COLLECTED)
        with Store(path=config.DB_PATH) as store:
            store.insert_records(a_parse(ref, "DE", COLLECTED))
        live = config.DB_PATH.read_bytes()

        refusal = refusal_of(root)
        check("--into the directory of the live store refuses",
              "is the live store" in refusal, refusal[:120])
        check("and the refusal leaves no lock file", not config.LOCK_PATH.exists())

        inside = config.RAW_DIR / "new-store"
        refusal = refusal_of(inside)
        check("--into a directory under raw/ refuses", "is inside" in refusal,
              refusal[:120])
        check("and no directory appears in the payload tree", not inside.exists())

        # The order of the run. ⚠ A refusal that comes after the lock makes the
        # command wait out a `daily` run of 600 s, and then refuse anyway.
        events: list[str] = []

        @contextlib.contextmanager
        def watched_hold(_holder, wait_seconds=None):
            events.append("lock")
            yield

        saved_hold = lock_module.hold
        lock_module.hold = watched_hold
        try:
            refusal = refusal_of(root)
        finally:
            lock_module.hold = saved_hold
        check("a refusal comes before the store lock", events == [], str(events))

        out = TEMP / "rebuild-refusals-out"
        code, text = a_rebuild(out)
        check("a rebuild makes a directory that is not there yet",
              code == 0 and (out / "atlas.duckdb").exists(), text[-160:])
        made = (out / "atlas.duckdb").read_bytes()

        refusal = refusal_of(out)
        check("a second rebuild into the same directory refuses",
              "is already there" in refusal, refusal[:120])
        check("and the store that was there keeps every byte",
              (out / "atlas.duckdb").read_bytes() == made)

        check("no rebuild wrote one byte to the live store",
              config.DB_PATH.read_bytes() == live)

        # The CLI. `--into` is required, and `--to` must reach `until`.
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                cli.main(["rebuild"])
            check("--into is required", False, "the command ran with no --into")
        except SystemExit as error:
            check("--into is required", error.code == 2, str(error.code))
            check("and the message names the flag", "--into" in stderr.getvalue(),
                  stderr.getvalue()[-90:])

        seen: dict = {}
        saved_run = rebuild.run
        rebuild.run = lambda **flags: seen.update(flags) or 0
        try:
            code = cli.main(["rebuild", "--into", str(TEMP / "rebuild-cli"),
                             "--source", SOURCE, "--from", "2026-09-17",
                             "--to", "2026-09-18"])
        finally:
            rebuild.run = saved_run
        check("the CLI gives --into to the command",
              code == 0 and seen.get("into") == str(TEMP / "rebuild-cli"), str(seen))
        check("--source reaches the command", seen.get("source") == SOURCE, str(seen))
        check("--from and --to reach the command as since and until",
              seen.get("since") == date(2026, 9, 17)
              and seen.get("until") == date(2026, 9, 18), str(seen))


@section
def test_rebuild_skips() -> None:
    """A bad payload is reported and skipped, and the walk goes on.

    The exit code is the contract that a script reads: 0 when every payload
    parsed, and non-zero when the walk skipped one or found none.
    """
    print("\n12b. the rebuild skips")
    stamps = [MIDNIGHT, MIDNIGHT + timedelta(minutes=15)]

    with a_raw_tree("rebuild-skips") as root:
        good = a_payload("DE", stamps, [400.0, 410.0], COLLECTED)
        changed = a_payload("FR", stamps, [500.0, 510.0],
                            COLLECTED + timedelta(minutes=1))
        empty = a_payload("NL", stamps, [None, None], COLLECTED + timedelta(minutes=3))
        # `zones.json` is the definition of a country, and ZZ is not in it.
        unknown = a_payload("ZZ", stamps, [400.0, 410.0],
                            COLLECTED + timedelta(minutes=5))

        # Guard 1 of the collector: the field set of the payload changed.
        broken_body = json.dumps(
            {
                "unix_seconds": [an_epoch(MIDNIGHT)],
                "co2eq_new_name": [400.0],
                "co2eq_forecast": [None],
                "deprecated": False,
            }
        ).encode()
        broken = raw.write(SOURCE, "BE", broken_body, COLLECTED + timedelta(minutes=2))

        # A payload that stops in the middle, which is what a disk that filled
        # up leaves. gzip carries a CRC32 of the bytes it packed, so the read
        # fails, and the walk must survive that.
        torn = config.RAW_DIR / SOURCE / "2026-09" / "20260917T100400Z-AT.json.gz"
        whole = gzip.compress(a_body(stamps, [400.0, 410.0]))
        torn.write_bytes(whole[: len(whole) // 2])
        torn_relative = torn.relative_to(config.STORE_DIR).as_posix()

        with Store(path=config.DB_PATH) as store:
            store.insert_records(a_parse(good, "DE", COLLECTED))
            store.insert_records(
                a_parse(changed, "FR", COLLECTED + timedelta(minutes=1))
            )
            # The broken payload holds no record, so only a run row can name
            # it. `stored_hashes` reads the `raw_ref` of both tables.
            store.write_runs(
                [
                    RunRow(
                        source_id=SOURCE, country="BE", day=MIDNIGHT.date(),
                        kind="actual", status="ok", http_status=200, raw_ref=broken,
                        started_at=COLLECTED + timedelta(minutes=2),
                        finished_at=COLLECTED + timedelta(minutes=2),
                    )
                ]
            )

        # The bytes of one payload move under the hash that the store holds.
        with gzip.open(raw.path_of(changed), "wb") as handle:
            handle.write(a_body(stamps, [501.0, 511.0]))

        out = TEMP / "rebuild-skips-out"
        code, text = a_rebuild(out)
        check("the hash check runs against the live store",
              "hash check   against the 3 payload(s)" in text,
              text.splitlines()[0] if text else "")
        check("a payload whose sha256 moved is skipped and named",
              f"SKIPPED  {a_relative(changed)}: the sha256 does not match" in text,
              text[:400])
        check("a payload that fails to parse is skipped and named",
              f"SKIPPED  {a_relative(broken)}: ParseError: the field set changed"
              in text, text[:400])
        check("a file that gzip cannot read is skipped and named",
              f"SKIPPED  {torn_relative}: the file does not read" in text, text[:400])
        check("a country that zones.json does not hold is skipped and named",
              f"SKIPPED  {a_relative(unknown)}: KeyError" in text, text[:400])
        check("a payload that holds no value is reported, and not skipped",
              f"NO RECORD  {a_relative(empty)}" in text
              and f"SKIPPED  {a_relative(empty)}" not in text, text[:400])
        check("the summary counts the 2 payloads that parsed",
              "parsed       2 of 6" in text, text[:200])
        check("and the 4 that it skipped", "skipped      4" in text, text[:200])
        check("the exit code is non-zero when a payload was skipped", code == 1,
              str(code))

        with Store(path=out / "atlas.duckdb", read_only=True) as store:
            rows = store.query(
                "SELECT country, ts_utc, value FROM record_current ORDER BY ts_utc"
            )
        check("the good payload is in the store, so no skip stopped the walk",
              rows == [("DE", stamps[0], 400.0), ("DE", stamps[1], 410.0)], str(rows))

        # Section 4 of the module: with no live store there is nothing to
        # compare against, and the self-hash mode takes the changed payload.
        config.DB_PATH = root / "no-store.duckdb"
        alone = TEMP / "rebuild-skips-alone"
        code, text = a_rebuild(alone)
        check("with no live store the check is the file against itself",
              "the file against itself only" in text,
              text.splitlines()[0] if text else "")
        with Store(path=alone / "atlas.duckdb", read_only=True) as store:
            french = store.query(
                "SELECT value FROM record_current WHERE country = 'FR' ORDER BY ts_utc"
            )
        check("so a payload that changed under its hash goes in the store",
              french == [(501.0,), (511.0,)], str(french))
        check("and the 3 payloads that cannot be read still give exit 1",
              code == 1, str(code))

    with a_raw_tree("rebuild-clean"):
        good = a_payload("DE", stamps, [400.0, 410.0], COLLECTED)
        empty = a_payload("NL", stamps, [None, None], COLLECTED + timedelta(minutes=3))
        with Store(path=config.DB_PATH) as store:
            store.insert_records(a_parse(good, "DE", COLLECTED))

        code, text = a_rebuild(TEMP / "rebuild-clean-out")
        check("the exit code is 0 when every payload parsed", code == 0, str(code))
        check("a payload that holds no value does not make the run fail",
              "skipped      0" in text and f"NO RECORD  {a_relative(empty)}" in text,
              text[:400])
        check("a payload that no raw_ref names is reported",
              f"NOT IN THE LIVE STORE  {a_relative(empty)}" in text, text[:400])

        # A walk that finds no payload is a wrong flag, and a script must see
        # it. An empty store is not a rebuild.
        none = TEMP / "rebuild-none"
        code, text = a_rebuild(none, until=date(2026, 9, 16))
        check("a walk that finds no payload exits non-zero", code == 1, str(code))
        check("and it names the 3 flags that select one",
              "Check --source, --from and --to." in text, text[:200])
        check("and it says that the 2 date flags count the collection day",
              "count the collection date" in text, text[:400])
        check("and it writes no store", not (none / "atlas.duckdb").exists())


@section
def test_rebuild_records() -> None:
    """The rebuilt rows against the parse of the collector itself.

    ⚠ Two columns of a rebuild are not the collected ones, and both are here:
    a forecast `run_at` is the collection time, so `horizon_min` is smaller
    than the stored one; and `http_status` is NULL in every run row, so
    `health.json` of a rebuilt store reports 0 failed days. A reader who takes
    either number for the collected one gets a wrong answer.
    """
    print("\n12c. the rebuilt records")
    with a_raw_tree("rebuild-records"):
        # The measurement payload crosses midnight UTC, so its records touch 2
        # UTC days, and the run table must hold one row for each of them.
        stamps = [MIDNIGHT - timedelta(minutes=15), MIDNIGHT,
                  MIDNIGHT + timedelta(minutes=15)]
        first = a_payload("DE", stamps, [400.0, 410.0, None], COLLECTED)
        # The next day the publisher corrects the second value.
        second = a_payload("DE", stamps, [400.0, 444.0, None], COLLECTED_AGAIN)

        # The snapshot, in the file-name form that the current code writes. The
        # first point lies before the collection stamp.
        snap_stamps = [SNAP_RUN_AT, SNAPPED + timedelta(hours=1),
                       SNAPPED + timedelta(hours=2)]
        snap = a_payload("FR", snap_stamps, [None, None, None], SNAPPED,
                         forecast=[280.0, 300.0, 310.0], snap=True)

        # The older directory form of a snapshot. RUNNING.md section 4.
        legacy_at = SNAPPED - timedelta(hours=2)
        legacy = a_payload("GB", [legacy_at + timedelta(hours=3)], [None], legacy_at,
                           forecast=[120.0], source_id=f"{SOURCE}-snap")

        with Store(path=config.DB_PATH) as store:
            store.insert_records(a_parse(first, "DE", COLLECTED))
            store.insert_records(a_parse(second, "DE", COLLECTED_AGAIN))
            store.insert_records(
                a_parse(snap, "FR", SNAPPED, kind="forecast", run_at=SNAP_RUN_AT)
            )
            store.insert_records(
                a_parse(legacy, "GB", legacy_at, kind="forecast", run_at=legacy_at)
            )

        out = TEMP / "rebuild-records-out"
        code, text = a_rebuild(out)
        check("every fixture payload parsed",
              code == 0 and "parsed       4 of 4" in text, text[:200])

        columns = ", ".join(REBUILT_COLUMNS)
        with Store(path=out / "atlas.duckdb", read_only=True) as store:
            german = store.query(
                f"SELECT {columns} FROM record_current WHERE country = 'DE' "
                "ORDER BY ts_utc"
            )
            history = store.query(
                "SELECT value, revision, raw_ref FROM record WHERE country = 'DE' "
                "AND ts_utc = ? ORDER BY revision", [MIDNIGHT]
            )
            kept = store.query(
                "SELECT raw_ref FROM record_current WHERE country = 'DE' "
                "AND ts_utc = ?", [stamps[0]]
            )
            french = store.query(
                "SELECT ts_utc, value, kind, run_at, horizon_min FROM record_current "
                "WHERE country = 'FR' ORDER BY ts_utc"
            )
            british = store.query(
                "SELECT source_id, kind, horizon_min, run_at FROM record_current "
                "WHERE country = 'GB'"
            )
            runs = store.query(
                "SELECT source_id, country, day, kind, status, rows, http_status, "
                "raw_ref, started_at, finished_at, run_at FROM run "
                "ORDER BY country, day, started_at"
            )
            marks = dict(store.query("SELECT key, value FROM meta"))
            refs = [row[0] for row in store.query("SELECT DISTINCT raw_ref FROM record")]

        with Store(path=config.DB_PATH, read_only=True) as store:
            collected = store.query(
                "SELECT ts_utc, horizon_min FROM record_current WHERE country = 'FR' "
                "ORDER BY ts_utc"
            )

        expected = [a_shape(item) for item in a_parse(second, "DE", COLLECTED_AGAIN)]
        check("the rebuilt rows are the rows of the collector, column for column",
              german == expected, f"{german} against {expected}")

        row = dict(zip(REBUILT_COLUMNS, german[0])) if german else {}
        check("the unit travels with the row", row.get("unit") == "gCO2eq/kWh",
              str(row.get("unit")))
        check("the basis comes from the register", row.get("basis") == COLLECTOR.basis,
              str(row.get("basis")))
        check("the scope comes from the register", row.get("scope") == COLLECTOR.scope,
              str(row.get("scope")))
        check("the granularity is native", row.get("granularity") == "native",
              str(row.get("granularity")))
        check("the kind of a measurement payload is actual",
              row.get("kind") == "actual", str(row.get("kind")))
        check("the fuel is the empty string, and not NULL", row.get("fuel") == "",
              repr(row.get("fuel")))

        check("the correction of the publisher is a second revision",
              [(value, revision) for value, revision, _ in history]
              == [(410.0, 1), (444.0, 2)], str(history))
        check("so the walk order is the collection order, oldest first",
              bool(history) and history[-1][2] == second,
              str(history[-1][2]) if history else "")
        check("a value that did not move keeps the reference of the first payload",
              kept == [(first,)], str(kept))

        check("a snapshot payload rebuilds as a forecast",
              [item[2] for item in french] == ["forecast", "forecast"], str(french))
        check("the point that lies before the collection time is dropped",
              [item[0] for item in french] == snap_stamps[1:], str(french))
        check("run_at is the collection time of the payload",
              [item[3] for item in french] == [SNAPPED, SNAPPED], str(french))
        check("and the horizon is the distance from that time",
              [item[4] for item in french] == [60, 120],
              str([item[4] for item in french]))
        check("the collected curve holds 3 points, and the rebuilt one holds 2",
              len(collected) == 3 and len(french) == 2,
              f"{len(collected)} and {len(french)}")
        # ⚠ The index needs the length first. A section that raises reports the
        # checks after it as nothing at all, and a reader then reads a shorter
        # run as a green one.
        check("a rebuilt horizon is smaller, because run_at moved 15 minutes",
              len(collected) > 1 and len(french) > 0
              and collected[1][1] == 75 and french[0][4] == 60,
              f"{collected} and {french}")

        check("the older -snap directory gives the source id of the collector",
              british == [(SOURCE, "forecast", 180, legacy_at)], str(british))

        check("no rebuilt run row carries an http status",
              runs and all(item[6] is None for item in runs),
              str([item[6] for item in runs]))
        german_runs = [item for item in runs if item[1] == "DE"]
        check("a measurement payload writes one run row for each UTC day it touches",
              [item[2] for item in german_runs]
              == [date(2026, 9, 14), date(2026, 9, 14), date(2026, 9, 15),
                  date(2026, 9, 15)], str(german_runs))
        check("and every row carries the record count of that day",
              [item[5] for item in german_runs] == [1, 1, 1, 1], str(german_runs))
        check("a run row of a rebuild claims no duration",
              all(item[8] == item[9] for item in runs), str(runs[:1]))
        forecast_runs = [item for item in runs if item[3] == "forecast"]
        check("a snapshot payload writes one run row, on the day of its run_at",
              [(item[1], item[2], item[4]) for item in forecast_runs]
              == [("FR", SNAPPED.date(), "ok"), ("GB", legacy_at.date(), "ok")],
              str(forecast_runs))

        check("the store says how many payloads it came from",
              marks.get("rebuilt_payloads") == "4 of 4",
              str(marks.get("rebuilt_payloads")))
        check("and which tree it came from",
              marks.get("rebuilt_from") == str(config.RAW_DIR),
              str(marks.get("rebuilt_from")))
        check("and it carries the note of the two limits",
              "run table holds no fail day" in (marks.get("rebuilt_note") or ""),
              str(marks.get("rebuilt_note"))[:80])
        check("and the time of the rebuild", bool(marks.get("rebuilt_at")),
              str(marks.get("rebuilt_at")))

        # Every rebuilt `raw_ref` must read back to its own hash. This is the
        # check that `atlas verify` runs, and it keeps a rebuilt store traceable.
        unread = []
        for ref in refs:
            try:
                raw.read(ref)
            except (OSError, ValueError) as error:
                unread.append(f"{ref}: {error}")
        check("every rebuilt raw_ref reads back to its own hash",
              len(refs) == 4 and not unread, f"{len(refs)} ref(s) {unread}")


SECTIONS = (
    test_guards,
    test_forecast_parse,
    test_revision,
    test_todo,
    test_windows,
    test_split,
    test_lock,
    test_registers,
    test_export,
    test_recent_window,
    test_pairs,
    test_coverage,
    test_neso,
    test_rte,
    test_energinet,
    test_elia,
    test_zero_guard,
    test_redo_ok_cli,
    test_redo_ok_days,
    test_coverage_edges,
    test_rebuild_refusals,
    test_rebuild_skips,
    test_rebuild_records,
)


def main() -> int:
    """Run every section, and then report all the failures together.

    A failed section raises, and this loop catches it, so one bad check does
    not hide the sections after it. pytest runs the same sections one at a
    time, and it reports each raise as a failed test.
    """
    print(f"store for the tests: {TEMP}")
    for test in SECTIONS:
        try:
            test()
        except SectionFailed:
            pass  # `check` printed and counted every failure of the section.
        except Exception as error:  # a broken section must not stop the run
            check(f"{test.__name__} runs to the end", False,
                  f"{type(error).__name__}: {error}")

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED:
        for line in FAILURES:
            print(f"  FAIL  {line}")
        print(f"the store of this run stays for a look: {TEMP}")
        return 1
    # A green run leaves nothing behind. A red run keeps the store, because
    # the DuckDB file is the only way to look at a failed check. The log file
    # of the package is open in this process, and Windows removes no open
    # file, so the handlers close first.
    logging.shutdown()
    shutil.rmtree(TEMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
