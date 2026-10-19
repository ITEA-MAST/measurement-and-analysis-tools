# Architecture

Why the parts are separate. `RUNNING.md` says how to operate the system, and `REFERENCE.md`
says what the data means.

The program has two halves that do not touch each other at run time.

```
   the sources                the collection process              the portal
   ───────────                ──────────────────────              ──────────

   6 of 13   ──fetch──▶  raw/*.json.gz ──parse──▶ record ──view──▶ JSON ──▶ HTML page
   collected              the evidence            table    series   files    in a browser
                         on disk                 DuckDB
                              ▲                     │
                              └──── verify ─────────┘

   ◀─── one process, 2 timers: daily + 4 snapshots ───▶      ◀─ no network ─▶
```

The portal never calls a source API. A scheduled process collects the data in the
background and writes it to the store. The portal reads files that the same process wrote.

`atlas rebuild` walks the `parse` arrow again, from the raw files to a new `record` table, and
it makes no request. So the evidence on disk and the database are one chain, and a reader can
test it.

## The program at run time

The CLI has 9 commands. Three of them run from the task scheduler, and the table gives those
three with the two directories they write. `export`, `measure`, `status`, `verify`, `rebuild`
and `serve` are run by hand. `RUNNING.md` §2 gives the commands.

| Part | What it is | When |
|---|---|---|
| `atlas backfill` | One command. It fills the years the sources still serve. | One time for each new source. |
| `atlas daily` | Fetch, parse, store, rebuild the views, export the JSON. | One time each day, from the task scheduler. |
| `atlas snap` | The forward forecast curve of each source. | 4 times each day, 6 hours apart. The first is 00:00 on the local clock of the host. |
| `atlas rebuild` | It makes a new DuckDB file from the raw payloads alone. It never writes the live store. | By hand, and after a lost store. |
| `store/` | `atlas.duckdb` and the gzipped raw payloads. | It is a directory, not a service. The payloads of the 5 licensed sources are in the repository. |
| `portal/` | The HTML page and `portal/data/*.json`. | It is opened in a browser. |

There is no server, no queue, no message bus and no always-on process. If the machine is
off for a week, the next `atlas daily` asks for the week. Only a missed forecast snapshot
is lost for ever. See `REFERENCE.md` §7.

## Why this split

1. History. The APIs limit what they serve. Electricity Maps gives the last 24 hours on
   the free plan. energy-charts limits the rate to 2 requests each minute. The store keeps
   each reading it collects, so the history grows from the first collector run. The
   portal can then show a period that no API will serve again.
2. A page view does no network work. The analysis runs one time for each new day, not one
   time for each visitor.
3. A source outage does not make the portal fail. It makes a gap record.
4. One collector controls the rate for one source. The portal cannot cause a rate-limit
   block, because it makes no request.
5. Reproducibility. The store holds what the API returned. `atlas verify` re-reads each
   stored payload and compares its hash, so a number on a page traces back to the bytes
   that made it. `atlas rebuild` parses every payload again into a new store. So a reader can
   test the parser, and not only the bytes. The repository ships the payloads of the sources
   whose reuse terms are recorded. A clone makes its own store, with no network request.
   `LICENSE-DATA.md` names the two series that stay inside Wirtek, and `README.md` says what a
   clone holds.

## The collector

One collector for each source. Each collector has:

| Property | Rule |
|---|---|
| Schedule | One run each day for every source. The publishers keep their own history, so a daily run loses nothing. See `RUNNING.md` §3. |
| Request window | Only the period that the store does not have. Never a full refetch. |
| Rate control | Set from the published limit of the source. energy-charts is 2 requests each minute. |
| Failure | 3 tries. Then write a gap record with the error, and continue. Do not stop the other collectors. |
| Raw payload | Keep it. Derive after you store it. |
| Forecast | If the source publishes one, collect it on its own schedule and keep each run. A publisher replaces its forecast with the next run and does not keep the old one. |

A gap record is data. It tells the portal to show "no record" instead of a value, and it
tells the operator which source failed and when. The gap records live in the `run` table,
which also gives the process its to-do list. The key of that table is
(source_id, country, day, kind). See `REFERENCE.md` §5.

## The store

Three tables and one view in one DuckDB file, and a directory of gzipped payloads. `record`
holds the readings, `run` holds the collection log, and `meta` holds the store version. The
view `record_current` gives the newest revision of each key.

The `record` table is append only. The key is
(country, source_id, metric, fuel, ts_utc, kind, run_at), which is the same key
`atlas/store.py` partitions `record_current` by.

| Field | Purpose |
|---|---|
| `country` | ISO code from `sources/zones.json`. |
| `source_id` | Key from `sources/sources.json`. |
| `metric` | `intensity`, `power` or `load`. |
| `fuel` | The production type for `power`. Empty for the others. |
| `ts_utc` | The timestamp the source gave, converted to UTC. |
| `value` | The reading. |
| `unit` | The unit of the reading. A unit in the row stops a silent unit error. |
| `basis` | Production-based or consumption-based. |
| `scope` | Lifecycle or direct. |
| `granularity` | `native`, `aggregated`, `group` or `proxy`. |
| `zones` | The zones that an `aggregated` value came from. |
| `collected_at` | When the collector ran. |
| `revision` | 1 for the first reading. A correction from the publisher makes revision 2. |
| `kind` | `actual` or `forecast`. One column holds one kind. |
| `run_at` | For a forecast that this program captured: the time of the fetch. Empty for an actual, and empty for a forecast that came from the history of the publisher. |
| `horizon_min` | For a forecast: `ts_utc` − `run_at`. Empty when `run_at` is empty. |
| `raw_ref` | The path and the hash of the payload that made this row. |

The store keeps the step of the publisher. Energinet gives one value every 5 minutes, RTE
every 15, NESO every 30, and the two Elia series one each hour. energy-charts gives 15, 30
or 60 minutes. The collector does not resample on the way in, because a resample cannot be
undone. Electricity Maps and Eurostat are register entries, and no collector reads them, so
the store holds no row from either.

The step is a property of the country. `sources/sources.json` holds the observed steps. The
collector derives the real step from each payload and never assumes it.

The analysis step makes the common grid. A cell holds the mean of the records of that hour
or that day, and null when the store has no record. The daily grid carries the record count
of each cell, and the hourly grid does not. No cell carries a value forward.

One hour has one actual and many forecasts. A forecast must never overwrite an older
forecast of the same hour, and a forecast is never a fallback for a missing actual. See
`FORECASTS.md`.

A correction never overwrites a value. The publisher of a national series can revise
a number weeks later. RTE does this. The store keeps both, and the portal shows the newest
revision with the count of revisions.

## The analysis

It is SQL, in the same process. The panel queries are in `atlas/export.py` and the pair query
is in `atlas/analyse.py`. Both read `record_current`, and the last step of `atlas daily`
writes the result to `portal/data/*.json`.

A view is not a copy. If the roll-up weighting or the factor set changes, the next run
gives new numbers with no rebuild and no second store.

What it computes now:

- the daily mean and the hourly mean for each country and each source,
- the month statistics for each country and each year,
- the profile of each country: each hour of the day in each month, across all the years,
- the newest captured forecast curve of each country,
- the spread between the sources of one country, from 2026-09-23.

The spread sits in its own module, `atlas/analyse.py`, and not with the panel queries. It
answers the headline claim of the project, so a reader must find the query in one place. The
module docstring holds the query in three steps, the sign rule and two traps. `atlas export`
calls it and writes `portal/data/pairs.json`. `atlas measure` prints the same table and writes
nothing. `REFERENCE.md` §9b and §9c give the result and the date of the run.

The spread is the one panel number that a document must not copy. Every other number on the
page moves slowly. A reader challenges the spread first. So the document gives the method and
a dated measurement, and the file gives the value of today.

What it does not compute yet, and what each one waits for:

| Not built | It waits for |
|---|---|
| A panel that gives the spread of each hour | Portal work only. The Source discrepancy tab reads `pairs.json` and draws each pair over all its shared hours since 2026-09-23. It gives no row for each country and hour. |
| The basis effect against the method effect, as two written claims | A rule. `pairs.json` already separates the two: the `kind` field is `basis` for the two Elia series and `method` for every other pair. `REFERENCE.md` §9c says why the two effects must stay two claims. |
| The generation mix by production type | The `/public_power` collector. |
| The load-weighted country value for the other roll-up countries | The load series of each one. Denmark is done: DK1 and DK2 are weighted by the gross consumption of the same hour. |
| The forecast score: error, bias and the skill against persistence | Many captured runs, or the forecast column that NESO publishes beside each measurement. |
| The decision test: did the forecast pick the cleanest hour? | Captured forecast runs, as the row above. The same test between two sources is built. `atlas/analyse.py` runs it, and `REFERENCE.md` §9b reads it. |

The portal does no aggregation of its own. If a panel needs a number, the analysis step
must produce it. `REFERENCE.md` §10 holds the same list with the reason for each one.

## The portal

Reads `portal/data/*.json`. It makes no query and no network request. It shows:

- the value and its `granularity` badge,
- the sources behind each panel, from `sources/sources.json`,
- which countries hold two or more sources, and which source can give the second value. The
  spread itself is in `portal/data/pairs.json` since 2026-09-23, and the Source discrepancy
  tab draws each pair from that file,
- the collection metadata on the Raw data tab. That is the stored range, the days ok,
  the days empty, the days failed, and the error text of a failure.

`portal/README.md` gives the tabs, and `REFERENCE.md` §8 gives the export contract. Start it
with `.venv\Scripts\python.exe -m atlas serve`.

## The written panels

Some panels give a written conclusion. *Which source can give the second value* is one, and
the Reading column of *Head to head* is another. A rule fills a template, and no model runs.

A panel of this kind carries a `built from the register` badge. Today the badge is on
*Which source can give the second value* only, at `portal/index.html:291`, and the Reading
column of *Head to head* carries none. If the program later adds a model, the badge must
say so.

### The three layers, and how fast each one ages

| Layer | Example | Updates | Maintenance |
|---|---|---|---|
| 1. Computed | "The band stays between 61 and 94 g, so this is a method gap." | On each collection run | None |
| 2. Register | "Lifecycle, production-based against lifecycle, consumption-based." | When `sources/sources.json` changes | The same review the collectors already need |
| 3. Fixed claim | "Publishers use different lifecycle factor tables." | Never, by itself | A person, on a review date |

Layer 1 follows the new data with no work. It is most of the text.

Layer 2 follows the register. A method change breaks the collector before it breaks the
prose. If Electricity Maps changes its flow-tracing method, the normalisation step is
already wrong.

Layer 3 is the only part that can go stale in silence. The rules below control it.

### Rules for the rule

1. A sentence must have an input. Write a sentence only when its input is present. If
   the country has no monthly source, do not write the sentence about monthly resolution.
   A sentence that is always true for every country is a fixed claim, not an explanation.
2. Branch on the register, never on a source name. The branches key on `basis`,
   `scope`, `resolution` class and `granularity`. A new source then gets the correct
   sentence on the day its collector starts, with no change to the rule.
3. Fail loudly. If the rule cannot classify an input, it writes that it cannot. It
   never writes a confident sentence by default.
4. A fixed claim must carry two dates, `checked` and `next_review`, and the panel must show
   them. The review interval is 6 months. No register entry carries these two dates today.
5. Do not make a claim about an unsettled source. If the register status is not
   `verified-live`, the rule names the source and its status instead.
6. Thresholds are configuration, not prose. If "steady" means that the widest band is less
   than 2.2 times the narrowest, that number must be owned, dated and shown. No panel uses
   a threshold of this kind yet.
7. ⚠ The size of a gap and the direction of a decision are two claims. Measured
   2026-09-18 on Belgium, and again on 2026-09-23 with the same two numbers. The accounting
   basis moves the 2-year mean by 1.3 %. It changes the cleanest hour of the day on 61.8 % of
   days. A rule that says "the basis explains the difference" is true for the second claim and
   false for the first. Write the two sentences separately, and give each one its own number.
   The `gap_share_pct` and `same_hour_pct` fields of the `basis` pair in `pairs.json` hold the
   two numbers of today. `REFERENCE.md` §9c.

### Signals that layer 3 or layer 2 has gone stale

None of the three is built. Each one is a design, and what it waits for follows it.

1. Methodology drift. The collector stores a hash of each methodology URL, and a change sets
   the register entry to `needs-review`. It waits for a hash field in `sources/sources.json`.
   `field_hash` in `atlas/collectors/base.py` hashes the payload field names. It does not
   read a URL.
2. Review date passed. A fixed claim past `next_review` is shown with its age. It waits for
   the two dates of rule 4.
3. The measurement contradicts the text. The analysis step compares the new spread against
   the band the last explanation implied, and a large move raises an alert. The spread is
   measured since 2026-09-23 and it is in `portal/data/pairs.json`. This signal now waits for
   the band only: a register field that states what each explanation implies.

## Open points

1. Retention of the raw payloads. The rule today is: keep all of them. The store holds
   47.7 MB gzipped across 364 files, measured 2026-09-23, so the cost is small. 223 of those
   files are in the repository, and they are 20.9 MB to download. `RUNNING.md` §4 holds the
   sizes.
2. The roll-up weighting and the factor set. See `SOURCES.md` §9 and §8.
3. The wrap of the cleanest-hour test. `atlas/analyse.py` takes the plain difference of the
   two hours in `within_one_hour_pct`, so hour 23 and hour 00 count as 23 hours apart.
   `REFERENCE.md` §10 holds this point. The denominator of the disagreement share was the
   other open point here. 2026-09-23 closed it: every share divides by the larger mean of the
   pair.

Settled on 2026-09-23: the figures of `REFERENCE.md` §9b and §9c were measured by hand until
that day. `atlas/analyse.py` now holds the query, `atlas measure` prints it, and
`portal/data/pairs.json` carries the result of the last run. A reader can repeat every figure
of those two sections with one command.

Settled on 2026-09-17: the store technology is DuckDB. The analysis runs at the end of
`atlas daily`.

Settled on 2026-09-23: `atlas rebuild` makes the DuckDB file again from `store/raw/`, with no
network request. The payloads are the evidence for an audit. `atlas verify` re-reads each one
and compares its hash. `rebuild` parses each one again into a new store. So a lost store comes
back in about 3 minutes. `atlas backfill` over the network is the other way, and it cannot
serve the periods that now answer HTTP 500.

⚠ A rebuilt store is not the collected store. It holds the same measurement values, and it
holds no failed day and no snapshot `run_at`. `RUNNING.md` §4 holds the table of the 7
differences, and `atlas/rebuild.py` sections 3 and 4 hold the contract.

`tests/test_s1.py` holds 3 sections for the command, and 62 of its 337 checks. They test the
three refusals, the two skips and the records that a rebuild writes. A payload that fails its
hash is one skip, and a payload that fails to parse is the other. One check reads the store
that the command must not touch, byte for byte, before and after a rebuild.
