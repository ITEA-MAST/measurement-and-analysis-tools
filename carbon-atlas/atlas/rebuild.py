"""`atlas rebuild` — the DuckDB file again, from `store/raw/` alone.

    python -m atlas rebuild --into <dir> [--source ID] [--from DATE] [--to DATE]

This module is the answer to "can I reproduce your data". Read the four
sections below before you trust a number that came out of a rebuilt store.

`README.md`, `ARCHITECTURE.md` and `RUNNING.md` all say that the store rebuilds
from the payloads. Until this command existed, nothing tested that claim.
`raw.read()` and `raw.path_of()` were in the tree, and no caller used them.


## 1. What the command does

1. It walks `store/raw/`. One file is one payload, as the publisher served it.
2. It reads the bytes back through gzip, and it makes the sha256 again.
3. It matches the payload to the collector that made the request, and it calls
   the `parse` of that collector with a `ParseContext`.
4. It writes the records into a new DuckDB file in the `--into` directory.

It makes no network request. A payload that fails its hash is reported and
skipped. A payload that fails to parse is reported and skipped. Neither stops
the run. The command prints a summary, and it exits 0 only when it found at
least one payload and every payload parsed.

A clone of this repository rebuilds less than the machine that collected the
data. MEASURED 2026-09-23: `store/raw/` holds 364 payloads, and `git
check-ignore` puts 223 of them in the repository. The other 141 are the
Energinet Denmark series and the NESO Great Britain series, which
`LICENSE-DATA.md` holds inside Wirtek.

MEASURED 2026-09-23, on a rebuild of those 223 payloads alone: 5,415,932
records, against the 6,590,460 of the live store. It holds the 5 licensed
sources, and the checksum of each of the 4 source ids is equal to the live one.
It loses the 1,022,288 Energinet DK rows, the 152,182 NESO GB actual rows and
the 203 NESO GB forecast rows.

⚠ A clone still holds Denmark and Great Britain, and it holds 34 countries, the
same as the live store. energy-charts covers both countries, and it is
licensed. What a clone loses is the second publisher of each: 118,464 DK rows
and 184,994 GB rows stay, at the step and the basis of energy-charts. So the
Source discrepancy tab falls from 6 pairs to 4, and the DK pair of -52.7 % that
`REFERENCE.md` section 9b reports is not in a clone. That is the licence, and
not a defect of this command.


## 2. The safety property

`--into` is required, and it names a directory that must not already hold an
`atlas.duckdb`. The command refuses rather than write over one. It also refuses
a target that resolves to the live `store/atlas.duckdb`, and a target inside
`store/raw/`. A rebuild that can destroy the live store is worse than no
rebuild, so these three guards run before the command opens anything.

The command never writes to `store/atlas.duckdb`. It does write three other
things under `store/`, and an operator must know about them:

- `store/atlas.lock`, for the length of the run. The lock stops a `daily` or a
  `snap` from adding a payload while the walk reads the tree.
- `store/tmp/<name>-<pid>-<uuid>.csv`, one file for each bulk load.
  `store.Store` writes the temporary files there, and it removes each one.
- the live store, opened read only, to read the expected hashes. See section 4.


## 3. What a rebuild reproduces, and what it can not

Exact, for a measurement payload (`kind = 'actual'`):

    country, source_id, metric, fuel, ts_utc, value, unit, basis, scope,
    granularity, zones, kind

MEASURED 2026-09-23, against the live store of that day: the rebuild gives the
same value and the same 6 attributes for 6,586,289 of the 6,586,295 actual rows
of `record_current`. The store holds 6 source ids, and the checksum of the 5
that are not `neso-carbon-intensity` is equal on both sides. No rebuilt row
holds a key or a value that the live store does not hold.

⚠ The 6 rows that a rebuild does not give are the 6 NESO GB rows that hold 0.0.
`zero_guard()` in `atlas/collectors/base.py` drops a 0.0 now, and it dropped
none when those 3 payloads arrived on 2026-09-18. A rebuild runs the parser of
today on the bytes of the collection day, so a guard that is newer than a
payload changes the count. Read a difference of this shape as a change of the
program, and not as a change of the data.

⚠ `collected_at` and `raw_ref` are exact properties of one payload, and the two
stores do not name the same payload. MEASURED: 659,826 of the 6,586,289 rows,
which is 10.0 %, carry another reference. The value is equal in every one of
them. The payload windows overlap, and `Store.insert_records` writes no row for
an equal value, so the first payload that carries a value keeps the reference.
The collection order and the walk order start from a different first payload.
395,424 DE rows show the widest case: the live store names
`20260917T103609Z-DE.json.gz`, the rebuild names `20260917T102215Z-DE.json.gz`,
and the live store names that second file nowhere. So a `raw_ref` states one
payload that holds the evidence for a number, and not the only one.

Not exact, for a snapshot payload (`kind = 'forecast'`):

    run_at, horizon_min

⚠ `run_at` is lost. `runner.snap_forecasts` reads the clock one time, before
the loop over the countries, and it gives that one instant to every country of
the run. The file name carries `collected_at`, which is the clock after the
fetch of that one country. A rebuild therefore sets `run_at = collected_at`,
and the rebuilt `run_at` is later than the original. MEASURED 2026-09-23 on the
live store: `collected_at - run_at` runs from 0 to 961 seconds across the 3,492
energy-charts forecast records, and it is 0 for the 203 NESO ones. So a rebuilt
`horizon_min` can be up to 16 minutes smaller than the stored one, and a
rebuilt curve can lose its first point, because both forecast parsers drop a
point with a negative horizon.

⚠ The whole forecast series gets larger, and not smaller. MEASURED 2026-09-23:
the rebuild holds 3,852 forecast rows against the 3,695 of the live store. It
loses 21 points to a negative horizon, and it adds 178 for Lithuania alone. 3
payloads of 2026-09-17 carry one LT curve, the live store gave all 3 the one
`run_at` of that snapshot run, and the rebuild gives each payload its own. So
`record_current` keeps 1 LT curve in the live store and 3 in the rebuild. A
panel that counts `run_at` values counts payloads after a rebuild: `atlas
export` writes 61 runs for energy-charts from the rebuilt store of the licensed
payloads, against 4 from the live store.

`run_at` is part of the record key, so a rebuilt forecast row does not join to
the stored forecast row of the same curve. Compare the actual series when you
compare two stores. The forecast series needs a comparison by `ts_utc` and
`value`, and not by the key.

The `run` table is the second thing that a rebuild can not reproduce. That
table records what happened at collection time, and a rebuild made no request.
This command writes a reconstruction, and it marks it:

- one row for each UTC day that the records of a payload touch, with the status
  `ok` and the record count of that day, which is the rule of
  `runner._runs_for_window`;
- one row for each snapshot payload, on the day of its `run_at`;
- `error` carries the dropped-point note of the re-parse, which is exact;
- `http_status` is NULL. A collection row always carries the status code of the
  request. A row with a `raw_ref` and no `http_status` came from a rebuild.
- `started_at` and `finished_at` both hold `collected_at`, so the row claims no
  duration.
- the `meta` table carries `rebuilt_at`, `rebuilt_from`, `rebuilt_payloads` and
  `rebuilt_note`.

⚠ A rebuilt run table holds no `fail` day. A failed request wrote no payload,
so the walk finds nothing to rebuild it from. It holds an `empty` day only for
a snapshot payload that parsed to no point. MEASURED 2026-09-23 on the rebuild
of the 364 payloads: 0 `fail` rows and 8 `empty` rows, against the 45,787 and
the 9,434 of the live store. `health.json` comes from the run table, so it then
reads `days_fail` 0 and `days_empty` 8, against the 6,990 and the 9,432 of the
live export. That is not a claim that nothing failed. `atlas status` shows the
same shortfall: it prints no failure block, and its run-row count is far below
the live one.

Two more differences that a reader must expect:

- A measurement payload that parses to no record writes no run row, because the
  requested window is not in the file name and the rebuild does not know which
  day to mark. The payload then leaves no `raw_ref` in the rebuilt store, so
  `atlas verify` against that store checks fewer payloads than against the
  live one. MEASURED 2026-09-23 on the rebuild of the 223 licensed payloads:
  `atlas verify` reads 206 of them, and it reports `ok 206 absent 0 changed 0`.
  The 17 that it does not read are the payloads of CY, GE, MD and XK that hold
  no value for the days they cover.
- The request window is not recoverable. A payload can hold days that the
  request did not ask for, and the file name does not say which days it did.


## 4. The hash check, and what it proves

`atlas verify` compares the sha256 of the file with the sha256 that the store
recorded at collection time. Two numbers, and one of them is independent of the
file. This command does the same when the live store is present: it reads every
`raw_ref` from `record` and from `run`, read only, and it compares.

⚠ When the live store is absent, there is nothing to compare against. The
repository ships the payloads and no checksum manifest, so a reader who clones
it can only make the hash again from the bytes and put that number in the
`raw_ref`. That chain is self-consistent, and it proves nothing about tampering.
It still catches a truncated or corrupt file, because gzip carries a CRC32 of
the uncompressed bytes and the read fails. The command prints which of the two
modes it ran.

To turn a rebuild into a real proof, run these three in order:

    python -m atlas verify                       # the live store against the files
    python -m atlas rebuild --into <dir>         # the files against the parsers
    # then compare the two stores, actual series only, by the record key

To run `atlas verify` against the rebuilt store, point `ATLAS_STORE` at a
directory that holds both the new `atlas.duckdb` and a `raw/` tree. A `raw_ref`
is relative to the store directory, so a rebuilt store with no `raw/` beside it
reports every payload as ABSENT.


## 5. Two things the file names carry, and one they do not

A payload path is
`store/raw/<directory>/<yyyy-mm>/<yyyymmddThhmmssZ>-<country>[-snap][-<n>].json.gz`.

The directory is a source id. Older code gave a snapshot a directory of its own
and a plain file name, so `store/raw/energy-charts-co2eq-snap/` and
`store/raw/neso-carbon-intensity-snap/` also exist. This module reads both
forms. The records of both carry the source id of the collector, so the `-snap`
directory name never reaches the store. `RUNNING.md` section 4 states the same.

⚠ `--from` and `--to` count the collection date from the file name, and not the
date of the data inside. Every payload in the tree was collected in September
2026, and the records in them start in 2011. So `--from 2015-06-01` selects
nothing at all. Use the two flags to rebuild one collection day.

The order of the walk is the collection order, oldest first. That order is not
cosmetic. `Store.insert_records` writes `revision = the stored revision + 1`,
and `record_current` keeps the highest revision. Payload windows overlap, so a
walk in a different order gives a different revision to the same correction,
and `record_current` can then hold a different value.
"""

from __future__ import annotations

import gzip
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from . import collectors, config, lock, log
from .collectors.base import ParseContext
from .model import RunRow
from .raw import ref_of
from .store import Store, StoreBusy, to_utc_naive

SUFFIX = ".json.gz"

# The file name that `raw.write()` makes: a collection stamp, then the country.
_NAME = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)-(?P<tail>.+)$")

# The counter that `raw.write()` adds when two payloads land in one second.
_COUNTER = re.compile(r"^(?P<rest>.+)-(?P<number>\d+)$")

SNAP = "-snap"

# The sentence that travels in the `meta` table of a rebuilt store.
REBUILT_NOTE = (
    "This store came from `atlas rebuild`. The actual series is a re-parse of "
    "the payloads. The forecast `run_at` is the collection time and not the "
    "snapshot time, so `horizon_min` is smaller than the collected one. The "
    "run table holds no fail day and no empty day, so health.json reports 0 "
    "for both. See the docstring of atlas/rebuild.py."
)


@dataclass(slots=True)
class Payload:
    """One file in `store/raw/`, and what its path says about it."""

    path: Path
    relative: str
    source_id: str
    country: str
    kind: str  # actual | forecast
    collected_at: datetime


@dataclass(slots=True)
class Outcome:
    """The counts and the reasons of one run. The command prints them."""

    found: int = 0
    parsed: int = 0
    records: int = 0
    revisions: int = 0
    run_rows: int = 0
    empty: list = field(default_factory=list)
    unnamed: list = field(default_factory=list)
    ignored: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # (reason, path)


# --- The file name, read backwards --------------------------------------------


def split_name(name: str) -> tuple[datetime, str, bool] | None:
    """Read a payload file name. It gives (collected_at, country, snapshot).

    It returns `None` for a name that `raw.write()` did not make. The counter
    comes off first, because `raw.write()` adds it last.
    """
    if not name.endswith(SUFFIX):
        return None
    stem = name[: -len(SUFFIX)]
    match = _NAME.match(stem)
    if not match:
        return None
    try:
        collected_at = datetime.strptime(match["stamp"], "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None

    tail = match["tail"]
    counter = _COUNTER.match(tail)
    if counter:
        tail = counter["rest"]
    snapshot = tail.endswith(SNAP)
    if snapshot:
        tail = tail[: -len(SNAP)]
    if not tail:
        return None
    return collected_at, tail, snapshot


def source_of_directory(name: str) -> tuple[str | None, bool]:
    """The source id of a directory in `store/raw/`, and the snapshot flag.

    The current code writes the source id. Older code wrote the source id with
    `-snap` for a forecast run. Both forms are on disk.
    """
    known = set(collectors.ids())
    if name in known:
        return name, False
    if name.endswith(SNAP) and name[: -len(SNAP)] in known:
        return name[: -len(SNAP)], True
    return None, False


# --- The walk -----------------------------------------------------------------


def scan(
    raw_dir: Path,
    source: str | None = None,
    since: date | None = None,
    until: date | None = None,
) -> tuple[list[Payload], Outcome]:
    """Every payload under `raw_dir`, oldest collection first.

    Section 5 of the module docstring gives the reason for the order and for
    the two date flags.
    """
    found: list[Payload] = []
    outcome = Outcome()
    if not raw_dir.is_dir():
        return found, outcome

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(config.STORE_DIR).as_posix()
        parts = path.relative_to(raw_dir).parts
        if len(parts) < 2 or not path.name.endswith(SUFFIX):
            outcome.ignored.append(relative)
            continue

        source_id, directory_snap = source_of_directory(parts[0])
        if source_id is None:
            outcome.ignored.append(relative)
            continue

        read = split_name(path.name)
        if read is None:
            outcome.ignored.append(relative)
            continue
        collected_at, country, name_snap = read

        if source and source_id != source:
            continue
        day = collected_at.date()
        if (since and day < since) or (until and day > until):
            continue

        found.append(
            Payload(
                path=path,
                relative=relative,
                source_id=source_id,
                country=country.upper(),
                kind="forecast" if (directory_snap or name_snap) else "actual",
                collected_at=collected_at,
            )
        )

    # The collection order. The counter suffix sorts after the plain name, so
    # the path is the right tiebreaker for two payloads of one second.
    found.sort(key=lambda item: (item.collected_at, item.relative))
    outcome.found = len(found)
    return found, outcome


# --- The expected hashes ------------------------------------------------------


def stored_hashes() -> tuple[dict[str, set[str]] | None, str]:
    """The sha256 of every payload that the live store names, by path.

    It gives `(None, reason)` when the live store is absent or busy. Section 4
    of the module docstring says what the rebuild can and can not prove then.
    """
    if not config.DB_PATH.exists():
        return None, f"no store at {config.DB_PATH}"
    try:
        with Store(read_only=True) as store:
            rows = store.query(
                """
                SELECT DISTINCT raw_ref FROM record
                UNION
                SELECT DISTINCT raw_ref FROM run WHERE raw_ref IS NOT NULL
                """
            )
    except StoreBusy as error:
        return None, str(error).splitlines()[0]

    table: dict[str, set[str]] = {}
    for (ref,) in rows:
        path, _, digest = str(ref).partition("#sha256:")
        if digest:
            table.setdefault(path, set()).add(digest)
    return table, ""


# --- The run rows of a rebuild -------------------------------------------------


def run_rows(item: Payload, records: list, run_at: datetime | None, ref: str,
             note: str | None) -> list[RunRow]:
    """The reconstruction of the run table for one payload.

    `http_status` is NULL in every row. Section 3 of the module docstring gives
    the reason, and it names what these rows can not hold.
    """
    common = {
        "source_id": item.source_id,
        "country": item.country,
        "kind": item.kind,
        "http_status": None,
        "error": note,
        "raw_ref": ref,
        "started_at": item.collected_at,
        "finished_at": item.collected_at,
    }

    if item.kind == "forecast":
        day = (run_at or item.collected_at).date()
        return [
            RunRow(
                day=day,
                run_at=run_at,
                status="ok" if records else "empty",
                rows=len(records),
                **common,
            )
        ]

    per_day = Counter(to_utc_naive(record.ts_utc).date() for record in records)
    return [
        RunRow(day=day, status="ok", rows=count, **common)
        for day, count in sorted(per_day.items())
    ]


# --- The command ---------------------------------------------------------------


def _guard_target(into: str) -> Path:
    """The three refusals of section 2. It gives the directory to write into."""
    target = Path(into).expanduser().resolve()
    db_path = target / "atlas.duckdb"

    if db_path == config.DB_PATH.resolve():
        raise SystemExit(
            f"--into {target} is the live store. A rebuild never writes "
            f"{config.DB_PATH}. Name an empty directory."
        )
    raw_dir = config.RAW_DIR.resolve()
    if raw_dir == target or raw_dir in target.parents:
        raise SystemExit(
            f"--into {target} is inside {raw_dir}. That tree holds the licensed "
            f"payloads. Name a directory outside it."
        )
    if db_path.exists():
        raise SystemExit(
            f"{db_path} is already there. The command does not write over a "
            f"store. Remove it, or name another directory."
        )
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SystemExit(f"--into {target} is not usable: {error}") from None
    return target


def _note_of(context: ParseContext) -> str | None:
    """The run-row text of the points that a guard refused.

    It holds the rule of `runner._dropped_note`. The two must stay the same, so
    a rebuilt run row reads like the row that the collection wrote.
    """
    if not context.dropped:
        return None
    text = f"{len(context.dropped)} point(s) dropped. First: {context.dropped[0]}"
    return text[:500]


def _one_payload(store, item: Payload, hashes, outcome: Outcome, logger) -> bool:
    """Read, check, parse and insert one payload. True when it parsed."""
    try:
        with gzip.open(item.path, "rb") as handle:
            body = handle.read()
    except (OSError, EOFError) as error:
        outcome.skipped.append((f"the file does not read: {error}", item.relative))
        logger.error("%s: the file does not read: %s", item.relative, error)
        return False

    digest = hashlib.sha256(body).hexdigest()
    if hashes is not None:
        expected = hashes.get(item.relative)
        if expected is None:
            outcome.unnamed.append(item.relative)
        elif digest not in expected:
            outcome.skipped.append(
                ("the sha256 does not match the store", item.relative)
            )
            logger.error(
                "%s: the sha256 is %s, and the store holds %s",
                item.relative, digest, ", ".join(sorted(expected)),
            )
            return False

    ref = ref_of(item.path, digest)
    run_at = item.collected_at if item.kind == "forecast" else None
    context = ParseContext(
        kind=item.kind,
        collected_at=item.collected_at,
        raw_ref=ref,
        run_at=run_at,
    )

    try:
        collector = collectors.get(item.source_id)
        config.country(item.country)  # The register is the definition of a country.
        records = collector.parse(body, item.country, context)
    except Exception as error:  # noqa: BLE001 - one payload must not stop the walk
        outcome.skipped.append((f"{type(error).__name__}: {error}", item.relative))
        logger.error("%s: %s", item.relative, error)
        return False

    try:
        new, revisions = store.insert_records(records)
        rows = run_rows(item, records, run_at, ref, _note_of(context))
        store.write_runs(rows)
    except Exception as error:  # noqa: BLE001 - the same rule as the parse above
        outcome.skipped.append((f"the write failed: {error}", item.relative))
        logger.exception("%s: the write failed", item.relative)
        return False

    outcome.parsed += 1
    outcome.records += new + revisions
    outcome.revisions += revisions
    outcome.run_rows += len(rows)
    if not records:
        outcome.empty.append(item.relative)
    logger.info(
        "%s %s %s: %d record(s), %d new, %d revision(s)",
        item.source_id, item.country, item.kind, len(records), new, revisions,
    )
    return True


def _stamp(store, outcome: Outcome) -> None:
    """Write the rebuild marker into the `meta` table of the new store."""
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    marks = {
        "rebuilt_at": now.isoformat(sep=" "),
        "rebuilt_from": str(config.RAW_DIR),
        "rebuilt_payloads": f"{outcome.parsed} of {outcome.found}",
        "rebuilt_note": REBUILT_NOTE,
    }
    for key, value in marks.items():
        store.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [key, value],
        )


def run(into: str, source: str | None = None, since: date | None = None,
        until: date | None = None) -> int:
    """Rebuild a store from `store/raw/`. It gives the exit code.

    0 when the walk found payloads and every one of them parsed. 1 when it
    skipped one or more, and 1 when it found none. A walk that finds nothing
    is a wrong `--source`, `--from` or `--to`, and a script must see that as a
    failure. An empty store is not a rebuild.
    """
    logger = log.get("atlas.rebuild")
    target = _guard_target(into)
    db_path = target / "atlas.duckdb"

    # Every printed line is ASCII. The console of a Windows task runs cp1252,
    # and a print of a character outside it stops the command. The docstrings
    # keep the warning sign, because nothing prints them.
    hashes, reason = stored_hashes()
    if hashes is None:
        print(
            f"hash check   the file against itself only, because {reason}.\n"
            f"             A clone of this repository ships no checksum "
            f"manifest, so this check proves no more than that the file "
            f"reads. See atlas/rebuild.py section 4."
        )
    else:
        print(f"hash check   against the {len(hashes):,} payload(s) the live store names")

    # The lock stops a `daily` or a `snap` from adding a payload while the walk
    # runs. It also makes the read of the live store above safe from a writer.
    with lock.hold("atlas rebuild"):
        found, outcome = scan(config.RAW_DIR, source=source, since=since, until=until)
        print(f"payloads     {outcome.found:,} under {config.RAW_DIR}")
        if not found:
            print("nothing to rebuild. Check --source, --from and --to.")
            print(
                "WARNING: --from and --to count the collection date, and not "
                "the date of the data. Every payload in the tree arrived in "
                "September 2026."
            )
            return 1

        logger.info("rebuild into %s: %d payload(s)", db_path, outcome.found)
        with Store(path=db_path) as store:
            for item in found:
                _one_payload(store, item, hashes, outcome, logger)
            _stamp(store, outcome)
            total = store.counts()

    _report(db_path, outcome, total)
    logger.info(
        "rebuild done: %d of %d payload(s), %d record(s)",
        outcome.parsed, outcome.found, total["record_rows"],
    )
    return 1 if outcome.skipped else 0


def _report(db_path: Path, outcome: Outcome, total: dict) -> None:
    """The summary. Every count that the run made, and every reason it holds."""
    print()
    print(f"store        {db_path}")
    print(f"parsed       {outcome.parsed:,} of {outcome.found:,}")
    print(f"records      {total['record_rows']:,}  ({outcome.revisions:,} revision(s))")
    print(f"run rows     {total['run_rows']:,}")
    print(f"skipped      {len(outcome.skipped):,}")

    for reason, relative in outcome.skipped:
        print(f"  SKIPPED  {relative}: {reason}")
    for relative in outcome.empty:
        print(f"  NO RECORD  {relative}: the payload parsed and held no value")
    for relative in outcome.unnamed:
        print(f"  NOT IN THE LIVE STORE  {relative}: no raw_ref names this payload")
    for relative in outcome.ignored:
        print(f"  IGNORED  {relative}: this is not a payload name")

    print()
    print(
        "WARNING: this store is a rebuild, and two parts of it are not the "
        "collected ones.\n"
        "  1. The run table holds no fail day and no empty day, because a "
        "failed request wrote no\n"
        "     payload. health.json therefore reports 0 for both, and that is "
        "not a claim that\n"
        "     nothing failed.\n"
        "  2. A forecast run_at is the collection time and not the snapshot "
        "time, so horizon_min\n"
        "     is smaller than the collected one, and a curve can hold fewer "
        "points.\n"
        "  atlas/rebuild.py section 3 states both limits in full."
    )
