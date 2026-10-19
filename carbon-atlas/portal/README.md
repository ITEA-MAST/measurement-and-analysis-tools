# Carbon Atlas — portal

The portal of the real store. It reads `data/*.json` and makes no request to a data source.
`atlas export` writes those files. See `../ARCHITECTURE.md`.

## How to open it

```
.venv\Scripts\python.exe -m atlas export   # write data/*.json from the store
.venv\Scripts\python.exe -m atlas serve    # give the portal at http://127.0.0.1:8765
```

`serve` opens a browser. A browser refuses to read a data file beside a page from the disk.
So `index.html` alone gives a red bar with this instruction.

## Files

| File | What it is |
|---|---|
| `index.html` | Structure. The controls, the 8 tabs and the collapsible source blocks. |
| `app.js` | Loading, calculation and rendering. Plain DOM and inline SVG. No libraries. |
| `style.css` | Wirtek brand tokens, the panels, the grids and the tooltip box. |
| `assets/` | The Wirtek logo, the dark header pattern and the "wi" glyph. |
| `data/` | What `atlas export` wrote. Nothing here is written by hand. `.gitignore` excludes it. |

## The data contract

The export writes 10 files that hold every country, and 2 files for each country.

| File | Shape |
|---|---|
| `meta.json` | The sources, the countries, the row counts, the stored range, and the unit and the granularity of each source. |
| `register.json` | `sources/sources.json` and `sources/zones.json`, copied whole. |
| `latest.json` | The newest value of each country, with its age in hours and a stale mark. |
| `monthly.json` | country × source × month: mean, lowest, highest, median. |
| `daily_all.json` | Source → country, a dense array of the last 400 daily means, with the record count of each day. |
| `hours.json` | Source → country, a dense array of the last 30 days of hourly means. |
| `profile.json` | Source → country, a 12 × 24 grid: month by hour of the day, all years. |
| `forecast.json` | The newest captured forward curve, for each country and each source that gives one. |
| `health.json` | The run table: days ok, empty and failed, for each country. Each series also gives the stored range, the records held, the records expected, the count absent, the step in minutes, and the widest hole. The hole is a date range: `hole_from`, `hole_to` and `hole_hours`. 18 fields, and the file names them in `fields`. |
| `pairs.json` | Each pair of sources that share a country, with the measured disagreement. See the table below. |
| `daily/<ISO>.json` | One country, every day of its history. |
| `recent/<ISO>.json` | One country, the last 14 days at the step of the publisher. |

The size of each file is in `../REFERENCE.md` §8. A size goes stale at each backfill, so this
table gives none. `atlas export` writes the total and the largest file to the log on each
run.

No export file states one unit for many sources. `meta.json` gives the unit of each source,
and every axis, table header and tooltip on the page takes the unit from there.

The page loads the 10 shared files at start, which is about 1.08 MB on 2026-09-23. It reads a
per-country file only when the Raw data tab asks for that country, and it keeps it.

Why three dense files: a panel that ranks 34 countries must not read 34 files. A dense array
also costs less than a row list, because it carries no country code and no timestamp.

⚠ The export keys the three dense files by source first. Two publishers give a different
number for the same hour of the same country, by 28.0 % to 52.7 % of the larger mean, measured
2026-09-23. A file keyed by country alone averages them into one cell, and the difference then
disappears without a trace. The Source control picks the key, and a panel never reads the
array of another source.

Belgium holds three arrays. One publisher, Elia, gives a production-based and a
consumption-based intensity for the same hour, and energy-charts gives a third number. The
two Elia series are two source ids, because `basis` is not part of the key of the record
table. A file keyed by country alone makes one of them a correction of the other.

### `pairs.json`, the disagreement measurement

`atlas/analyse.py` writes this file. `atlas export` calls it, so every `atlas daily` writes it
again, and `atlas measure` prints the same table to a terminal. The page must take the
disagreement from this file, and never from a number in a document.

The page loads this file apart from the other 9, and the absence of it is not a fault. An
export from before the analysis step holds no such file, and a file with no `pairs` array
counts as absent. `boot()` then leaves `D.pairs` empty, and the Source discrepancy tab hides
the measured block and keeps the state table.

Top-level keys, in order: `generated_at_utc`, `store_last_ts_utc`, `denominator`, `method`,
`min_hours`, `chance`, `range`, `skipped`, `pairs`. That is 9 keys.

| Key | What it holds |
|---|---|
| `denominator` | The text `larger mean of the pair`. Every share in the file divides by it. A panel that shows a share must name it. |
| `method` | One sentence that names the query. Show it beside the number, or behind the source block. |
| `min_hours` | 168. A pair with fewer shared hours is not measured. |
| `chance` | `same_hour_pct` 4.17 and `within_one_hour_pct` 12.5. Two series that agree by chance alone. Never give an agreement rate with no baseline beside it. |
| `range` | `lo_pct`, `hi_pct` and `over`. The lowest and the highest `abs(gap_share_pct)` over the pairs with `kind` `method`. |
| `skipped` | The pairs under `min_hours`, each with `country`, `a`, `b` and `hours`. It is an empty list on 2026-09-23. |
| `pairs` | One object for each pair of sources that share a country. 6 objects on 2026-09-23: BE 3, and DK, FR and GB 1 each. |

Each pair object holds 24 keys, in four groups.

- who: `country`, `a`, `b`, `kind`
- the shared hours: `hours`, `first_ts_utc`, `last_ts_utc`
- the gap: `mean_a`, `mean_b`, `mean_gap`, `mean_abs_gap`, `ratio`, `gap_share_pct`,
  `abs_gap_share_pct`, `correlation`
- the decision test and the labels: `days`, `same_hour_pct`, `within_one_hour_pct`, `unit_a`,
  `unit_b`, `basis_a`, `basis_b`, `same_unit`, `same_basis`

`kind` is `basis` when the two sources share a publisher, a unit and a scope, and differ in
the accounting basis alone. Today that is the two Elia series only. Every other pair is
`method`, and no `method` pair can say which of the basis, the scope and the factor table
causes its gap. A panel must not merge the two kinds into one claim. `../REFERENCE.md` §9c
says why.

⚠ `a` is the alphabetically first `source_id`, and not the larger mean. So `mean_gap` and
`gap_share_pct` are negative when the first source holds the smaller mean. That is the case
for DK and for the two Belgian method pairs on 2026-09-23.

`gap_share_pct` and `abs_gap_share_pct` divide by the larger of the two means, and the
top-level field `denominator` states it. So no share passes 100 %, and the range of the file
is 28.0 % to 52.7 %, which is the range that the documents quote. A panel that renders
`gap_share_pct` must show the sign, or take the absolute value. Name the denominator with the
number.

⚠ `unit_a` and `unit_b` are not decoration. `analyse.py` reads both from the stored rows.
`same_unit` is false for 3 of the 6 pairs on 2026-09-23, and those three compare gCO₂/kWh
against gCO₂eq/kWh, which are two quantities. `same_basis` is false for all 6. A panel that
draws a pair must state both labels beside the two means.

Nullable fields that a panel must handle: `ratio`, `gap_share_pct`, `abs_gap_share_pct` and
`correlation` are null when the denominator is zero or the statistic has no value.
`same_hour_pct` and `within_one_hour_pct` are null when `days` is 0. `range.lo_pct` and
`range.hi_pct` are null when no `method` pair passes `min_hours`. `mean_a` and `mean_b` carry
1 decimal place, `ratio` and `correlation` 2, every percentage 1, and `hours` and `days` are
integers. Every timestamp is UTC in the form `YYYY-MM-DD HH:MM:SS`, with no zone suffix.

`within_one_hour_pct` counts a difference of at most 1 hour, and it includes the same-hour
days. It takes the plain difference of the two hours, so hour 23 and hour 00 count as 23 hours
apart. `../REFERENCE.md` §10 holds that open point.

## The tabs

| Tab | What it shows | State |
|---|---|---|
| Overview | 5 KPI tiles. The ranking with a bar. The tile map. The day hour by hour, with the band of the other days. The window day by day. | Complete |
| Time of year | The month × hour grid across all the years. Every month of every year. The month spread, with the lowest and the highest year. The last 365 days. Head to head. | Complete |
| Workload calculator | For an amount of energy: stay in the current region, move the run to the best region, or follow the cleanest region hour by hour. | Complete |
| Compare | Up to 6 countries. The window mean and range, the cleanest and dirtiest day of the year, the swing, the cleanest hour, and the stored range. | Complete |
| Source discrepancy | 5 KPI tiles. The method pairs, with the two means, the gap, the share of the larger mean and the correlation. The cleanest-hour test, with the chance rate in the same columns. The one basis pair. Then the state table of what each country needs, and the source that can give the second value. | The tab shows the live numbers of `data/pairs.json`, for BE, DK, FR and GB. It gives no row for each country and hour. |
| Forecast | The captured forward curve against the measurement, and the horizon of each country. | No score. It needs many captured runs. |
| Raw data | 6 cards above the table: Country, Source, Stored range, Days collected, Records and holes, and Licence. Then the stored records at the step of the publisher, the day-by-day table, the coverage and failures table, the pipeline and a CSV download. | Complete |
| Source register | Every source in the register, with basis, scope, access, licence, risks and clickable links. | Complete |

### The coverage table reads `health.json` by field name

Each column names the fields that it shows, and the table never reads a fixed position. The
file states the order in `fields`. A field that no column names gets a column of its own at
the end of the row, so a new field in the file reaches the page on the day that it appears.

The file holds 18 fields, and the table shows 11 columns: country, source, kind, collection
ran, step, records, absent, widest hole, days, last run, and error or note. The exact counts
and the exact stamps are in the tooltip of the cell. The text of the collector sits behind a
detail block, as "The error: " and "The note: ". The CSV download keeps every field and every
row.

⚠ The `collection ran` column is not the range of the stored data. `export.py` takes
`first_day` and `last_day` from the run table. The two name the first day and the last day on
which the collector ran and reported no error. On 2026-09-23, 30 of the 39 actual rows give a
different day from the first stored record of the same series. AT gives 2015-06-01 against a
first record at 2015-05-31 22:00. The Stored range card above the table gives the true
instants.

The column carried the label `stored range` until 2026-09-23. That label put two answers to
one question on one screen.

## Three rules that the portal follows

1. It never mixes two sources into one value. The store holds 6 sources, and 4 countries hold
   two or more. The discrepancy is a measurement, and it is never an average.
2. It states what it does not have. A country with no record shows "no record", and never a
   value from another hour or another source.
3. It changes no basis. The page states the basis and the scope of the source, and it
   converts nothing. A control that multiplies a value by a factor is an invention, so this
   portal has none.

## How the page explains itself

Tooltips use a `data-tip` attribute. A `title` waits about a second, it cannot hold a colour
mark, and a cell of the 365-day strip is 2 px wide. The pointer leaves that cell before the
browser opens a `title`. One box in `app.js` shows `data-tip` at once, and it holds HTML, so
a chart gives one line for each country.

Each chart draws a transparent column for each point, so the pointer finds the value anywhere
in the column. The column gives the value of every series at that point.

The prose of the page is ASD-STE100. `../.ste-ui.md` holds a copy of the visible text, for
the style checker. Change a string in the page, change it there, and run the checker again.

The header gives the counts of the store and the export time, and the tray strip gives how
many countries report the hour on screen. The page makes no claim about where the numbers
come from, because the "Sources behind this panel" block gives that.

## The Source control changes the page

The store holds 6 sources, and 5 of them report one country each. So the Source control does
more than change a number:

- the country list follows the source, and a country that it does not report leaves the tray,
- the unit follows the source. energy-charts and the two Elia series give gCO₂eq/kWh, and
  NESO, RTE and Energinet give gCO₂/kWh. Every axis, tooltip and table header takes the unit
  of the source on screen,
- a source with one country gets its own KPI tiles. "Cleanest" and "dirtiest" name the same
  country there, and a ratio of one country against itself is always 1.0,
- the Time of year, Raw data and Compare panels read the rows of that source only.

## Two rules that the data forced

The publishers do not finish at the same time. At the newest hour in the store only 1 country
of 34 has a record, and a ranking of 1 row is not useful. So the page does not open on the
newest hour. It opens on the newest hour that holds at least 90 % of the records of the best
hour of the last 3 days. The tray strip always states how many countries report the hour on
screen.

A sum across "the hours that this region has" gives a region with fewer hours a smaller
total, and that reads as a saving. So the calculator compares only regions that cover the
whole run. A region enters the comparison only when it reports every hour of the run, and the
panel names the regions that it left out. The day steps back when the current region does not
cover the run.

## What the portal found

⚠ Georgia sits at a floor of 3.0 gCO₂eq/kWh for months at a time. The season panel shows a
swing of 80.8× across the months of Georgia. 8 months hold a mean below 8 g, and each of the
8 holds 89 % to 100 % of the hours of its month. The collector guards cannot catch the
floor, because 3.0 g is inside every sensible band. See `../SOURCES.md` §1.1.

The page now marks that defect. `DATA_FLAG` in `app.js` holds one entry, `GE`. It carries a
mark, a rule and the measurement behind the rule. The badge reads `floor at 3.0`. The tooltip
gives the rule of `../REFERENCE.md` §2, "Do not quote a Georgian number", with the counts
that support it.

The flag hides no value and drops no country. It goes on the KPI tiles, the ranking row, the
tile of the map and the Overview callout. It also goes on the season callout, the best-region
tile and the candidate table of the workload calculator, the compare card, and the Country
card of the Raw data tab.

`dataFlag()` reads a `quality` object of the country entry of `register.json` first, and it
falls back to `DATA_FLAG`. No country entry carries one on 2026-09-23. Delete a country from
`DATA_FLAG` on the day that the register carries it. If you do not, the page states the
defect two times.

Belgium shows that the accounting basis moves the schedule more than it moves the mean.
Select `elia-co2-production` and then `elia-co2-consumption`. The window mean moves by 1.3 %,
and the cleanest hour of the day moves on 61.8 % of days, measured 2026-09-23. One publisher,
one unit, one factor table, and only the basis differs. The `basis` pair of `data/pairs.json`
holds both numbers of today. See `../REFERENCE.md` §9c.

## What is not here yet

- Generation mix. No mix is collected. It arrives with `energy-charts /v2/public_power`.
- A load-weighted mean. Every mean on this page is a time mean. The export field is called
  `mean_unweighted` for that reason. The load series arrives with `/public_power`.
- The spread of each hour. The Source discrepancy tab draws each pair of `data/pairs.json`
  over all its shared hours since 2026-09-23. It gives no row for each country and hour, and
  no widest pair of an hour.
- The forecast score. It needs more collection.
- A permalink, a saved view and an export of a comparison.
