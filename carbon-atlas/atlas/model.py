"""The record.

One row for each value. The key is
(country, source_id, metric, fuel, ts_utc, kind, run_at).
REFERENCE.md section 4.

The row carries `unit`, because the store holds two different quantities:
gCO2eq/kWh from energy-charts and Elia, and gCO2/kWh from NESO, RTE and
Energinet. The unit must travel with the row. REFERENCE.md section 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# The column order of the `record` table. The store and the parsers use it.
RECORD_COLUMNS = (
    "country",
    "source_id",
    "metric",
    "fuel",
    "ts_utc",
    "value",
    "unit",
    "basis",
    "scope",
    "granularity",
    "zones",
    "kind",
    "run_at",
    "horizon_min",
    "collected_at",
    "raw_ref",
)

# The vocabulary of the three columns that every query filters on.
# `Record.__post_init__` refuses a value that is not in these tuples.
# REFERENCE.md section 4 for `metric` and `kind`, and the granularity table.
METRICS = ("intensity", "power", "load")
KINDS = ("actual", "forecast")
GRANULARITIES = ("native", "aggregated", "group", "proxy")


@dataclass(slots=True)
class Record:
    country: str
    source_id: str
    metric: str
    ts_utc: datetime
    value: float | None
    unit: str
    granularity: str
    kind: str
    fuel: str = ""
    basis: str | None = None
    scope: str | None = None
    zones: str | None = None
    run_at: datetime | None = None
    horizon_min: int | None = None
    collected_at: datetime | None = None
    raw_ref: str = ""

    def __post_init__(self) -> None:
        """The vocabulary guard. A word that no query knows stops here.

        Every export query filters on `kind = 'actual'` or `kind = 'forecast'`,
        and on `metric`. A row with a different word goes in the store, counts
        in `atlas status`, and is absent from every panel. So the store must
        not take it.
        """
        if self.metric not in METRICS:
            raise ParseError(f"metric {self.metric!r} is not one of {METRICS}")
        if self.kind not in KINDS:
            raise ParseError(f"kind {self.kind!r} is not one of {KINDS}")
        if self.granularity not in GRANULARITIES:
            raise ParseError(
                f"granularity {self.granularity!r} is not one of {GRANULARITIES}"
            )

    def as_row(self) -> tuple:
        """The values in the column order of the `record` table."""
        return (
            self.country,
            self.source_id,
            self.metric,
            self.fuel,
            self.ts_utc,
            self.value,
            self.unit,
            self.basis,
            self.scope,
            self.granularity,
            self.zones,
            self.kind,
            self.run_at,
            self.horizon_min,
            self.collected_at,
            self.raw_ref,
        )


@dataclass(slots=True)
class RunRow:
    """One line of the to-do list. REFERENCE.md section 5."""

    source_id: str
    country: str
    day: object  # datetime.date
    kind: str
    status: str  # ok | empty | fail
    started_at: datetime
    finished_at: datetime
    run_at: datetime | None = None
    rows: int = 0
    http_status: int | None = None
    error: str | None = None
    raw_ref: str | None = None

    def as_row(self) -> tuple:
        return (
            self.source_id,
            self.country,
            self.day,
            self.kind,
            self.run_at,
            self.status,
            self.rows,
            self.http_status,
            self.error,
            self.raw_ref,
            self.started_at,
            self.finished_at,
        )


RUN_COLUMNS = (
    "source_id",
    "country",
    "day",
    "kind",
    "run_at",
    "status",
    "rows",
    "http_status",
    "error",
    "raw_ref",
    "started_at",
    "finished_at",
)


class ParseError(RuntimeError):
    """A guard in a parser stopped the write. REFERENCE.md section 6."""


class FetchError(RuntimeError):
    """The request failed after the last try."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status
