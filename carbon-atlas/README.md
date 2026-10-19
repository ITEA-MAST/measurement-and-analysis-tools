# carbon-atlas

A multi-source grid-carbon analysis system for European countries, with an HTML portal.

It collects the carbon intensity of the electricity grid, keeps every reading with its
source, and gives a portal that compares countries, seasons and hours. For an amount of
energy it computes the CO₂ in each country, and the CO₂ if the work follows the cleanest
country hour by hour.

The store holds 6.59 million records from 6 sources, for 34 countries, from 2011-12-31. Four
countries have two or more publishers. Over the hours that both of them report, one publisher
gives 1.4 to 2.1 times the number of the other. That gap is 28 % to 53 % of the larger mean of
each pair, measured on 2026-09-23. `REFERENCE.md` §9b.

`portal/data/pairs.json` holds that measurement, with every pair, the query that made it and
the date it ran. `atlas measure` prints the same table, and every `atlas daily` writes the file
again. Take the number of today from the file, and not from a document.

⚠ A clone of this repository measures 3 of those 5 pairs, and not the largest one. The
Denmark pair and the Great Britain pair need the two series that stay inside Wirtek. Read
"What a clone gets, and what it does not" below before you quote the range from a rebuilt
store.

Belgium separates the cause of that disagreement. One publisher gives both accounting bases
for the same hour, in one unit, from one factor table. The basis moves the 2-year mean by
1.3 %, and it changes the cleanest hour of the day on 61.8 % of days, measured on 2026-09-23.
`REFERENCE.md` §9c.

The earlier investigation is in `carbon-aware 1/`, beside this directory. It used 2
publishers, energy-charts and NESO. This system replaces it, and that directory stays
read-only. `SOURCES.md` §0.

## Run it

The interpreter is Python 3.11. `requirements.txt` pins `duckdb` and `httpx` to the exact
versions that made every number in these documents. `RUNNING.md` §1.

```
python -m venv .venv                          # with Python 3.11
.venv\Scripts\python.exe -m pip install -r requirements.txt

.venv\Scripts\python.exe -m atlas rebuild --into ..\atlas-store   # about 2 minutes, no network
set ATLAS_STORE=..\atlas-store                # PowerShell: $env:ATLAS_STORE = '..\atlas-store'
.venv\Scripts\python.exe -m atlas export      # writes portal/data/
.venv\Scripts\python.exe -m atlas serve       # the portal at 127.0.0.1:8765
```

First look for `store/atlas.duckdb`. If that file is present, the copy you hold already has
the data. Then skip the rebuild and start at `export`. A clone has no `atlas.duckdb` and no
`portal/data/`, because `.gitignore` excludes both. A clone does hold `store/raw/` for the
licensed sources, so `atlas rebuild` makes the store from the files on disk.

`atlas backfill` is the other way to a store. It asks every publisher for every day, and it
takes about 2 hours 47 minutes. Use it for the days after the last commit, and for a source
that this repository does not ship.

`rebuild` and `backfill` write the store. `export` reads the store, and the portal reads the
export. So each step needs the step before it.

`rebuild` never writes `store/atlas.duckdb`. `--into` is required, and the command stops if
the directory it names already holds an `atlas.duckdb`. `ATLAS_STORE` then points the other
commands at the new directory. `RUNNING.md` §4 gives the recipe and the limits.

### What a clone gets, and what it does not

A clone holds the raw payload of every source whose reuse terms are recorded. That is 223
files. They are 32.0 MB in the working tree and 20.9 MB to download, counted on 2026-09-23 in
decimal MB.

| In the clone | What it gives |
|---|---|
| `energy-charts-co2eq`, 145 payloads | 34 countries, from 2015-05-31. Fraunhofer ISE, CC BY 4.0. |
| `energy-charts-co2eq-snap`, 36 payloads | The captured forward forecast curves. 29 of the 34 countries give one. |
| `rte-eco2mix-odre`, 36 payloads | France, from 2011-12-31. RTE through ODRÉ, Licence Ouverte v2.0. |
| `elia-co2-production`, 3 payloads | Belgium, production basis, from 2024-09-30. Elia Open Data Licence. |
| `elia-co2-consumption`, 3 payloads | Belgium, consumption basis, from 2024-09-30. Elia Open Data Licence. |

| Not in the clone | Why |
|---|---|
| `energinet-eds`, 24 payloads. The Denmark series of Energinet | Nobody read the reuse terms of the publisher, so nobody knows the right to republish. `LICENSE-DATA.md`. |
| `neso-carbon-intensity` and `neso-carbon-intensity-snap`, 117 payloads. The Great Britain series of NESO | The same reason. |

The absence of those two series is a licence decision and not a hole in the data. Both series
are collected, both are complete, and both stay inside Wirtek until somebody reads the terms
of the publisher and records them in `sources/sources.json`.

Measured on 2026-09-23: a rebuild of the 223 licensed payloads gives 5,415,932 records,
against the 6,590,460 of the live store. It holds 34 countries, the same as the live store,
and the same first and last hour, 2011-12-31 23:00 to 2026-09-23 09:00 UTC. The checksum of
each of the 4 licensed source ids is equal to the live one, value by value.

⚠ Denmark and Great Britain do not disappear from a clone. energy-charts publishes both, and
energy-charts is licensed. DK falls from 1,140,752 rows to 118,464, and GB from 337,176 to
184,994. What a clone loses is the second publisher of each country.

So the Source discrepancy tab draws 4 pairs and not 6. A reader of a clone measures -1.3 %,
-28.9 %, -28.0 % and 39.6 %. That reader cannot measure the -52.7 % of the Denmark pair or the
29.4 % of the Great Britain pair.

Two more numbers of a rebuilt store differ from the collected one, and `RUNNING.md` §4 gives
both in full. The run table holds no failed day, because a failed request wrote no payload. So
`health.json` reads `days_fail` 0. A forecast `run_at` is the collection time of the payload,
and not the time of the snapshot pass. So the Forecast tab counts 61 energy-charts runs where
the live store counts 4. Every measurement value is the same.

One thing runs before you have any data. `.venv\Scripts\python.exe tests\test_s1.py` runs
337 checks in seconds and makes no network request. The portal needs an export, so it shows
nothing until a store and an `export` are there.

On Linux and on macOS the interpreter is `.venv/bin/python`. The atlas commands are the same.

Then one run each day keeps it current:

```
.venv\Scripts\python.exe -m atlas daily       # the new days, then the export
.venv\Scripts\python.exe -m atlas snap        # the forward forecast curves
```

`ops/register-tasks.ps1` makes the two Windows scheduled tasks that do this.

Three more commands read the store and change nothing:

```
.venv\Scripts\python.exe -m atlas status      # what the store holds, and the failures
.venv\Scripts\python.exe -m atlas verify      # each raw payload against its sha256
.venv\Scripts\python.exe -m atlas measure     # what two publishers of one country disagree by
```

`verify` is the traceability check. It reads every raw payload again and compares it with the
hash that the store keeps. `measure` prints the pair table that `portal/data/pairs.json`
holds. All three open the store read only and take no lock, and all three stop with exit
code 2 while a writer holds the store. `RUNNING.md` is the operator manual, and its §2
documents all 9 commands.

## Read this before you quote a number

| Fact | Where |
|---|---|
| Two publishers of one country disagree by 28 % to 53 % of the larger mean. They pick the same cleanest hour on 3 days of 10. Measured 2026-09-23. Always name the source with the number. | `REFERENCE.md` §9b, `portal/data/pairs.json` |
| A share of a gap needs its denominator. Every share of this system divides by the larger mean of the pair, and `pairs.json` states it in the field `denominator`. A minus sign says that the alphabetically first source holds the smaller mean. | `REFERENCE.md` §9b |
| The store holds two units. energy-charts and Elia give gCO₂eq/kWh. NESO, RTE and Energinet give gCO₂/kWh. | `REFERENCE.md` §1 |
| The basis is not the same in every source: production, consumption-inclusive and consumption-based are all in the store. | `REFERENCE.md` §1 |
| Every mean is a time mean. No mean uses the demand as a weight. | `REFERENCE.md` §1 |
| All times are UTC. The publishers count a day in local time. | `REFERENCE.md` §1 |
| The store is short by 3.22 % of the records that the step of each publisher makes necessary. CY, ME and GE hold 88.9 % of that shortfall, and CY, GE and MD each started again only on 2026-08-23, after a stop of years. | `REFERENCE.md` §2 |
| The newest hours hold fewer series than the store has. Of the 39 series, 35 reach 2026-09-22 22:00 and 7 hold nothing on 2026-09-23, because the publishers finish at different times. | `REFERENCE.md` §2 |
| ⚠ Do not quote a Georgian number. The source holds 8 months of it with a minimum of exactly 3.0 g. | `REFERENCE.md` §2 |
| ⚠ Do not quote the hour of the spring time change. Two publishers break in it. | `REFERENCE.md` §2 |
| 2 of the 36 zones hold no record: IE and MK. `sources/zones.json` gives the reason for each. MD holds records only from 2026-08-23. CY and GE started again on that same day, after a stop of years. Each of the three holds fewer than 1,000 records since. GE and XK start in 2021. | `sources/zones.json`, `REFERENCE.md` §2 |

## The documents

| File | What it is |
|---|---|
| `RUNNING.md` | The operator manual. Install, the commands, the schedule, the store, backup, the locks, troubleshooting. |
| `REFERENCE.md` | The technical reference. How to read a number, the known defects of the data, the tables, the guards, the forecast model, the export contract. |
| `ARCHITECTURE.md` | Why the collection and the portal do not touch each other, and how the written text on a panel is built. |
| `SOURCES.md` | The source register in prose. Every source: what it gives, what it costs, what it gets wrong, and if a live probe verified it. |
| `FORECASTS.md` | The forecast sources, their horizons, how a prediction is stored, and how it is scored against the measurement. |
| `portal/README.md` | The portal: the tabs, the data contract, and the two rules that the data forced. |

## The layout

| Path | What it is |
|---|---|
| `atlas/` | The collection program. `store` is the DuckDB file. `net` owns the rate limit. `raw` writes the payload to disk. `runner` is the shared loop. `collectors/` holds one module for each source. `analyse` measures the pairs of sources. `export` writes the portal JSON. |
| `sources/sources.json` | The machine-readable register. The collectors and the portal read this file. It is the single definition of a source. Never hard-code a URL anywhere else. |
| `sources/zones.json` | The canonical country list, 36 entries, with the per-source mapping. The single definition of a region. Never hard-code a country list anywhere else. |
| `store/` | The data. `atlas.duckdb`, the gzipped payloads in `raw/`, and the logs. `raw/` is the part to back up. The repository ships 5 of the 8 directories under `raw/`. `.gitignore` holds back the DuckDB file, the logs, and the 3 directories of the two series that stay inside Wirtek. |
| `portal/` | The portal. It reads `portal/data/*.json` and makes no network request. |
| `tests/test_s1.py` | The tests. They make no network request, and they print their own count. `RUNNING.md` §1. |
| `ops/register-tasks.ps1` | It makes the two Windows scheduled tasks. |
| `LICENSE`, `LICENSE-DATA.md`, `NOTICE.md`, `CITATION.cff` | The code is Apache-2.0. The collected data is CC BY 4.0, and each series also keeps the terms of its publisher. `LICENSE-DATA.md` states the terms of the payloads that this repository redistributes, and names the two series that it holds back. `NOTICE.md` names every publisher and the attribution it asks for. The Wirtek brand assets in `portal/assets/` are under no licence here. `CITATION.cff` is the citation form. |

## State

| Part | State |
|---|---|
| Source register | 13 entries from 11 publishers. Fraunhofer ISE and Elia each give 2 entries. Probed 2026-09-16, and cut from 27 entries to 12 on 2026-09-18, with one entry added after that. It holds a source only when that source can be collected. `SOURCES.md` §0.1. |
| Zone model | Country level, 36 countries, decided 2026-09-16. `sources/zones.json`. |
| Collection | Runs, 6 sources. energy-charts 34 countries from 2015-05-31 · Energinet DK from 2016-12-31 · RTE FR from 2011-12-31 · NESO GB from 2017-12-31 · Elia BE, both bases, from 2024-09-30. 6,586,295 measurements and 3,695 captured forecast points on 2026-09-23. The newest record is 2026-09-23 05:15 UTC. |
| Two sources for one country | BE with 3, and DK, FR and GB with 2. Every open source that publishes a sub-hourly or hourly national carbon series is collected. The other 30 countries wait for the ENTSO-E key. |
| Forecast capture | 6 captures in the store, on 3 days: energy-charts on 2026-09-17 and 2026-09-23, 29 countries each, and NESO on 2026-09-18 and 2026-09-23. The newest NESO curve reaches 50.4 hours ahead of its capture, and the newest energy-charts curve 38.5 hours. |
| Rebuild from the payloads | Built on 2026-09-23. `atlas rebuild --into <dir>` reads `store/raw/`, checks each sha256, parses each payload again and writes a new store. It makes no network request and it never writes `store/atlas.duckdb`. The full run is 2 min 43 s over 364 payloads; the 223 licensed payloads alone take 2 min 3 s. 62 of the 337 checks of `tests/test_s1.py` test it, in 3 sections. |
| Portal | Runs on the store. 8 tabs. The source control changes the country list, the unit and every panel. |
| Discrepancy measurement | Built on 2026-09-23. `atlas/analyse.py` measures each pair of sources that share a country, 6 pairs today, and writes `portal/data/pairs.json`. `atlas measure` prints it. `REFERENCE.md` §9b and §9c. |
| Discrepancy number in the portal | Built on 2026-09-23. The Source discrepancy tab reads `pairs.json` and draws the 6 pairs, the unit mark of each pair, the cleanest-hour test and the Belgian basis pair. It gives no row for each country and hour yet. `REFERENCE.md` §10. |
| Forecast score | Not yet. NESO publishes its own past forecast, which gives a score with no wait. `REFERENCE.md` §10. |
| Generation mix, and the load-weighted roll-up | Not yet, except Denmark, which is rolled up from DK1 and DK2 by load. `REFERENCE.md` §10. |

## The rules of this system

1. Every number carries a source id. A record without a `source_id` is a defect. The portal
   builds the collapsible source block from `sources.json`, so a missing id makes the panel
   unciteable.
2. Never mix sources inside one comparison, unless the system states the mixing and reports
   the size of the bias. The earlier investigation compared Fraunhofer numbers against NESO
   numbers with a fixed "±30 g" caveat. That band is the wrong shape, because the
   uncertainty scales with the level. `SOURCES.md` §3.
3. Record provenance, and not only the value. Actual and forecast are different data. So are
   settled and preliminary. The earlier pipeline collapsed the two with an `or` expression
   and lost the difference. A forecast carries `kind`, `run_at` and `horizon_min`, and it is
   never a fallback for a missing measurement.
4. Keep the raw payload, and keep the step of the publisher. Store what the API returned,
   then derive. Never resample on the way in, because a resample cannot be undone.
   Re-fetching is expensive: energy-charts allows 2 requests each minute. `atlas rebuild`
   makes the store again from those payloads, so the evidence and the database are one chain.
5. State the accounting basis. Production-based or consumption-based. Lifecycle or direct.
   These are not interchangeable, and the difference is larger than most of the effects that
   the system measures.
6. The unit of analysis is the country, and every value says how it got there. A value is
   `native`, `aggregated`, `group` or `proxy`. Aggregation from sub-national zones is
   load-weighted, and never an unweighted mean of intensities. A `group` value is one
   reading copied to several countries, so those countries are not independent.
7. The portal makes no request to a source. Collectors write to the store, and the portal
   reads the store.
8. Write all text in ASD-STE100 (Simplified Technical English). This applies to the UI text,
   the documents and the code comments. Describe the function. Do not argue a position.
9. Mark text that a rule generates. A panel that gives a written conclusion carries a
   `built from the register` badge. If a model ever writes the text, the badge must say so.
