# Running the system

How to install, run, schedule, back up and repair the program. `REFERENCE.md` says what the
data means. Read `REFERENCE.md` §1 before you quote a number.

---

## 1. Install

Python 3.11 and two dependencies: `duckdb` and `httpx`. `requirements.txt` pins both to the
exact version that made every number in these documents.

```
cd carbon-atlas
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tests\test_s1.py        # 337 checks, no network
```

The tests make no network request and use a temporary store, so they never touch
`store/atlas.duckdb`.

---

## 2. The commands

The program has 9 commands. This section documents every one of them.

From this section onward, `python` means `.venv\Scripts\python.exe`, the interpreter that
section 1 makes, and `pythonw` means `.venv\Scripts\pythonw.exe` beside it. A system Python
on `PATH` does not have `duckdb` or `httpx`, so it stops with `ModuleNotFoundError`.

```
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
```

| Command | What it does | How long |
|---|---|---|
| `backfill` | It asks for every day from the first day of the source. Run it one time for each new source. `--redo-ok` also reads the days whose newest run row says `ok`, over the window that `--from` and `--to` name. That flag is the one repair for a part day, and it needs `--from`. It repaired 2026-09-18 on 2026-09-23, so it is proved against live publishers. | From the `run` table: energy-charts 2 h 23 min over 107 windows and 34 countries. NESO 13 min 24 s over 112 windows. RTE 5 min 44 s over 34. Energinet 4 min 54 s over 22. Elia 13 s and 12 s over 2 each. Every source together is about 2 h 47 min. One source and one day is about 3 s. |
| `daily` | It asks for the days with no `ok` row, and it always reads the last 2 days again. Then it exports. | Seconds, on a store that is current. |
| `snap` | It captures the forward forecast curve of each country, for every source that gives one. | 16.5 min for energy-charts and 34 countries. Seconds for NESO. |
| `export` | It writes `portal/data/*.json` again from the store. | About 5 s. The run of 2026-09-23 wrote 78 files and 10.9 MB. |
| `measure` | It prints what two publishers of one country say about the same hour. One line for each pair: the shared hours, the two means, the gap, the ratio and the correlation. The line also gives the share of days on which the two name the same cleanest hour. `atlas export` writes the same table to `portal/data/pairs.json`. `--country` limits the print to one country or more. | Seconds. |
| `status` | It prints what the store holds, and the failures. | Instant. |
| `verify` | It reads every raw payload again and compares it with the sha256 in the store. | Seconds for the 363 payloads that the store names on 2026-09-23. The tree holds 364; section 4 names the one that no `raw_ref` points at. |
| `rebuild` | It makes a new DuckDB file from `store/raw/` alone, in the directory that `--into` names. It makes no network request and it never writes `store/atlas.duckdb`. Section 4 gives the recipe and the limits. | 2 min 43 s for the 364 payloads on disk, and 2 min 3 s for the 223 payloads that a clone holds. Measured 2026-09-23. |
| `serve` | It gives `portal/` at `http://127.0.0.1:8765` and opens a browser. | It runs until you stop it. |

`backfill` and `daily` run the same code. The only difference is the question that they ask
the run table. Both restart with no loss. `--from` narrows the window that either one scans;
it cannot widen it, because both already start at the first day of the source.

An unknown `--source` id stops the command before it takes the lock, and it prints the list
of ids. `--country` without `--source` runs every source and skips the sources that do not
serve the code.

Exit codes: 0 is a success. 1 means that one or more days failed, or that a source stopped
with an unexpected error. 2 means that another process holds the store. 130 means that the
operator stopped it.

`rebuild` reads the same codes in its own way. It exits 0 when the walk found payloads and
every one of them parsed. It exits 1 when it skipped one or more, and also when it found none,
because an empty store is not a rebuild. So a script can test the exit code alone.

### A first run on a new machine

```
python -m atlas backfill --country DE   # 40 seconds, to test the path
python -m atlas backfill                # every source, about 2 h 47 min
python -m atlas snap                    # the forward curves, 16 minutes
python -m atlas export                  # write portal/data/*.json
python -m atlas serve                   # look at the result
```

`backfill` and `snap` do not export. Without the `export` step the portal opens with no data.

### A normal day

`atlas daily` does four things in one process:

1. For each source, it requests the days with no `ok` row, and the last 2 days again. The
   overlap catches a correction from the publisher.
2. It writes the payload to disk, parses it, and inserts the records.
3. It rebuilds the derived views.
4. It writes the JSON files that the portal reads.

There is no service, no queue and no state machine. The operating system starts one process.

---

## 3. The schedule

`ops/register-tasks.ps1` makes two Windows scheduled tasks.

| Task | Command | Time |
|---|---|---|
| `carbon-atlas daily` | `pythonw -m atlas daily` | 05:00 local, one time each day |
| `carbon-atlas snap` | `pythonw -m atlas snap` | 00:00 local, then every 6 hours |

Both times are local, and they move with summer time. The `ScheduledTasks` cmdlets give no
way to anchor a trigger to UTC. The interval of 6 hours is exact in every time zone, and the
absolute hours are not.

The script prints the UTC equivalent of both times for the host at
the end of the registration. Record those hours. They hold for this host only. A UTC hour
from another document can be wrong here.

Both tasks run `.venv\Scripts\pythonw.exe`, so no console window opens. The program writes to
`store/log/` and to the `run` table.

A laptop is a correct host, because a daily job tolerates a machine that sleeps. Five task
settings decide if the run happens, and `register-tasks.ps1` sets all five.

| Setting | Why |
|---|---|
| Start the task as soon as possible after a missed start | The laptop is asleep at 05:00. Without this setting, the run of that day does not happen. |
| Start the task on battery power | The default skips a run on battery, and a laptop is on battery for much of the day. |
| Do not stop the task on a change to battery power | The default stops a run in progress. |
| One instance only | A late run must not start beside the next run. The store gives write access to one process. |
| Stop the task after 2 hours | A request that hangs must not hold the store lock for ever. The dialog default is 3 days. |

Four of the five differ from the default dialog. The one-instance rule is already the
default, and the script states it so the definition is complete.

The script registers both tasks with the S4U logon type: they run with no user session, and
no password is kept. If the policy of the machine refuses S4U, the script registers the task
as Interactive and prints a warning. An Interactive task runs only while the user has a
session. Read the warning, and check the state at any time:

```
Get-ScheduledTask     -TaskName 'carbon-atlas *'        # the logon type of each task
Get-ScheduledTaskInfo -TaskName 'carbon-atlas daily'    # the last result and the next run
Start-ScheduledTask   -TaskName 'carbon-atlas daily'    # a test run now
```

### Confirm that the daily task really runs

⚠ A registered task is not a task that fires. No collection ran on 19, 20, 21 or 22 September
2026, and `ops/register-tasks.ps1` asks for one daily run and four snapshots each day. The `run`
table holds a `finished_at` on 2026-09-17, 2026-09-18 and 2026-09-23 only. The program reports
none of this, because a run that never starts writes no row.

Read the state of the task first:

```
Get-ScheduledTaskInfo -TaskName 'carbon-atlas daily'    # LastRunTime, LastTaskResult, NextRunTime
Get-ScheduledTask     -TaskName 'carbon-atlas *'        # State and the logon type
```

- `LastRunTime` more than one day before now says that the task did not fire.
- `LastTaskResult` 0 is a success. Any other value is the exit code of the last run.
- `State` must be `Ready`. A task in the state `Disabled` never fires.
- An Interactive task runs only while the user has a session. Section 3 gives the reason.
- `NextRunTime` empty is the mark of a task that will never fire again.

Then read `atlas status`. It gives no line for a run that did not happen, so read the dates and
not the failures:

| What to read in `atlas status` | What it says |
|---|---|
| The `to` column of each `actual` line | On a current store the newest `to` is today or yesterday. A `to` that stops on an older day, for every source at one time, says that no run landed data. |
| The `run rows` count | It does not grow while no run happens. Write it down each week. |
| The `failures:` block | It lists a day that failed. It lists no day that nobody asked for, so an absent run leaves this block exactly as it was. |
| The `to` column of each `forecast` line | See the next part. A stale forecast is the first symptom of a snapshot task that stopped. |

### A frozen part day, and the command that repairs it

⚠ A part day does not heal by itself. `atlas daily` reads the last `config.RECENT_DAYS` days
again, which is 2. `atlas backfill` reads a day again only when the newest run row of that day
says `fail` or `empty`. So no scheduled run asks for a day that holds an `ok` row and is older
than 2 days, whatever `--from` gives. An operator must ask for that day by hand.

That rule is the durable part, and it did not change. What changed on 2026-09-23 is that the
command for it is now proved end to end. `portal/data/health.json` states a hole as a date
range, so read the series and the day from there. Then give one command for that one source
and that one day, and export:

```
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source energinet-eds --country DK
python -m atlas export
```

Those two lines are the repair that ran on 2026-09-23, and the next part gives its result.
Change the date, the source id and the country code for another hole.

`--redo-ok` reads the days whose newest run row says `ok`, over the window that `--from` and
`--to` name. Always run `atlas export` after a repair. `backfill` writes no portal file, so
the portal keeps the old numbers until the export runs.

Scope the window to one source and one day. One command with no `--source` repairs the same
day for every series, and it then asks all 6 sources and the 34 collected energy-charts
countries. That is 39 requests for one day, and about 20 minutes at 2 requests each minute.

`--redo-ok` needs `--from`. Without it the command stops with exit code 1, before it takes the
lock, and it prints an example window. A re-read of the whole history is about 2 hours 47
minutes over the network. That is also a reason for a publisher to refuse the next request.

### The repair of 2026-09-18, and what it cost

The run of 2026-09-18 stopped part way through that day and wrote an `ok` row for it. That day
then held 132 of 288 stamps for `energinet-eds` DK, 20 of 48 for `neso-carbon-intensity` GB
and 40 of 96 for `rte-eco2mix-odre` FR. 240 records were absent. The owner ran one command for
each of the 3 frozen series on 2026-09-23:

```
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source energinet-eds --country DK
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source neso-carbon-intensity --country GB
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source rte-eco2mix-odre --country FR
python -m atlas export
```

The three backfills took about 10 seconds and 3 requests together. Energinet DK gave 156 new
records, NESO GB 28 new records and 12 revisions, and RTE FR 56 new records. That is 240 new
records, which is the count that the gap analysis predicted. `atlas export` then wrote 78
files. The test suite grew on the same day. It holds 337 checks in 23 sections, and all 337
pass.

2026-09-18 now holds 288 of 288 for Energinet DK, 48 of 48 for NESO GB and 96 of 96 for RTE
FR. All three series are complete for that day. A daily mean of 2026-09-18 from those three
sources is the mean of a whole day again.

The same flag reaches the smaller frozen days. `energy-charts-co2eq` GB 2026-09-14 holds 44
stamps of 48, and LT 2026-09-15 holds 87 of 96. `REFERENCE.md` §2 holds those counts, the six
countries that freeze 2026-09-22 tomorrow, and the shortfall figures that the repair moved.

### The forecast layer goes stale, and nothing says so

`atlas snap` captures the forward curve that a publisher gives at that moment. A curve is good
for its horizon only. The program writes no warning when the horizon passes, and no command
fails. The Forecast tab and `portal/data/forecast.json` then draw a curve that stopped before
the hour on screen.

This happened. Before the snapshot of 2026-09-23 the newest energy-charts capture held `run_at`
2026-09-17 12:44 UTC. The newest NESO capture held `run_at` 2026-09-18 10:19 UTC. The newest
forecast timestamp in the store was 2026-09-20 13:00 UTC. All 1,891 forecast rows were then in
the past.

Check it in `atlas status`. Each `forecast` line gives a `to` column. It holds the date of the
last hour of the newest curve of that country, and it must be after today.

- A `to` of today or of an older date says that the layer is expired.
- Compare it with the `to` of the `actual` line of the same country. A forecast that stops
  before the measurement gives a scheduler nothing.
- The `rows` count of the `forecast` line does not grow while the snapshot task does not fire.

To repair it:

```
python -m atlas snap      # capture the curves again, about 16.5 min for energy-charts
python -m atlas export    # write portal/data/forecast.json again
```

### What a missed run costs

| Missed | Cost |
|---|---|
| A day of measurement collection | Nothing, while the day holds no `ok` row. The publishers keep their own history, and the next run asks for that day and gets it. |
| A run that started and did not finish | The part of the day that it did not reach. The day holds an `ok` row, so no scheduled run asks for it again after 2 days. Only `atlas backfill --redo-ok` reads it, and an operator must give that command. See the part above. |
| A forecast snapshot | The curve of that hour, for ever. energy-charts keeps no forecast history. |
| Every snapshot of a signed-out window | The curve of each of those hours. This is what an Interactive task costs, so check the logon type. |
| A day of a source with a live window | Electricity Maps is in the register and has no collector yet. When one is written, a missed day is lost, because the free plan serves the last 24 hours only. |

⚠ A missed forecast snapshot is a hole and not a delay. The program records `run_at` from
the clock, and not from the schedule. A snapshot that starts at 07:20 after the machine
wakes gives an exact horizon for 07:20. The lead set of that day is less regular, and the
rows are correct.

### The two tasks and one store

The one-instance rule protects each task from itself only. `daily` and `snap` are two tasks
and one store, and both carry "start as soon as possible after a missed start". A laptop
that wakes can fire both missed runs together. The second one waits 10 minutes for the lock
and then exits with code 2. The cost is one skipped run: the next `daily` asks for the day
again, but a skipped `snap` loses its curve. Keep the first snapshot time away from 05:00.

---

## 4. The store on disk

```
store/
  atlas.duckdb                                377 MB   three tables, one view
  raw/<source>/<yyyy-mm>/<ts>-<ISO>.json.gz   47.7 MB   the payloads. A snapshot adds -snap.
  log/                                                 one log for each run
  atlas.lock                                           it exists only while a writer runs
  tmp/                                                 the CSV files of the bulk load
```

A raw file name carries the collection timestamp and the country. The sha256 is in the
`raw_ref` column of the `record` row, and not in the file name.

That tree is what the code writes today. The 37 snapshot payloads on disk are somewhere else.
Older code gave a snapshot a directory of its own and a plain file name. So they sit in
`store/raw/energy-charts-co2eq-snap/` and `store/raw/neso-carbon-intensity-snap/`.
`atlas verify` reads the path that the `raw_ref` holds, so it finds both forms.

⚠ Back up `store/raw/` first. It is the part that nobody can make again. `atlas rebuild`
turns those payloads into a DuckDB file in about 3 minutes, and no publisher serves the
periods that now answer HTTP 500. Back up `store/atlas.duckdb` with it, because a rebuilt
store is not the collected store: it holds no failed day and no snapshot `run_at`. The next
part states every limit.

`portal/data/` needs no backup. `atlas export` writes it again in about 5 seconds.

### Rebuild the store from the payloads

```
python -m atlas rebuild --into ..\atlas-store            # the whole tree
python -m atlas rebuild --into ..\atlas-de --source energy-charts-co2eq
```

The command walks `store/raw/` and checks the sha256 of each payload. Then it parses each
payload again, through the collector that wrote it, and writes the records into a new DuckDB
file at `<dir>/atlas.duckdb`. It makes no network request.

`--source` limits the walk to one source id, and it covers the older `<id>-snap` directory of
that source too.

⚠ `--from` and `--to` count the collection date from the file name, and not the date of the
data inside the file. Every payload in the tree arrived in September 2026, and the records in
them start in 2011. So `--from 2015-06-01` selects nothing. Use the two flags to rebuild one
collection day.

Where the new store lands, and what it refuses:

- `--into` is required. The command writes `atlas.duckdb` in the directory it names, and it
  makes the directory if it is absent.
- It refuses a directory that already holds an `atlas.duckdb`. It never writes over a store.
- It refuses a target that resolves to the live `store/atlas.duckdb`.
- It refuses a target inside `store/raw/`. That tree holds the licensed payloads.
- All three refusals happen before the command opens anything.

It does write three other things under `store/`, and an operator must know about them. It
takes `store/atlas.lock` for the length of the run, so a `daily` or a `snap` cannot add a
payload while the walk reads the tree. It writes and removes one CSV in `store/tmp/` for each
bulk load. And it opens the live store read only, to read the expected hashes.

To use the new store, point `ATLAS_STORE` at its directory:

```
set ATLAS_STORE=..\atlas-store          # PowerShell: $env:ATLAS_STORE = '..\atlas-store'
python -m atlas export
python -m atlas serve
```

Remove `ATLAS_STORE` before the next rebuild. `rebuild` reads the payloads under the store
that the variable names, so a second rebuild with it set walks `..\atlas-store\raw\`, which
holds nothing. The command then stops with "nothing to rebuild" and exit code 1.

`atlas verify` against a rebuilt store needs a `raw/` tree beside the new `atlas.duckdb`. A
`raw_ref` is relative to the store directory, so a rebuilt store with no `raw/` beside it
reports every payload as ABSENT. `atlas verify` against a store rebuilt from the 223 licensed
payloads reads 206 of them and reports `ok 206  absent 0  changed 0`. The other 17 are the CY,
GE, MD and XK payloads that hold no value for the days they cover. No `raw_ref` names them, so
`verify` does not read them.

The command prints which hash check it ran. With the live store present, it compares each
payload against the sha256 that the store recorded at collection time. That is a second number
and it does not come from the file. With no live store, as in a clone, the command can only
make the hash again from the bytes.

⚠ That second mode is self-consistent and it proves nothing about tampering. It still catches
a truncated file, because gzip carries a CRC32 and the read fails. The repository ships no
checksum manifest.

Then it prints the summary: the payload count, the parsed count, the record count with the
revision count, and the run-row count. After that it gives one line for each payload it
skipped, with the reason. A payload that fails its hash is reported and skipped. A payload
that fails to parse is reported and skipped. Neither stops the run. Exit code 0 says that
every payload parsed.

The full run of 2026-09-23 read 364 payloads, parsed 364, skipped 0, and wrote 6,590,611
records with 470 revisions and 147,700 run rows. It took 2 min 43 s and made a file of 389 MB
against the 377 MB of the live one.

### What a rebuild does not reproduce

`atlas/rebuild.py` sections 3 and 4 hold the full contract. These are the parts that change a
number on a page. All of them were measured on 2026-09-23, against the live store of that day.

| Part | The live store | A rebuild | What it costs |
|---|---|---|---|
| The actual series | 6,586,295 rows | 6,586,289 rows | 6 rows. See below. Every one of the 6,586,289 joined rows holds the same value, unit, basis, scope, granularity and zones. |
| `collected_at` and `raw_ref` | one payload | another payload | 659,826 rows, which is 10.0 %, name a different payload. The value is equal in all of them. Payload windows overlap, and `Store.insert_records` writes no row for an equal value, so the first payload that carries a value keeps the reference. A `raw_ref` names one file that holds the evidence, and not the only one. |
| The `run` table | 192,974 rows, 45,787 `fail` and 9,434 `empty` | 147,700 rows, 0 `fail` and 8 `empty` | A failed request wrote no payload, so the walk finds nothing to rebuild it from. `health.json` then reads `days_fail` 0 and `days_empty` 8, against 6,990 and 9,432. `atlas status` prints no failure block. ⚠ That is not a claim that nothing failed. |
| `http_status` | a code in every collection row | NULL in every row | A row with a `raw_ref` and no `http_status` came from a rebuild. |
| The forecast `run_at` | 6 values | 63 values | `runner.snap_forecasts` gives one clock instant to every country of a snapshot pass. A rebuild has only the collection time of each file. ⚠ The Forecast tab then counts 61 energy-charts runs where the live store counts 4. |
| The forecast series | 3,695 rows | 3,852 rows | It gets larger, and not smaller. 21 points go to a negative horizon, and 178 arrive for Lithuania alone, because 3 payloads of one snapshot pass become 3 curves. 15 countries lose their first forecast point. |
| The revision history | 466 rows at revision 2, 4 at revision 3 | the same | Nothing. The corrections that a publisher made survive a rebuild. |

⚠ The 6 absent rows are the 6 NESO GB rows that hold 0.0. `zero_guard()` in
`atlas/collectors/base.py` drops a 0.0 today, and it dropped none when those 3 payloads
arrived on 2026-09-18. A rebuild runs the parser of today on the bytes of the collection day.
Read a difference of this shape as a change of the program, and not as a change of the data.
`REFERENCE.md` §2 holds the 6 timestamps.

The rebuilt store marks itself. Its `meta` table carries `rebuilt_at`, `rebuilt_from`,
`rebuilt_payloads` and `rebuilt_note`.

### The payload that no record names

`store/raw/energy-charts-co2eq/2026-09/20260917T102215Z-DE.json.gz` is on disk, and the live
store names it in 0 record rows and 0 run rows. The live `run` table jumps from 10:20:49 to
10:36:09 for DE on that day. So the tree holds 364 payloads and `atlas verify` reads the 363
that the store names. A reader who subtracts the two counts finds this one file.

The rebuild parses it first, and it becomes the `raw_ref` of 395,424 DE rows. The values are
equal to the live ones. It is an energy-charts file, so it raises no licence question. The
owner decides to keep it or to remove it.

### Size, and how it grows

Measured on 2026-09-23, with 6 source ids in the store. Every size is decimal MB.

| Part | Now | Growth |
|---|---|---|
| `atlas.duckdb`, 6.59 M current rows | 377 MB | About 1.2 M rows each year for energy-charts. |
| `raw/energy-charts-co2eq` | 25.2 MB | A few MB each day. |
| `raw/energinet-eds` | 14.1 MB | DK gives one value every 5 minutes, for 2 price areas. |
| `raw/rte-eco2mix-odre` | 6.4 MB | Two datasets in one payload. |
| `raw/neso-carbon-intensity` | 1.7 MB | GB gives one value every 30 minutes. |
| `raw/elia-co2-production` and `raw/elia-co2-consumption` | 183 kB each | BE gives one value each hour. The two ids ask the same dataset, so the two directories hold the same bytes. |
| The two `-snap` directories of the older code | 36 kB | The 37 forecast curves, about 1 kB each. |
| The raw files together | 47.7 MB over 364 files | The evidence for every row, and the input of `atlas rebuild`. `atlas verify` reads the 363 that the store names, and on 2026-09-23 it found 0 changed and 0 absent. The part above names the 364th. 223 of the 364 files are in this repository, and 141 are not; `LICENSE-DATA.md` gives the reason. |
| The generation mix, when it is collected | not collected | About 740,000 rows for one country and one year. |

A full mix backfill is 1 to 2 GB. That size is acceptable on one machine. If it is not,
materialise 3 years and keep all the raw files.

---

## 5. One writer at a time

DuckDB gives the file to one process. That rule holds for a reader too.

- `backfill`, `daily`, `snap`, `export` and `rebuild` take `store/atlas.lock`. A second writer
  waits, and it stops after 10 minutes with the name and the process number of the holder.
  `rebuild` writes its own store somewhere else, and it still takes the lock. The lock stops a
  `daily` or a `snap` from adding a payload while the walk reads the tree.
- `atlas status`, `atlas verify` and `atlas measure` open the store read-only, and they still
  fail while a writer runs. The message gives the path of the store and the DuckDB error, and
  the exit code is 2. It gives no process number, because a reader never takes the lock.

  `measure` opens the store in the same way as `status`, and section 9 of `REFERENCE.md`
  measured that open as a failure under a writer. A test of 2026-09-23 on a scratch DuckDB
  file gave the same result: a read-only open fails while another process holds the file.
  The docstring of `cmd_measure` in `atlas/__main__.py` says so since that day. Do not plan
  a run of `measure` inside the window of `atlas daily`.
- A stale lock from a process that died is detected and removed. `atlas/lock.py` asks the
  operating system if the process id lives: `os.kill(pid, 0)` on POSIX, `OpenProcess` on
  Windows.
- A lock file with no readable process id counts as held for the first 60 seconds. A live
  holder makes the file one step before it writes the body, and a waiter must not remove it
  in that moment.

The lock is the only concurrency rule inside the program. It does not order the two
scheduled tasks; see section 3.

---

## 6. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ATLAS_STORE` | `carbon-atlas/store` | Where the store is. The tests set it to a temporary directory. |
| `ATLAS_CA_BUNDLE` | empty | The path of the CA file of a proxy. |

TLS is always on. `httpx` verifies `api.energy-charts.info` with the certifi bundle. The
program has no switch to turn the verification off. A machine behind a proxy that signs its
own certificates sets `ATLAS_CA_BUNDLE` to the path of the CA file.

---

## 7. Troubleshooting

| What you see | What it is | What to do |
|---|---|---|
| `... is open in another process. DuckDB gives the file to one process.` (exit 2) | Any command, `atlas status` included, found the DuckDB file open. Another run holds it. | Wait for that run to end, then run the command again. A full backfill takes about 2 h 47 min. |
| `atlas backfill (pid NNNN) holds the store lock. The wait of 600 s ran out.` (exit 2) | A second writer waited the full 10 minutes. | Wait for the first run to end. A backfill is longer than the 600 s limit, so do not start a second writer during one. If no process runs, the lock file is stale and the next command removes it. |
| The portal page shows a red bar about an address | The page was opened from the disk. A browser refuses to read a data file beside it. | Run `python -m atlas serve` and open the address it prints. |
| The portal shows old numbers | The export did not run. | Run `python -m atlas export`. |
| A country is grey on the tile map | It has no record at the hour on screen. | Move the hour control back. See `REFERENCE.md` §2. |
| `atlas daily` exits with 1 | One or more days failed, or one source stopped with an unexpected error. | Run `atlas status`. It lists the failures with the error text. The log names a source that stopped. |
| Many `fail` days for one country | The publisher answers HTTP 500 for that period. | Nothing. The runner splits the window and keeps the good years. `daily` retries only the last 30 days. |
| `atlas status` gives the same `to` date for every source on two days one after the other | The daily task did not fire. A run that never starts writes no row, so no command fails and the failure list does not change. | Read section 3, "Confirm that the daily task really runs". |
| `health.json` gives a hole inside a day, and the run row of that day says `ok` | A run stopped part way through the day and froze it. No scheduled run reads that day again after 2 days. | `python -m atlas backfill --redo-ok --from <day> --to <day> --source <id> --country <ISO>`, then `python -m atlas export`. Section 3 gives the measured cost. |
| The Forecast tab draws a curve that stops before now | No `snap` ran inside the horizon of the last capture. Nothing warns about this. | `python -m atlas snap`, then `python -m atlas export`. Section 3. |
| `no store at ...` (exit 1) | No backfill has run. `status`, `verify` and `export` all stop with this line. | `python -m atlas backfill`. |
| `no record in the store at ...` (exit 1) | `atlas export` found a store that holds the schema and no record row. A backfill did not finish. | `python -m atlas backfill`. The export wrote nothing, so the files of the last good export are still in place. |
| Some of the 78 files in `portal/data/` differ after two exports, and no new data arrived. 39 of 75 differed when this was measured on 2026-09-22 | `atlas export` is not reproducible byte for byte. DuckDB sums in parallel, so the order of the sum moves by about 4e-5, and the round to 2 decimals then flips. | Nothing. Each difference is one unit in the last decimal, such as 270.97 or 270.98 for one row of `daily/AT.json`. It changes no result. |
| The DuckDB file is damaged or deleted | The payloads are still there, and `atlas rebuild` parses them again. | `python -m atlas rebuild --into <dir>`, about 3 minutes, then point `ATLAS_STORE` at that directory. Section 4 states what a rebuilt store does not hold: no failed day, no snapshot `run_at`. Restore from a backup if you need those. `atlas backfill` is the last choice, and it cannot bring back the periods that now answer HTTP 500. |
| `--into <dir> is the live store`, or `is already there`, or `is inside <raw dir>` (exit 1) | One of the three refusals of `atlas rebuild`. The command does not write over a store and does not write inside `store/raw/`. | Name an empty directory outside `store/`. |
| `nothing to rebuild. Check --source, --from and --to.` (exit 1) | The walk of `atlas rebuild` selected no payload. | `--from` and `--to` count the collection date, and every payload arrived in September 2026. Run the command with no window. |
| `duplicates` is not 0 in `atlas status` | The `record` table holds a key two times at one revision. | Read `REFERENCE.md` §4. Every row count above that line is too large. |

### What `atlas status` tells you

It prints the row counts first, and with them a `duplicates` count that must be 0. Then one
line for each source, country and kind, with the row count and the stored range. Then the
failures, with their error text. Run it first for any question about coverage.

It gives no line for a day that nobody asked for, and no line for a forecast layer that
expired. Both are silent, and section 3 gives the check for each one.

---

## 8. The portal

```
python -m atlas export      # write portal/data/*.json from the store
python -m atlas serve       # http://127.0.0.1:8765
```

`serve` uses the standard library and reads `portal/` only. It makes no network request.
Add `--port <n>` if 8765 is taken, and `--no-browser` to stop it from opening a browser.

The server answers more than one request at a time, because the page asks for 10 data files
together. It also sends `Cache-Control: no-store`, so a browser always gets the files of the last
export.

`portal/README.md` gives the tabs, the data contract and the two rules that the data forced.

---

## 9. Adding a country or a source

A country is a line in `sources/zones.json` and a code in the per-source map. Never
hard-code a country list anywhere else. The collector reads the register.

A source is one module in `atlas/collectors/` with `fetch` and `parse`, plus an entry in
`sources/sources.json`. That entry is the single definition of the source: the URL, the rate
limit, the licence, the basis and the risks. Never hard-code a URL anywhere else.

`REFERENCE.md` §6 gives the collector contract and the four guards.
Five modules are written, they give six collectors, and each one answers a different problem:

| Module | Shape of the problem |
|---|---|
| `energy_charts_co2eq.py` | One request for one country and the whole history. The plainest case. |
| `neso_carbon_intensity.py` | The window goes in the path. One payload holds the measurement and the forecast in two columns. |
| `rte_eco2mix_odre.py` | Two datasets make one series. The newest one wins a timestamp that both hold. |
| `energinet_eds.py` | Two price areas make one country value, weighted by the load of the same hour. |
| `elia_opendata.py` | One dataset holds two accounting bases. One module gives two collectors and two source ids, because `basis` is not in the key of the record table. The module also drops a published 0.0, which is an outage of the publisher and not a clean hour. |

A module can give more than one source id. `atlas/collectors/__init__.py` maps a source
id to a collector object, and `elia_opendata.py` gives two objects. A new entry in
`sources/sources.json` is necessary for each id.

After a new collector:

```
python -m atlas backfill --source <id>
python -m atlas export
```

Those two commands do not publish the new source. `.gitignore` denies every directory under
`store/raw/` and allows one source with one line. So the payloads of the new source stay on
disk and out of the repository. To publish them, read the reuse terms of the publisher, record
them in `sources/sources.json` and in `NOTICE.md`, then add one `!store/raw/<id>/` line. That
order is deliberate: a source is private until a person states its terms.
