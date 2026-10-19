"""The pair table: what two publishers of one country say about the same hour.

Every share in this module divides by the larger of the two means, and the
output states it in the field `denominator`. That denominator keeps each share
inside 100 %, it is the energy-charts mean in all five method pairs, and every
document of the project reports it.

This module answers one question, and the docstring is the answer to it. The
project claims that two publishers of one country disagree by a large share.
REFERENCE.md section 9b gave that claim from a hand query, and no shipped
command wrote it. `atlas measure` and `portal/data/pairs.json` now write it.

**The query.** Three steps, and each one is a named CTE below.

1. `hourly`: the mean of each (country, source, hour) of `record_current`,
   where `metric = 'intensity'` and `kind = 'actual'` and `value IS NOT NULL`.
2. `shared`: an inner join of `hourly` on (country, hour), with
   `a.source_id < b.source_id`. That join gives every pair of sources that
   share a country, and one row for each hour that both of them report.
3. The aggregate: the mean of each side, the mean gap, the mean absolute gap,
   and the correlation, over those shared hours.

A second query repeats steps 1 and 2 for the decision test. It keeps the days
that BOTH sources cover with 24 hours, and it compares the hour of each
source's own minimum on those days. Two hours of one day that hold one value
are a tie, and the earliest of them wins. The comment above `_DAY_SQL` gives
the measurement that made that rule necessary.

**The sign is stable.** `a` is the alphabetically first `source_id` of the
pair, and `b` is the second. `mean_gap` is `mean_a - mean_b`. `ratio` is
`mean_a / mean_b`. A pair keeps the same `a` between runs, so the sign of the
gap never turns over.

⚠ **The join is on the hour, and not on `ts_utc`.** The sources do not share a
step. Energinet gives 5 minutes, Elia and RTE give 15 minutes, NESO gives 30
minutes, and energy-charts gives 15 or 60 minutes by country and by period. A
join on the raw `ts_utc` then counts a sub-hourly source many times inside one
hour, and it weights the recent years of the store above the old ones, because
the step got shorter over time. Measured on 2026-09-23: the raw join puts the
Danish pair at 126.1 / 265.2 over 104,431 rows, and the hourly join puts it at
134.5 / 284.2 over 85,182 hours. The second pair of numbers is the one that
REFERENCE.md section 9b reports. The mean of a publisher must not move because
that publisher changed its step, so the hour is the unit of comparison.

⚠ **The denominator is the larger mean of the pair, and the numerator keeps
the sign of `mean_a - mean_b`.** `gap_share_pct` is
`mean_gap / max(mean_a, mean_b) * 100`, and `abs_gap_share_pct` divides
`mean_abs_gap` by the same number. The denominator is therefore a property of
the data, and the sign is a property of the alphabet. A division by `mean_a`
instead puts DK at -111.3 %, because `energinet-eds` sorts first and holds the
smaller mean. The larger mean puts that same gap of 149.7 g at -52.7 %.
REFERENCE.md section 9b and every other document report the second number.

Three reasons decided that denominator on 2026-09-23.

1. The seven documents and the whole history of the project report the share
   this way. The other choice rewrites the headline of the project.
2. It is bounded. `abs(mean_gap)` is never above the larger mean, so the share
   never passes 100 %, and "share of the mean" reads as it is written. A share
   of 111.3 % says that one series is twice another, which is not what the
   pair measures.
3. For all five method pairs of the store on 2026-09-23 the larger mean is the
   energy-charts mean. energy-charts is the common member of every method
   pair, so one denominator holds across the countries and the column compares.

`mean_a`, `mean_b`, `mean_gap` and `ratio` are in the file unchanged, so a
reader who wants another denominator can compute it.

**`kind` separates two causes.** A pair is `basis` when the two sources share a
publisher, a unit and a scope, and differ in the accounting basis alone. Today
that is the two Elia series, and section 9c measures what it separates. Every
other pair is `method`: the factor table, the model and the basis all differ
together, and no such pair can say which of them causes the gap. The factor
table is not a column of the store, so the publisher stands for it. Two series
of one operator use one table.

**The chance baseline.** Two series that agree by chance alone name the same
cleanest hour on 1 day of 24, which is 4.17 %, and come within one hour on 3
days of 24, which is 12.5 %. `chance` holds the two numbers, so a panel never
reports an agreement rate with no baseline beside it.

The module opens no file and writes none. `export.run` writes the result to
`portal/data/pairs.json`, and `atlas measure` prints it.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from . import config

# A pair with fewer shared hours than this is not measured. One week of hours.
# A shorter overlap gives a mean that one storm can move.
MIN_HOURS = 168

# The denominator of every share of this module. The output carries it as the
# field `denominator`, so no reader of the file has to guess which of the two
# means the share divides by. The docstring gives the three reasons.
DENOMINATOR = "larger mean of the pair"

# Two series that pick a cleanest hour at random agree on 1 hour of 24, and
# come within one hour on 3 of 24. Every agreement rate is read against these.
CHANCE_SAME_HOUR_PCT = 4.17
CHANCE_WITHIN_ONE_HOUR_PCT = 12.5

# The hour is the unit of comparison. The docstring says why, and the first ⚠
# gives the measurement that decided it.
_HOURLY_CTE = """
    hourly AS (
      SELECT country, source_id,
             date_trunc('hour', ts_utc) AS hour_utc,
             avg(value) AS value
      FROM record_current
      WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
      GROUP BY country, source_id, date_trunc('hour', ts_utc)
    )
"""

# `a.source_id < b.source_id` does two things at one time. It keeps one row of
# each unordered pair, and it makes `a` the alphabetically first source. So the
# sign of `mean_gap` is the same at every run.
_PAIR_SQL = f"""
WITH {_HOURLY_CTE},
shared AS (
  SELECT a.country    AS country,
         a.source_id  AS source_a,
         b.source_id  AS source_b,
         a.hour_utc   AS hour_utc,
         a.value      AS value_a,
         b.value      AS value_b
  FROM hourly a
  JOIN hourly b
    ON  a.country   = b.country
    AND a.hour_utc  = b.hour_utc
    AND a.source_id < b.source_id
)
SELECT country, source_a, source_b,
       count(*)                      AS shared_hours,
       min(hour_utc)                 AS first_hour,
       max(hour_utc)                 AS last_hour,
       avg(value_a)                  AS mean_a,
       avg(value_b)                  AS mean_b,
       avg(abs(value_a - value_b))   AS mean_abs_gap,
       corr(value_a, value_b)        AS correlation
FROM shared
GROUP BY country, source_a, source_b
ORDER BY country, source_a, source_b
"""

# The decision test. A day counts only when both sources cover all 24 hours of
# it, because the minimum of a part day is the minimum of the part.
#
# The two sources are compared on their own minimum, and not on a shared one,
# because the question is which hour each publisher would tell a scheduler to
# use.
#
# ⚠ **The tie-break is a part of the answer, and `arg_min` does not give one.**
# A publisher that reports whole numbers holds the same value for many hours of
# a quiet night, so the lowest hour of the day is often a tie. `arg_min` picks
# one of the tied hours by thread order, so the same query on the same store
# gave the Belgian method pair 68.53 %, then 68.36 %, then 67.83 % on three
# runs of 2026-09-23. A claim that moves between two runs cannot be shown to a
# reviewer. So the row number below states the order: the lowest value first,
# and the earliest hour of the tied ones. `round(value, 6)` holds that order
# steady too, because a parallel `avg` sums a sub-hourly source in a different
# order each time, and the last bits of two equal hours then differ.
_DAY_SQL = f"""
WITH {_HOURLY_CTE},
day_of_source AS (
  SELECT country, source_id,
         CAST(hour_utc AS DATE) AS day,
         hour(hour_utc)         AS cleanest_hour,
         count(*) OVER (
           PARTITION BY country, source_id, CAST(hour_utc AS DATE)
         ) AS hours_in_day
  FROM hourly
  QUALIFY row_number() OVER (
    PARTITION BY country, source_id, CAST(hour_utc AS DATE)
    ORDER BY round(value, 6) ASC, hour_utc ASC
  ) = 1
),
complete_day AS (
  SELECT * FROM day_of_source WHERE hours_in_day = 24
),
paired_day AS (
  SELECT a.country   AS country,
         a.source_id AS source_a,
         b.source_id AS source_b,
         abs(a.cleanest_hour - b.cleanest_hour) AS hours_apart
  FROM complete_day a
  JOIN complete_day b
    ON  a.country   = b.country
    AND a.day       = b.day
    AND a.source_id < b.source_id
)
SELECT country, source_a, source_b,
       count(*)                          AS days,
       count(*) FILTER (hours_apart = 0)  AS same_hour_days,
       count(*) FILTER (hours_apart <= 1) AS within_one_hour_days
FROM paired_day
GROUP BY country, source_a, source_b
"""

# ⚠ in the export module: the unit belongs to the source, and not to the file.
# The same rule holds here, and this query is where the pair reads it. A
# literal in the code goes stale the day a publisher changes its factor table.
_LABEL_SQL = """
SELECT country, source_id,
       string_agg(DISTINCT unit, ' / ')  AS units,
       string_agg(DISTINCT basis, ' / ') AS bases,
       string_agg(DISTINCT scope, ' / ') AS scopes
FROM record_current
WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
GROUP BY country, source_id
"""

METHOD = (
    "Every pair of sources that share a country, over the hours that both of "
    "them report. The mean of each source in each hour comes first. Then an "
    "inner join on (country, hour) of record_current, where metric is "
    "'intensity' and kind is 'actual' and value is not null. `a` is the "
    "alphabetically first source_id and `b` is the second. mean_gap is "
    "mean_a minus mean_b. ratio is mean_a divided by mean_b. gap_share_pct is "
    "mean_gap divided by the larger of mean_a and mean_b, times 100, and "
    "abs_gap_share_pct divides mean_abs_gap by that same larger mean. So the "
    "denominator comes from the data and the sign comes from the order of the "
    "two source ids. A day of the cleanest-hour test "
    "counts only when both sources cover all 24 hours of it, and the earliest "
    "hour wins when two hours of one day hold one value."
)


def _text(stamp) -> str | None:
    """One timestamp as `YYYY-MM-DD HH:MM:SS`. The store holds UTC with no zone."""
    if stamp is None:
        return None
    if isinstance(stamp, datetime):
        return stamp.replace(microsecond=0).isoformat(sep=" ")
    return str(stamp)


def _rounded(value, places: int) -> float | None:
    """A rounded number, and `None` for anything that JSON cannot hold.

    ⚠ DuckDB `corr` gives NaN, and not NULL, when one side of the pair holds
    one value at every hour. `json.dumps` writes NaN as the bare word `NaN`,
    which no strict JSON reader takes, so one flat series would break the whole
    portal file. A source that reports a constant is a defect the store already
    holds: REFERENCE.md section 2 gives the Georgian floor of 3.0.
    """
    if value is None or not math.isfinite(value):
        return None
    return round(value, places)


def _share(part: float | None, whole: float | None) -> float | None:
    """`part / whole * 100`, to 1 decimal. A whole of 0 gives no share.

    No stored intensity is below 3.0 g, so a mean of 0 needs a source that
    reports one value of 0 and nothing else. It must give null, and not stop
    the export of the other 8 files.
    """
    if part is None or not whole:
        return None
    return _rounded(part / whole * 100, 1)


def _larger(mean_a: float | None, mean_b: float | None) -> float | None:
    """The larger of the two means. It is the denominator of every share here.

    The docstring of the module gives the three reasons for that choice. A
    `None` on one side gives the other side, and two of them give `None`. So a
    pair with one absent mean makes no share, and it stops no export.
    """
    if mean_a is None:
        return mean_b
    if mean_b is None:
        return mean_a
    return max(mean_a, mean_b)


def _kind(source_a: str, source_b: str, label_a: dict, label_b: dict) -> str:
    """`basis` when the pair differs in the accounting basis alone.

    The factor table is not a column of the store, so the publisher stands for
    it: two series of one operator use one table. A `basis` pair therefore
    needs one operator, one unit, one scope and two bases. Today the two Elia
    series of Belgium are the only pair that meets that, and REFERENCE.md
    section 9c is what they measure. Every other pair is `method`.
    """
    register = config.sources()
    operator_a = (register.get(source_a) or {}).get("operator")
    operator_b = (register.get(source_b) or {}).get("operator")
    one_publisher = operator_a is not None and operator_a == operator_b
    if (
        one_publisher
        and label_a["unit"] == label_b["unit"]
        and label_a["scope"] == label_b["scope"]
        and label_a["basis"] != label_b["basis"]
    ):
        return "basis"
    return "method"


def pairs(store) -> dict:
    """The pair table as plain data. It reads the store and writes nothing."""
    labels = {
        (country, source_id): {"unit": unit, "basis": basis, "scope": scope}
        for country, source_id, unit, basis, scope in store.query(_LABEL_SQL)
    }
    decision = {
        (country, source_a, source_b): (days, same, near)
        for country, source_a, source_b, days, same, near in store.query(_DAY_SQL)
    }
    last = store.query(
        "SELECT max(ts_utc) FROM record_current "
        "WHERE metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL"
    )

    out: list[dict] = []
    skipped: list[dict] = []
    for row in store.query(_PAIR_SQL):
        (country, source_a, source_b, shared_hours, first_hour, last_hour,
         mean_a, mean_b, mean_abs_gap, correlation) = row

        if shared_hours < MIN_HOURS:
            skipped.append(
                {"country": country, "a": source_a, "b": source_b,
                 "hours": shared_hours}
            )
            continue

        label_a = labels.get((country, source_a), {"unit": None, "basis": None, "scope": None})
        label_b = labels.get((country, source_b), {"unit": None, "basis": None, "scope": None})
        mean_gap = mean_a - mean_b
        # The larger mean, and not `mean_a`. The module docstring says why.
        denominator = _larger(mean_a, mean_b)
        days, same_hour_days, within_one_hour_days = decision.get(
            (country, source_a, source_b), (0, 0, 0)
        )

        out.append(
            {
                "country": country,
                "a": source_a,
                "b": source_b,
                "kind": _kind(source_a, source_b, label_a, label_b),
                "hours": shared_hours,
                "first_ts_utc": _text(first_hour),
                "last_ts_utc": _text(last_hour),
                "mean_a": _rounded(mean_a, 1),
                "mean_b": _rounded(mean_b, 1),
                "mean_gap": _rounded(mean_gap, 1),
                "mean_abs_gap": _rounded(mean_abs_gap, 1),
                "ratio": _rounded(mean_a / mean_b, 2) if mean_b else None,
                "gap_share_pct": _share(mean_gap, denominator),
                "abs_gap_share_pct": _share(mean_abs_gap, denominator),
                "correlation": _rounded(correlation, 2),
                "days": days,
                "same_hour_pct": _share(same_hour_days, days),
                "within_one_hour_pct": _share(within_one_hour_days, days),
                "unit_a": label_a["unit"],
                "unit_b": label_b["unit"],
                "basis_a": label_a["basis"],
                "basis_b": label_b["basis"],
                "same_unit": label_a["unit"] == label_b["unit"],
                "same_basis": label_a["basis"] == label_b["basis"],
            }
        )

    # The headline range: the lowest and the highest absolute share over the
    # `method` pairs. It covers those pairs alone, because a `basis` pair holds
    # the unit and the factor table still, and it answers another question.
    # REFERENCE.md section 9c. The denominator above makes this range the one
    # the documents report, so the repository states the statistic one way.
    spread = [
        abs(item["gap_share_pct"])
        for item in out
        if item["kind"] == "method" and item["gap_share_pct"] is not None
    ]

    return {
        "generated_at_utc": _text(datetime.now(timezone.utc).replace(tzinfo=None)),
        "store_last_ts_utc": _text(last[0][0] if last else None),
        # The file states its own convention, so no reader has to find the
        # denominator by dividing the columns of one row into each other.
        "denominator": DENOMINATOR,
        "method": METHOD,
        "min_hours": MIN_HOURS,
        "chance": {
            "same_hour_pct": CHANCE_SAME_HOUR_PCT,
            "within_one_hour_pct": CHANCE_WITHIN_ONE_HOUR_PCT,
        },
        "range": {
            "lo_pct": round(min(spread), 1) if spread else None,
            "hi_pct": round(max(spread), 1) if spread else None,
            "over": "method-pairs",
        },
        # A pair with too few shared hours is named here, and not dropped in
        # silence. A reader must be able to see that the pair exists.
        "skipped": skipped,
        "pairs": out,
    }


def lines(table: dict) -> list[str]:
    """The pair table as terminal lines. `atlas measure` prints these.

    ⚠ Every line here is ASCII. A Windows console runs cp1252, and `print` of
    one character outside it stops the command with `UnicodeEncodeError` after
    it wrote a part of the table. The warning glyph of the documents is
    therefore the word `WARNING` in this output.
    """
    head = (
        f"{'iso':4} {'a':22} {'b':22} {'kind':6} {'hours':>8} "
        f"{'mean a':>8} {'mean b':>8} {'gap':>8} {'ratio':>6} "
        f"{'share%':>7} {'|gap|%':>7} {'r':>6} {'days':>6} {'same%':>6} {'1h%':>6}"
    )
    out = [
        f"store to {table['store_last_ts_utc']}",
        f"{len(table['pairs'])} pair(s). A pair needs {table['min_hours']} shared hours.",
        "",
        head,
        "-" * len(head),
    ]

    def number(value, width: int, places: int = 1) -> str:
        return f"{'':>{width}}" if value is None else f"{value:>{width}.{places}f}"

    for item in table["pairs"]:
        out.append(
            f"{item['country']:4} {item['a']:22} {item['b']:22} "
            f"{item['kind']:6} {item['hours']:>8,} "
            f"{number(item['mean_a'], 8)} {number(item['mean_b'], 8)} "
            f"{number(item['mean_gap'], 8)} {number(item['ratio'], 6, 2)} "
            f"{number(item['gap_share_pct'], 7)} {number(item['abs_gap_share_pct'], 7)} "
            f"{number(item['correlation'], 6, 2)} {item['days']:>6,} "
            f"{number(item['same_hour_pct'], 6)} {number(item['within_one_hour_pct'], 6)}"
        )

    for item in table["skipped"]:
        out.append(
            f"{item['country']:4} {item['a']:22} {item['b']:22} "
            f"skipped, {item['hours']:,} shared hour(s)"
        )

    window = table["range"]
    denominator = table.get("denominator", DENOMINATOR)
    out += [
        "",
        f"range over the method pairs: {number(window['lo_pct'], 0)} % to "
        f"{number(window['hi_pct'], 0)} % of the {denominator}, absolute.",
        f"chance names the same hour on {table['chance']['same_hour_pct']} % of days, "
        f"and comes within one hour on {table['chance']['within_one_hour_pct']} %.",
        "",
        f"NOTE  share% and |gap|% divide by the {denominator}, so",
        "      neither one passes 100 %. The sign of share% comes from mean a",
        "      less mean b, and mean a is the alphabetically first source and",
        "      not the larger one. A minus sign says that the first source id",
        "      of the row holds the smaller mean.",
    ]
    return out
