"""The command line.

    python -m atlas backfill [--source X] [--country DE ...] [--from D] [--to D]
                             [--redo-ok]
    python -m atlas daily    [--source X] [--country DE ...] [--from D] [--no-export]
    python -m atlas snap     [--source X] [--country DE ...]
    python -m atlas export
    python -m atlas measure  [--country DE ...]
    python -m atlas status
    python -m atlas verify
    python -m atlas rebuild  --into DIR [--source X] [--from D] [--to D]
    python -m atlas serve    [--port 8765] [--no-browser]

`serve` gives the portal from a local address. A browser refuses to read a
file beside an HTML page that it opened from the disk, so the portal needs an
address. The server reads `portal/` only, and it makes no network request.

`backfill` and `daily` run the same code. `backfill` asks for every day from
the first day of the source. `daily` asks for the days with no `ok` row, and
it always reads the last 2 days again to catch a correction.

Neither of them reads a day that already carries an `ok` row and is older than
2 days. A run that stopped in the middle of a day wrote that `ok` row, so the
part day stays a part day. `backfill --redo-ok` reads those days again, over
the window that `--from` and `--to` name. It refuses to run without `--from`.

`measure` prints what two publishers of one country say about the same hour.
`atlas export` writes the same table to `portal/data/pairs.json`, so the
headline claim of the project comes from a query that anybody can run again.
It opens the store read only. `atlas/analyse.py` holds the query.

`verify` reads every raw payload again and compares it with the sha256 in the
store. It makes no network request, and it opens the store read only.

`rebuild` makes a new DuckDB file from `store/raw/` alone, in the directory
that `--into` names. It makes no network request, and it never writes
`store/atlas.duckdb`. ⚠ It reproduces the actual series and not the forecast
`run_at`, and its run table holds no failed day. `atlas/rebuild.py` states
every limit.

Every command that writes takes the store lock. RUNNING.md section 5.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from . import analyse, collectors, config, export, lock, log, raw, rebuild, runner
from .store import Store, StoreBusy


def _date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def _sources(args) -> list:
    if args.source:
        return [collectors.get(args.source)]
    return [collectors.get(name) for name in collectors.ids()]


def _countries(collector, args) -> list[str]:
    """The countries to collect from this source. The list can be empty.

    With `--source`, an ISO code that the source does not serve is a mistake of
    the operator, and the command stops. Without `--source` the command runs
    every source, and no source serves every country, so a code that this
    source does not serve only drops this source. `_run_sources` stops the
    command when no source is left.
    """
    known = collector.countries()
    if not args.country:
        return known
    wanted = [item.upper() for item in args.country]
    if not args.source:
        return [item for item in wanted if item in known]
    unknown = [item for item in wanted if item not in known]
    if unknown:
        raise SystemExit(
            f"{collector.source_id} does not serve {', '.join(unknown)}. "
            f"It serves: {', '.join(known)}."
        )
    return wanted


def _run_sources(args, logger, work) -> tuple[int, int]:
    """Call `work(collector, isos)` for each source that the arguments name.

    It returns (the sources that ran, the sources that stopped with an error).

    One source that stops with an error must not take the other sources with
    it, and must not skip the export at the end of `atlas daily`. A source that
    serves none of the countries the operator named is skipped, not an error,
    because the default is every source.
    """
    used = 0
    broken = 0
    for collector in _sources(args):
        isos = _countries(collector, args)
        if not isos:
            logger.info(
                "%s serves none of %s. It is skipped.",
                collector.source_id,
                ", ".join(item.upper() for item in args.country or ["the countries"]),
            )
            continue
        used += 1
        try:
            work(collector, isos)
        except Exception:  # noqa: BLE001 - one bad publisher must not stop the run
            broken += 1
            logger.exception(
                "%s stopped with an error. The command goes on with the next source.",
                collector.source_id,
            )
    if args.country and not used:
        raise SystemExit(
            "no source serves "
            f"{', '.join(item.upper() for item in args.country)}. "
            "sources/zones.json holds the countries, and sources/sources.json "
            "holds the sources."
        )
    return used, broken


# --- The commands ------------------------------------------------------------


def cmd_backfill(args) -> int:
    """Fill the days that the store does not hold.

    `--redo-ok` also reads the days whose newest run row says `ok`. That is the
    one repair for a part day: a run that stopped in the middle of a day wrote
    an `ok` row for it, and no other command asks for that day again.

    The flag needs `--from`. Without a window it would read every day of every
    source again, which is about 2 hours 47 minutes over the network and a
    reason for a publisher to refuse the next request. RUNNING.md section 2.
    """
    logger = log.get("atlas")
    today = date.today()
    end = args.to or today
    total = {"windows": 0, "new": 0, "revisions": 0, "fail": 0, "empty": 0}

    # This runs before the lock, so a mistake of the operator costs no wait.
    if args.redo_ok and args.since is None:
        raise SystemExit(
            "--redo-ok needs --from. Without it the command reads every day of "
            "every source again, which is about 2 hours 47 minutes over the "
            "network. Name the window, for example:\n"
            "  python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18"
        )

    with lock.hold("atlas backfill"), Store() as store:
        from .net import Http

        def work(collector, isos):
            start = args.since or collector.available_from
            # `store.days_to_collect` gives back a day with an `ok` row only
            # while `day > today - force_recent_days`. The span from `start` to
            # today, plus 1 day, therefore covers every day of the window.
            redo_days = (today - start).days + 1 if args.redo_ok else 0
            logger.info(
                "backfill %s: %d country(s), %s to %s%s",
                collector.source_id, len(isos), start, end,
                ". It reads the ok days again." if args.redo_ok else "",
            )
            outcome = runner.collect_measurements(
                store, http, collector, isos, start, end,
                force_recent_days=redo_days,
            )
            for key in total:
                total[key] += outcome.get(key, 0)

        with Http() as http:
            _used, broken = _run_sources(args, logger, work)

    logger.info("backfill done: %s", total)
    if broken:
        logger.error("%d source(s) stopped with an error. See the log.", broken)
    return 1 if total["fail"] or broken else 0


def cmd_daily(args) -> int:
    logger = log.get("atlas")
    end = date.today()
    total = {"windows": 0, "new": 0, "revisions": 0, "fail": 0, "empty": 0}

    with lock.hold("atlas daily"), Store() as store:
        from .net import Http

        def work(collector, isos):
            start = args.since or collector.available_from
            outcome = runner.collect_measurements(
                store, http, collector, isos, start, end,
                force_recent_days=config.RECENT_DAYS,
                retry_fail_days=config.DAILY_RETRY_FAIL_DAYS,
            )
            for key in total:
                total[key] += outcome.get(key, 0)

        with Http() as http:
            _used, broken = _run_sources(args, logger, work)

        if not args.no_export:
            export.run(store)

    logger.info("daily done: %s", total)
    if broken:
        logger.error("%d source(s) stopped with an error. See the log.", broken)
    return 1 if total["fail"] or broken else 0


def cmd_snap(args) -> int:
    logger = log.get("atlas")
    total = {"countries": 0, "new": 0, "fail": 0, "empty": 0}

    with lock.hold("atlas snap"), Store() as store:
        from .net import Http

        def work(collector, isos):
            outcome = runner.snap_forecasts(store, http, collector, isos)
            for key in total:
                total[key] += outcome.get(key, 0)

        with Http() as http:
            _used, broken = _run_sources(args, logger, work)

    logger.info("snap done: %s", total)
    if broken:
        logger.error("%d source(s) stopped with an error. See the log.", broken)
    return 1 if total["fail"] or broken else 0


def cmd_export(_args) -> int:
    """Write `portal/data/*.json` again from the store.

    The guard is the same as in `cmd_status` and `cmd_verify`, and it has one
    more test. An export from a store with no record row writes 10 empty files
    over `portal/data/`, and the files of the last good export are then gone.
    So an empty store stops the command before it writes anything.
    """
    if not config.DB_PATH.exists():
        print(f"no store at {config.DB_PATH}. Run a backfill first.")
        return 1

    with lock.hold("atlas export"), Store() as store:
        if not store.counts()["record_rows"]:
            print(f"no record in the store at {config.DB_PATH}. Run a backfill first.")
            return 1
        export.run(store)
    return 0


def cmd_measure(args) -> int:
    """Print what two publishers of one country say about the same hour.

    This is the query behind the headline claim of the project, and it is the
    answer to "show me the query that produced that number". `atlas export`
    writes the same table to `portal/data/pairs.json`.

    The command opens the store read only. It writes nothing and it takes no
    lock of its own. DuckDB gives the file to one process, so the command
    fails while a writer runs. `RUNNING.md` section 5 gives the rule.
    """
    if not config.DB_PATH.exists():
        print(f"no store at {config.DB_PATH}. Run a backfill first.")
        return 1

    with Store(read_only=True) as store:
        table = analyse.pairs(store)

    wanted = [item.upper() for item in args.country or []]
    if wanted:
        table = dict(table)
        table["pairs"] = [row for row in table["pairs"] if row["country"] in wanted]
        table["skipped"] = [row for row in table["skipped"] if row["country"] in wanted]

    for line in analyse.lines(table):
        print(line)

    if not table["pairs"]:
        # A country with one source only is not a failure of the command. The
        # store holds one source for 30 of the 34 countries on 2026-09-23.
        print("\nno pair to measure. A pair needs two sources of one country.")
    return 0


def cmd_serve(args) -> int:
    """Give `portal/` from a local address, then open a browser."""
    import functools
    import http.server
    import socketserver
    import webbrowser

    logger = log.get("atlas")
    root = config.ROOT / "portal"
    if not (root / "index.html").exists():
        raise SystemExit(f"no portal at {root}")
    if not (config.PORTAL_DATA_DIR / "meta.json").exists():
        logger.warning("no portal data yet. Run 'python -m atlas export' first.")

    # The page asks for 10 data files at one time. A server that answers one
    # request at a time fills the listen queue, and the browser then gets
    # "connection refused" for a file. So the server is threaded, and the
    # queue is larger than the default of 5.
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
        request_queue_size = 32

    class Handler(http.server.SimpleHTTPRequestHandler):
        """A local server must never give a page from the browser cache.
        An export writes new data files under the same names."""

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    handler = functools.partial(Handler, directory=str(root))
    try:
        server_context = Server(("127.0.0.1", args.port), handler)
    except OSError as error:
        raise SystemExit(
            f"the portal cannot take port {args.port}: {error}\n"
            f"Another program holds it. Add --port <n> with a free number."
        ) from None
    with server_context as server:
        url = f"http://127.0.0.1:{args.port}/index.html"
        logger.info("portal at %s. Press Ctrl+C to stop.", url)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("portal stopped")
    return 0


def cmd_status(_args) -> int:
    if not config.DB_PATH.exists():
        print(f"no store at {config.DB_PATH}. Run a backfill first.")
        return 1

    with Store(read_only=True) as store:
        counts = store.counts()
        duplicates = store.duplicate_keys()
        print(f"store        {config.DB_PATH}")
        print(f"record rows  {counts['record_rows']:,}")
        print(f"run rows     {counts['run_rows']:,}")
        print(f"duplicates   {duplicates:,}")
        if duplicates:
            print(
                "  ERROR: the record table holds a key two times at one revision. "
                "Every count above is too large. REFERENCE.md section 4."
            )
        print()
        print(f"{'source':28} {'iso':4} {'kind':9} {'rows':>10}  {'from':10} {'to':10}")
        rows = store.query(
            """
            SELECT source_id, country, kind, count(*) AS n,
                   min(ts_utc) AS lo, max(ts_utc) AS hi
            FROM record_current
            GROUP BY source_id, country, kind
            ORDER BY source_id, country, kind
            """
        )
        for source_id, iso, kind, count, lo, hi in rows:
            print(
                f"{source_id:28} {iso:4} {kind:9} {count:>10,}  "
                f"{str(lo)[:10]} {str(hi)[:10]}"
            )

        bad = store.query(
            """
            WITH last AS (
              SELECT source_id, country, day, kind, status, error
              FROM run
              QUALIFY row_number() OVER (
                PARTITION BY source_id, country, day, kind ORDER BY finished_at DESC
              ) = 1
            )
            SELECT source_id, country, kind, count(*) AS days, any_value(error)
            FROM last WHERE status = 'fail'
            GROUP BY source_id, country, kind
            """
        )
        if bad:
            print()
            print("failures:")
            for source_id, iso, kind, days, error in bad:
                print(f"  {source_id} {iso} {kind}: {days} day(s). {str(error)[:120]}")
    return 0


def cmd_verify(_args) -> int:
    """Read every raw payload again, and compare it with the hash in the store.

    This is the traceability test. A record carries the relative path of the
    payload and its sha256. `raw.read` reads the file and makes the hash again.
    The command makes no network request, and it writes nothing.
    """
    if not config.DB_PATH.exists():
        print(f"no store at {config.DB_PATH}. Run a backfill first.")
        return 1

    with Store(read_only=True) as store:
        refs = [
            row[0]
            for row in store.query(
                """
                SELECT DISTINCT raw_ref FROM record
                UNION
                SELECT DISTINCT raw_ref FROM run WHERE raw_ref IS NOT NULL
                """
            )
        ]

    print(f"{len(refs):,} raw payload(s) from {config.RAW_DIR}")
    absent = 0
    changed = 0
    for ref in refs:
        try:
            raw.read(ref)
        except FileNotFoundError:
            absent += 1
            print(f"  ABSENT   {raw.path_of(ref)}")
        except ValueError as error:
            changed += 1
            print(f"  CHANGED  {error}")
        except OSError as error:
            changed += 1
            print(f"  UNREAD   {raw.path_of(ref)}: {error}")
    print(f"ok {len(refs) - absent - changed:,}   absent {absent:,}   changed {changed:,}")
    return 1 if absent or changed else 0


def cmd_rebuild(args) -> int:
    """Make a new DuckDB file from `store/raw/`, with no network request.

    This is the test of the reproducibility claim. `atlas verify` proves that
    the payloads did not change. This command proves that the payloads still
    give the numbers.

    It never writes `store/atlas.duckdb`. `--into` names a directory that must
    not already hold a store, and the command refuses rather than write over
    one. `atlas/rebuild.py` holds the full contract, and it names what a
    rebuild can not reproduce.
    """
    return rebuild.run(
        into=args.into, source=args.source, since=args.since, until=args.to
    )


# --- The parser --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas", description="carbon-atlas collection")
    subs = parser.add_subparsers(dest="command", required=True)

    def add_common(target):
        # `choices` answers a typo during `parse_args`, so no lock is taken and
        # no store file is opened. `collectors.get` would raise `KeyError`
        # inside the lock, and the traceback would hide the list of ids.
        target.add_argument(
            "--source", choices=collectors.ids(), metavar="ID",
            help="one source id. The default is every source.",
        )
        target.add_argument(
            "--country", action="append",
            help="one ISO code. Repeat it for more. Without --source, a source "
                 "that does not serve the code is skipped.",
        )

    backfill = subs.add_parser("backfill", help="fill the years the source serves")
    add_common(backfill)
    backfill.add_argument("--from", dest="since", type=_date, help="the first day")
    backfill.add_argument("--to", dest="to", type=_date, help="the last day")
    backfill.add_argument(
        "--redo-ok", dest="redo_ok", action="store_true",
        help="read the days whose newest run row says ok again. This repairs a "
             "day that a stopped run left part full. It needs --from, because "
             "a re-read of the whole history is about 2 hours 47 minutes.",
    )
    backfill.set_defaults(func=cmd_backfill)

    daily = subs.add_parser("daily", help="collect the new days, then export")
    add_common(daily)
    daily.add_argument("--from", dest="since", type=_date, help="the first day")
    daily.add_argument("--no-export", action="store_true", help="skip the portal export")
    daily.set_defaults(func=cmd_daily)

    snap = subs.add_parser("snap", help="capture the forward forecast curve")
    add_common(snap)
    snap.set_defaults(func=cmd_snap)

    export_cmd = subs.add_parser("export", help="write portal/data/*.json again")
    export_cmd.set_defaults(func=cmd_export)

    measure = subs.add_parser(
        "measure", help="what two publishers of one country say about the same hour"
    )
    measure.add_argument(
        "--country", action="append",
        help="one ISO code. Repeat it for more. The default is every country "
             "that has two sources.",
    )
    measure.set_defaults(func=cmd_measure)

    status = subs.add_parser("status", help="what the store holds")
    status.set_defaults(func=cmd_status)

    verify = subs.add_parser(
        "verify", help="check every raw payload against the hash in the store"
    )
    verify.set_defaults(func=cmd_verify)

    rebuild_cmd = subs.add_parser(
        "rebuild", help="make a new store from store/raw/, with no network request"
    )
    rebuild_cmd.add_argument(
        "--into", required=True, metavar="DIR",
        help="the directory for the new atlas.duckdb. It must not already hold "
             "one. The command never writes the live store.",
    )
    rebuild_cmd.add_argument(
        "--source", choices=collectors.ids(), metavar="ID",
        help="one source id. The default is every source. It covers the older "
             "<id>-snap directory of that source too.",
    )
    rebuild_cmd.add_argument(
        "--from", dest="since", type=_date, metavar="DATE",
        help="the first COLLECTION day. Warning: this is the day the payload "
             "arrived, and not the day of the data inside it.",
    )
    rebuild_cmd.add_argument(
        "--to", dest="to", type=_date, metavar="DATE",
        help="the last COLLECTION day. See --from.",
    )
    rebuild_cmd.set_defaults(func=cmd_rebuild)

    serve = subs.add_parser("serve", help="give the portal at a local address")
    serve.add_argument("--port", type=int, default=8765, help="the port. The default is 8765.")
    serve.add_argument("--no-browser", action="store_true", help="do not open a browser")
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger = log.get("atlas")
    try:
        return args.func(args)
    except (lock.LockBusy, StoreBusy) as error:
        logger.error("%s", error)
        return 2
    except KeyboardInterrupt:
        logger.warning("stopped by the operator")
        return 130


if __name__ == "__main__":
    sys.exit(main())
