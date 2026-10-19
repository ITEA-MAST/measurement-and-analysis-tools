"""The store.

One DuckDB file. Three tables and one view:

    meta            the schema version, one row. Nothing reads it yet.
    record          one row for each value, append only
    run             the to-do list and the failure log, append only
    record_current  a view: the newest revision of each key

The store never runs an `UPDATE` on a value. A second read of the same key with
an equal value writes nothing. A different value writes `revision` + 1.
REFERENCE.md sections 4 and 5.

Every timestamp in the store is UTC, and it carries no zone. A value with a
zone goes through `to_utc_naive` first.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from . import config, log
from .model import RECORD_COLUMNS, RUN_COLUMNS, Record, RunRow

# `_migrate` writes this number into the `meta` table. No code reads it back,
# and the DDL below cannot change a table that is already there. So the number
# is a stamp for a first migration step, and not a check. The first migration
# must read it before it runs a step.
SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
  key            VARCHAR PRIMARY KEY,
  value          VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS record (
  country        VARCHAR   NOT NULL,
  source_id      VARCHAR   NOT NULL,
  metric         VARCHAR   NOT NULL,
  fuel           VARCHAR   NOT NULL DEFAULT '',
  ts_utc         TIMESTAMP NOT NULL,
  value          DOUBLE,
  unit           VARCHAR   NOT NULL,
  basis          VARCHAR,
  scope          VARCHAR,
  granularity    VARCHAR   NOT NULL,
  zones          VARCHAR,
  kind           VARCHAR   NOT NULL,
  run_at         TIMESTAMP,
  horizon_min    INTEGER,
  collected_at   TIMESTAMP NOT NULL,
  revision       INTEGER   NOT NULL,
  raw_ref        VARCHAR   NOT NULL
);

CREATE INDEX IF NOT EXISTS record_lookup
  ON record (source_id, country, metric, kind, ts_utc);

CREATE TABLE IF NOT EXISTS run (
  source_id      VARCHAR   NOT NULL,
  country        VARCHAR   NOT NULL,
  day            DATE      NOT NULL,
  kind           VARCHAR   NOT NULL,
  run_at         TIMESTAMP,
  status         VARCHAR   NOT NULL,
  rows           INTEGER   NOT NULL DEFAULT 0,
  http_status    INTEGER,
  error          VARCHAR,
  raw_ref        VARCHAR,
  started_at     TIMESTAMP NOT NULL,
  finished_at    TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS run_lookup
  ON run (source_id, country, kind, day);

-- One row for each key, and never two. `row_number` and not
-- `revision = max(revision)`: the table carries no unique key, so two rows can
-- hold one key at one revision. `max` keeps both of them, and the count of
-- every panel then grows. `row_number` keeps the newest one.
CREATE OR REPLACE VIEW record_current AS
SELECT *
FROM record
QUALIFY row_number() OVER (
  PARTITION BY country, source_id, metric, fuel, ts_utc, kind, run_at
  ORDER BY revision DESC, collected_at DESC
) = 1;
"""

_BATCH_DDL = """
CREATE OR REPLACE TEMP TABLE batch (
  country        VARCHAR,
  source_id      VARCHAR,
  metric         VARCHAR,
  fuel           VARCHAR,
  ts_utc         TIMESTAMP,
  value          DOUBLE,
  unit           VARCHAR,
  basis          VARCHAR,
  scope          VARCHAR,
  granularity    VARCHAR,
  zones          VARCHAR,
  kind           VARCHAR,
  run_at         TIMESTAMP,
  horizon_min    INTEGER,
  collected_at   TIMESTAMP,
  raw_ref        VARCHAR
);
"""


def _csv_field(value) -> str:
    """One CSV field for the bulk load.

    A string always gets quotes, and a `None` gets no quotes and no text. The
    `COPY` below reads an empty field as NULL, and a quoted empty field as an
    empty string. So `fuel = ''` and `basis = NULL` stay different.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return '"' + value.replace('"', '""') + '"'
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _copy_rows(conn, table: str, rows: list[tuple]) -> None:
    """Load a batch with one `COPY` from a temporary CSV file.

    `executemany` binds one row at a time. A probe on 2026-09-17 measured more
    than 600 seconds for 375,000 rows. The same rows go in with `COPY` in
    0.9 seconds, because DuckDB reads the file in its own columnar loader.
    """
    if not rows:
        return
    config.ensure_dirs()
    path = config.TMP_DIR / f"{table}-{os.getpid()}-{uuid.uuid4().hex}.csv"
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            for row in rows:
                handle.write(",".join(_csv_field(item) for item in row))
                handle.write("\n")
        target = str(path).replace("\\", "/").replace("'", "''")
        conn.execute(
            f"COPY {table} FROM '{target}' "
            "(FORMAT CSV, HEADER FALSE, NULLSTR '', ALLOW_QUOTED_NULLS FALSE)"
        )
    finally:
        path.unlink(missing_ok=True)


def to_utc_naive(value: datetime | None) -> datetime | None:
    """A UTC timestamp with no zone. The store holds nothing else."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class StoreBusy(RuntimeError):
    """Another process has the store file open. DuckDB gives it to one process.

    This happens to a reader too, and not only to a second writer. A long
    backfill holds the file, so `atlas status` must wait for it.
    """


class Store:
    """An open DuckDB connection. Use it as a context manager."""

    def __init__(self, path: Path | None = None, read_only: bool = False) -> None:
        config.ensure_dirs()
        self.path = Path(path or config.DB_PATH)
        self.read_only = read_only
        try:
            self.conn = duckdb.connect(str(self.path), read_only=read_only)
        except duckdb.IOException as error:
            raise StoreBusy(
                f"{self.path} is open in another process. DuckDB gives the file to one "
                f"process. Wait for the run to end, then try again.\n  {error}"
            ) from None
        self._log = log.get("atlas.store")
        if not read_only:
            self._migrate()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        self.conn.execute(_DDL)
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [str(SCHEMA_VERSION)],
        )

    # --- The record table ----------------------------------------------------

    def insert_records(self, records: list[Record]) -> tuple[int, int]:
        """Insert a batch. It returns (new rows, revision rows).

        A batch holds one source and one country, because the runner makes one
        request for one country. The scope of the duplicate check follows that.
        """
        if not records:
            return (0, 0)

        first = records[0]
        rows = []
        lowest = highest = to_utc_naive(first.ts_utc)
        for item in records:
            stamp = to_utc_naive(item.ts_utc)
            lowest = min(lowest, stamp)
            highest = max(highest, stamp)
            row = list(item.as_row())
            column = RECORD_COLUMNS
            row[column.index("ts_utc")] = stamp
            row[column.index("run_at")] = to_utc_naive(item.run_at)
            row[column.index("collected_at")] = to_utc_naive(item.collected_at)
            rows.append(tuple(row))

        self.conn.execute(_BATCH_DDL)
        _copy_rows(self.conn, "batch", rows)

        before = self.conn.execute("SELECT count(*) FROM record").fetchone()[0]

        # `fresh` and `scope` both keep one row for each key. The table has no
        # unique key, so a duplicate key on either side of the join makes a
        # cross product: 2 batch rows against 2 stored rows write 4 rows, then
        # 8 on the next correction. `row_number` stops that at both ends.
        self.conn.execute(
            """
            WITH fresh AS (
              SELECT *
              FROM batch
              QUALIFY row_number() OVER (
                PARTITION BY country, source_id, metric, fuel, ts_utc, kind, run_at
                ORDER BY collected_at DESC
              ) = 1
            ),
            scope AS (
              SELECT *
              FROM record
              WHERE source_id = ? AND country = ?
                AND ts_utc BETWEEN ? AND ?
              QUALIFY row_number() OVER (
                PARTITION BY country, source_id, metric, fuel, ts_utc, kind, run_at
                ORDER BY revision DESC, collected_at DESC
              ) = 1
            )
            INSERT INTO record
            SELECT b.country, b.source_id, b.metric, b.fuel, b.ts_utc, b.value,
                   b.unit, b.basis, b.scope, b.granularity, b.zones, b.kind,
                   b.run_at, b.horizon_min, b.collected_at,
                   COALESCE(c.revision, 0) + 1 AS revision,
                   b.raw_ref
            FROM fresh b
            LEFT JOIN scope c
              ON  b.country   = c.country
              AND b.source_id = c.source_id
              AND b.metric    = c.metric
              AND b.fuel      = c.fuel
              AND b.ts_utc    = c.ts_utc
              AND b.kind      = c.kind
              AND b.run_at IS NOT DISTINCT FROM c.run_at
            WHERE c.country IS NULL
               OR (c.value IS NULL) <> (b.value IS NULL)
               OR abs(COALESCE(c.value, 0) - COALESCE(b.value, 0)) > ?
            """,
            [first.source_id, first.country, lowest, highest, config.VALUE_EPSILON],
        )

        after = self.conn.execute("SELECT count(*) FROM record").fetchone()[0]
        written = after - before
        revisions = self.conn.execute(
            "SELECT count(*) FROM record WHERE source_id = ? AND country = ? "
            "AND ts_utc BETWEEN ? AND ? AND revision > 1 AND collected_at = ?",
            [first.source_id, first.country, lowest, highest, to_utc_naive(first.collected_at)],
        ).fetchone()[0]
        return (written - revisions, revisions)

    # --- The run table -------------------------------------------------------

    def write_runs(self, runs: list[RunRow]) -> None:
        if not runs:
            return
        rows = []
        for item in runs:
            row = list(item.as_row())
            column = RUN_COLUMNS
            row[column.index("run_at")] = to_utc_naive(item.run_at)
            row[column.index("started_at")] = to_utc_naive(item.started_at)
            row[column.index("finished_at")] = to_utc_naive(item.finished_at)
            rows.append(tuple(row))
        _copy_rows(self.conn, "run", rows)

    def days_to_collect(
        self,
        source_id: str,
        country: str,
        kind: str,
        start: date,
        end: date,
        force_recent_days: int = 0,
        retry_fail_days: int = 1_000_000,
        today: date | None = None,
    ) -> list[date]:
        """The days with no `ok` row, plus the days the caller always re-reads.

        An `empty` day comes back only while it is younger than
        `EMPTY_RETRY_DAYS`, because a publisher can still fill it.

        A `fail` day comes back while it is younger than `retry_fail_days`.
        `atlas backfill` sets no limit, so it tries every failed day again.
        `atlas daily` sets 30 days. A source that answers with a server error
        for a period of 2017 must not take requests from the daily run.
        """
        now = today or date.today()
        result = self.conn.execute(
            """
            WITH days AS (
              SELECT CAST(range AS DATE) AS day
              FROM range(CAST(? AS TIMESTAMP), CAST(? AS TIMESTAMP), INTERVAL 1 DAY)
            ),
            last AS (
              SELECT day, status
              FROM run
              WHERE source_id = ? AND country = ? AND kind = ?
              QUALIFY row_number() OVER (PARTITION BY day ORDER BY finished_at DESC) = 1
            )
            SELECT d.day
            FROM days d
            LEFT JOIN last l ON d.day = l.day
            WHERE l.status IS NULL
               OR (l.status = 'fail'  AND d.day > CAST(? AS DATE) - ?)
               OR (l.status = 'empty' AND d.day > CAST(? AS DATE) - ?)
               OR d.day > CAST(? AS DATE) - ?
            ORDER BY d.day
            """,
            [
                start,
                end,  # `range` stops before `end`, so the caller passes end + 1 day
                source_id,
                country,
                kind,
                now,
                max(0, retry_fail_days),
                now,
                config.EMPTY_RETRY_DAYS,
                now,
                max(0, force_recent_days),
            ],
        ).fetchall()
        return [row[0] for row in result]

    # --- Reads for the export and the status command -------------------------

    def query(self, sql: str, params: list | None = None) -> list[tuple]:
        return self.conn.execute(sql, params or []).fetchall()

    def counts(self) -> dict:
        records = self.conn.execute("SELECT count(*) FROM record").fetchone()[0]
        runs = self.conn.execute("SELECT count(*) FROM run").fetchone()[0]
        return {"record_rows": records, "run_rows": runs}

    def duplicate_keys(self) -> int:
        """The number of keys that the table holds two times at one revision.

        The `record` table carries no unique key, so this is the one test that
        shows a duplicate. It must be 0. A probe on 2026-09-22 measured 0.4
        seconds for 6.6 million rows, so `atlas status` can run it every time.
        """
        return self.conn.execute(
            """
            SELECT count(*) FROM (
              SELECT country, source_id, metric, fuel, ts_utc, kind, run_at, revision
              FROM record
              GROUP BY ALL
              HAVING count(*) > 1
            )
            """
        ).fetchone()[0]
