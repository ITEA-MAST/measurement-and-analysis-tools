# Reference

What a person must know to use the data correctly. `RUNNING.md` says how to operate the
program. `ARCHITECTURE.md` says why the parts are separate.

Read section 1 and section 2 before you quote any number from this system.

---

## 1. How to read a number

### The unit, the basis and the scope are properties of the source

⚠ The store holds two units, and they are not the same quantity. The `unit` column holds
the one of each row, so an analysis step cannot confuse them in silence. The portal takes
the unit of the selected source, and it never prints one unit above another source's number.

Two export files state a unit, and no other one does. `meta.json` gives one for each source,
and one for each country and source pair. `pairs.json` gives `unit_a` and `unit_b` for each
pair of sources, and it reads both from the stored rows. Its `same_unit` field is false for 3
of the 6 pairs of 2026-09-23. Those three compare gCO₂/kWh against gCO₂eq/kWh. `basis_a`,
`basis_b` and `same_basis` do the same for the accounting basis, and `same_basis` is false for
all 6.

| Source | Countries | Unit | Basis | Scope | What the publisher states |
|---|---|---|---|---|---|
| energy-charts `/co2eq` | 33 | gCO₂eq/kWh | production-based (inferred) | lifecycle (inferred) | Nothing. Both are read from the endpoint name, and neither is documented. |
| NESO | GB | gCO₂/kWh | consumption-inclusive | direct combustion, not lifecycle | A published methodology and a published factor table. |
| RTE through ODRE | FR | gCO₂/kWh | production-based | not stated | "Estimation des émissions de carbone générées par la production d'électricité en France." |
| Energinet | DK | gCO₂/kWh | consumption-based | not stated | "the CO2 emission from electricity consumed in Denmark measured in g/kWh". |
| Elia `ods192` production | BE | gCO₂eq/kWh | production-based | not stated | "…per unit of generated electricity… Cross-border flows are not taken into account." |
| Elia `ods192` consumption | BE | gCO₂eq/kWh | consumption-based | not stated | "…per unit of consumed electricity… Cross-border flows are taken into account." |

Three of the six say CO₂, and three say CO₂eq. A CO₂ number counts no methane and no
other greenhouse gas. So it is below a CO₂eq number of the same hour, before any other
difference. This program converts nothing, and it never mixes two sources into one value.

The two Elia rows are one publisher, one dataset and one request. They are two source
ids because `basis` is not in the key of the record table. Two values of one hour under one id
collide, and the store writes the second one as a revision of the first, which is false. They
are also the only pair in the store that changes the basis alone. The publisher, the unit, the
scope and the factor table stay constant. Section 9c measures what that separates.

⚠ A number from another basis is not a check of this one. Section 9b and section 9c
measure the size of the disagreement, and it is large.

### Every mean is a time mean

A daily, monthly or hourly mean in this system is the mean of the readings in that period.
It is not weighted by the load.

A time mean answers "what was the mean intensity of the day". The carbon of a day of work
needs the load-weighted mean, because work does not use the same power in each hour.
The two differ most in a country with a large solar share.

The export names the field `mean_unweighted` for this reason. No panel can use it by
mistake. The load series arrives with `/public_power`. See section 10.

The workload calculator in the portal is not affected. It multiplies the energy of each
hour by the intensity of that hour, so it needs no weighted mean.

### The time is UTC

`ts_utc` is UTC. The portal hour control is UTC. The month-by-hour grid is UTC.

⚠ The publishers count a day in local time. So a request for one UTC day gives a short
day. The collector adds one day at each end of the request, and then keeps the UTC
timestamps. A reader of the grid must remember the offset. A country 2 hours ahead of UTC
has its midday solar dip near 10:00 in the grid.

### How the value reached the country

Every row carries a `granularity` tag. It says what the source did.

| Tag | Meaning |
|---|---|
| `native` | The source reports this exact country. No transformation. |
| `aggregated` | The source reports smaller zones. The country value is a load-weighted roll-up. |
| `group` | One reading covers several countries, and it is copied to each one. It is not a measurement of the country. |
| `proxy` | A value borrowed from a different area. The last resort. It carries a written reason. |

⚠ Two countries with a `group` value are not independent. Germany and Luxembourg share
one ENTSO-E reading (`DE-LU`), so a comparison of the two measures nothing. The portal shows
them in one row and states the group.

Most rows are `native`. The exception is Energinet. The Danish country value is `aggregated`
from DK1 and DK2. The weight is the gross consumption of each area in the same hour.
`meta.json` carries the tag of each country and source, and the portal reads it. See section
9b and `SOURCES.md` §9.

### A gap is a gap

The program never fills a hole. It has no interpolation, no carry-forward and no fallback to
another source.

1. A missing measurement shows "no record". The portal never shows a value from another hour
   or another country in its place.
2. A forecast is never a fallback for a missing measurement. The two are different data
   and they stay in different rows.

⚠ The strongest case for this rule is a hole that looks free to fill. Measured on
2026-09-23: energy-charts GB holds nothing from 2021-06-15 to 2022-01-26, which is 226 days,
and NESO covers the whole of that window. So a patch from NESO looks like a repair. It is
not one.

The two sources share 78,891 timestamps. Across them NESO gives 142.7 g and energy-charts
gives 245.8 g, so the two levels differ by 103 g. A patched GB series takes a step of 103 g
into the hole and another step out of it. That step is larger than the effect this system
measures. Section 2 holds the rest of the measurement.

### A correction makes a revision, and never an overwrite

A publisher can restate a recent value. A measured example: a second read of the last 2
days, 10 seconds after the first, gave 4 changes, such as 309.1 → 308.8.

A publisher also restates a settled day. The repair of 2026-09-23 read 2026-09-18 again at
NESO, 5 days after the first read of that day, and 12 values came back changed. So a re-read
of an old day corrects the record and fills a hole. Section 2 gives that repair.
Nobody had this measurement before 2026-09-23.

The store writes a new row with `revision` + 1. It never runs an `UPDATE`. The
`record_current` view gives the newest revision. Both numbers stay, so a past report can be
reproduced.

---

## 2. Known defects in the data

These are properties of the publisher, and of what the collection does with them. Each one is
measured and dated. One of them is the collection alone: the 2-day window that freezes a hole
inside a day. That window is still in the code, and an operator repaired its largest victim on
2026-09-23. The two subsections on the frozen day hold the mechanism and the repair.

### The store is short by 3.22 % of the records that it must hold

Measured on 2026-09-23, after the repair of 2026-09-18 that a later subsection records, across
the 39 series of measurements. A series is one source and one country. energy-charts gives 34
of them, and Energinet DK, NESO GB, RTE FR and the 2 Elia series of Belgium give 5 more.

The store holds 6,586,295 records. The expected count is 6,805,636, so 219,341 records are
absent, which is 3.22 %. That expected count takes the step from the data itself, day by day,
from the modal interval between one timestamp and the next one.
`portal/data/health.json` computes the same model in code and gives 6,805,707 expected and
219,460 absent, which is 3.22 % as well.

The repair of 2026-09-18 moved this figure on 2026-09-23. Before it the store held 6,586,007
records and 219,629 were absent, which is 3.23 %. Every figure of this subsection is of the
store after the repair.

⚠ A fixed step for each country gives 35.35 % instead, and that figure is an artefact. 14
series changed their step inside their own span, and a fixed step reads the change as
absence. The fixed step calls DK, EE, FR, IT, LT, NO and SE about 70 % short, and those 7
series are complete.

The measured dates of the change:

- NL 2016-01-03
- RO 2022-01-02
- ES 2023-01-01
- FI 2023-12-31
- CZ, HR and PL 2024-12-29
- DK, EE, FR, IT, LT, NO and SE 2025-12-28
- RTE FR 2026-06-30

3.22 % is the right number. A reader who takes one step from `sources/sources.json` and
divides computes 35.35 % first. So always say which of the two models gave a shortfall.

The absence is not spread evenly across the series.

| Series | Records held | Records absent | Absent share of its own span |
|---|---|---|---|
| energy-charts CY | 27,925 | 166,509 | 85.64 % |
| energy-charts ME | 83,124 | 15,873 | 16.03 % |
| energy-charts GB | 184,994 | 13,348 | 6.73 % |
| energy-charts GE | 28,981 | 12,590 | 30.28 % |
| the other 35 series together | — | 11,021 | — |

CY, ME and GE hold 194,972 of the 219,341 absent records, which is 88.9 %. Add energy-charts
GB and those 4 series hold 95.0 %. 24 of the 39 series are short by fewer than 100 records,
and AT, BE, DE, MD and PT are complete inside their own span.

The repair of 2026-09-18 took all 240 of its records from the last row of the table. The four
large series did not change. Before the repair that row read 11,293, and the two shares read
88.8 % and 94.9 %.

⚠ The CY row of `portal/data/health.json` gives 167,037 absent and not 166,509. The 528
records of the difference are one choice: which step applies inside the hole of 3,360 days,
in which the publisher held nothing. The table above takes 60 minutes there, and the code
carries the last observed step of 30 minutes forward. The true step of a period with no data
is not knowable. Every other large series agrees to the record.

### Georgia sits at a floor of 3.0 gCO₂eq/kWh

8 months, from 2022-05 to 2024-07, hold 665 to 744 records each. That is 89 % to 100 % of the
hours of the month, so some of the 8 are part months. Each one holds a mean below 8 g and a
minimum of exactly 3.0 g. The season panel shows a swing of 80.8× across the months of
Georgia.

The floor is now counted. Measured on 2026-09-23: 2,254 of the 28,975 Georgian records sit at
exactly 3.0 g, which is 7.8 %, and 27.9 % sit at or below 5.0 g. The first of the 3.0 values
is 2022-04-04 20:00 and the last one is 2025-04-17 20:00. The 723 records of the window that
opened on 2026-08-23 hold no 3.0 value at all, so the floor stopped when the publisher came
back. The older records keep it.

IPCC AR5 Annex III puts the lifecycle median of hydro near 24 gCO₂eq/kWh, so no national grid
reaches 3 g under that table. The next lowest month from energy-charts, the same publisher and
the same unit, is CH at 10.9 g. RTE reports French months as low as 8.5 gCO₂/kWh. That is
another publisher, another unit and another basis, so it does not rank against these two.

The four guards do not catch this. 3.0 g is inside the store band, and the step, the field set
and the count are all correct. A check on a repeated identical minimum can find it, and the
program has none today. A second source scores it directly. Do not quote a Georgian
number. See `SOURCES.md` §1.1.

### The time change costs 416 records, and most of them fall in autumn

Measured on 2026-09-23. 416 records are absent on 117 country-days at the European clock
change. 327 of them fall on 80 autumn days, and 89 fall on 37 spring days. So the absence is
an autumn defect first.

| Series | Records absent | Where they fall |
|---|---|---|
| Energinet DK | 119 autumn, 12 spring | 12 stamps on every last Sunday of October since 2017, and 12 on 2026-03-29 |
| energy-charts LU | 92 autumn | all on 2023-10-29, a day that holds 4 records of 96 |
| RTE FR | 28 autumn, 4 spring | 2 half hours on every autumn Sunday since 2012 |
| energy-charts GB | 20 autumn, 7 spring | — |
| energy-charts GR | 18 spring | 2 hours on 9 of the 10 spring Sundays |
| NESO GB | 16 spring | all on 2019-03-31 |
| energy-charts BA | 12 autumn, 10 spring | — |
| energy-charts EE | 12 spring | 3 hours on 4 spring Sundays |

The spring hour breaks two publishers in a second way, and that fault costs one instant each
year and not a block of records. Measured on 2026-09-18, the day the store went from one
source to six. The hour when the clock moves forward is the one hour of the year that these
two publishers handle badly.

| Publisher | What it returns | What the program does |
|---|---|---|
| RTE | One UTC instant, two rows, with the local labels 02:00 and 03:00. From 2020 the two numbers are equal. In 2013 to 2019 they differ, for example 25 and 27 on 2019-03-31. | Equal numbers give one record. Different numbers give none, and the run row names both. One instant each year is lost. |
| Energinet | 12 negative values for DK1 on 2026-03-29, from 01:00 to 01:55 UTC, down to −321 gCO₂/kWh. | Guard 2 drops each point and names it in the run row. The day stays. |

A number from that hour is worth nothing in either series. NESO carries its own
defect, and it is not at the time change: `2021-04-19T19:00Z` came back two times with
`actual` 303 and 295. energy-charts carries small negatives for Lithuania, in the forward
curve only, and they are in the forecast subsection below.

### Elia writes 0.0 for an hour that it did not compute

Measured on 2026-09-18 across the whole Belgian series of 15,279 hours. 326 rows carry 0.0 in
one column or both, and 284 carry 0.0 in `production`.

The zeros come in blocks. The blocks repeat at 18:00 to 21:00 UTC on days that follow
each other, which is a fixed local evening window. Three measurements say that a zero is not
a measurement:

1. energy-charts gives a mean of 218.5 gCO₂eq/kWh for those same 284 hours, and never
   below 82.4.
2. The energy-charts mean across the whole period is 203.9, so the zero hours are dirtier
   than the mean and not cleaner.
3. The smallest value that Elia gives above zero is 17.4 gCO₂eq/kWh.

⚠ This defect is worse than a gap. Guard 2 accepts 0.0, because `INTENSITY_MIN` is 0.0
and a true zero is possible for another country. A gap shows as "no record". A zero becomes
the cleanest hour of the day, in the hours when the grid is dirtiest. It then moves the answer
of the workload calculator to the wrong hour.

The Elia collector drops every zero and names it in the run row. It stops the payload only
above a share of half. Half means the publisher changed the format.

The defect is live, and it grew. Measured on 2026-09-23: production now holds 335 absent
hours inside days that hold data, and consumption holds 377, against 284 and 326 on
2026-09-18. This morning's run dropped 16 points on each series, and the 16 are one block,
18:00 to 21:00 UTC on 2026-09-18, 19, 20 and 21. Every production gap is also a consumption
gap.

The drop is right for the hour, and it moves the mean of the day down. The block takes the
evening peak, which holds the dirtiest hours. energy-charts holds all 335 hours and gives
218.8 gCO₂eq/kWh across them, against 204.1 g across the whole Elia span.

Over 2026-09-14 to 2026-09-22 an Elia daily mean covers 18 or 20 hours of 24. On those same
hours energy-charts sits 4 to 48 g below its own 24-hour mean. The median of that difference
is near 20 g, and the worst day is 47.5 g on 2026-09-20. So a Belgian daily mean from Elia
reads low by about 20 g while the block continues.

### 6 records hold 0.0, and all 6 are NESO GB

Measured on 2026-09-23. 6 rows of the whole store hold the value 0.0: `2023-01-31T01:00Z`,
then 09:30, 10:00, 10:30 and 11:00 on 2023-06-07, then `2026-08-06T11:00Z`. Every one of them
is `neso-carbon-intensity` GB. They are the 6 lowest values of the 6.59 million rows, and the
next value above them is 3.0 g. The reasoning of the Elia subsection above holds here too. A
panel that picks the cleanest half hour of a day, a month or a year picks one of these 6.

The guard on the parse path stops the next zero. `atlas/collectors/base.py` holds
`zero_guard()` and `check_zero_share()`, and `neso_carbon_intensity.py` calls both, for the
`actual` column and for the `forecast` column. `elia_opendata.py` keeps its own copy of the
rule. The other 3 collectors call neither, and no 0.0 record from those 3 is in the store.

The guard cannot remove these 6. A dropped point writes no row, and the store never runs an
`UPDATE`, so `record_current` keeps a stored 0.0 whatever a later run does. A query that
ranks GB by the lowest value must exclude 0.0.

⚠ A rebuilt store holds none of the 6. `atlas rebuild` runs the parser of today on the bytes
of the collection day. The guard is newer than the 3 payloads of 2026-09-18 that carry those
points. So a rebuild of the whole tree gives 6,586,289 actual rows against the 6,586,295 of
the live store. That difference is a change of the program and not of the data, and it is the
only row-count difference in the actual series. `RUNNING.md` §4.

### The Belgian series is short, and it has a hole of 70 days

Measured on 2026-09-18. The Elia export holds 15,279 of the 17,204 hours between the first
and the last record. The store keeps 14,995 production rows and 14,953 consumption rows,
because the collector drops the zeros above. The largest hole runs 70 days, from
2025-12-10T18:00Z to 2026-02-18T23:00Z, and a second runs 10 days from 2025-10-30. The
history starts on 2024-09-30, so this source gives 2 years and energy-charts gives 11.
Compare them on the period that both hold.

Measured on 2026-09-23: production is short by 2,231 records of the 17,324 of its span, and
consumption by 2,273. That is 12.88 % and 13.12 %. 79 whole days hold nothing in each series,
and the largest run of them is 69 days, 2025-12-11 to 2026-02-17.

### Four countries hold little or no history

The probe of 2026-09-16 called every country code for one day, and 34 answered. That is a
test of the present, and it says nothing about the past.

The table is of 2026-09-23. The MD and CY rows changed after the probe, and the paragraph
below the table says how.

| Country | What the store holds |
|---|---|
| MD Moldova | 527 records, 2026-08-23 to 2026-09-14, and nothing before that day. 2,957 days fail and 1,155 days return an empty list. It went silent again on 2026-09-15. |
| CY Cyprus | 27,925 records in 2 eras, with a hole of 3,360 days between them, 2017-06-11 to 2026-08-22. Not one time series. See the paragraph below. |
| GE Georgia | 28,975 records, with a hole of 489 days, 2025-04-21 to 2026-08-22, and 2 smaller holes of 17 and 6 days. See the defect above. |
| XK Kosovo | 2021-08-22 onward. 44,526 records, and 46 absent inside that span. Usable from 2021. |

⚠ The 2 Cyprus eras are not one series. The first holds 27,198 records at a step of 30
minutes, 2015-07-25 21:00 to 2017-06-10 20:30, and its mean is 880.2 g. The second holds 727
records at a step of 60 minutes, 2026-08-23 21:00 to 2026-09-23 03:00, and its mean is
768.7 g. The step changed and the level changed. A trend, a 12-month mean or a European
ranking that joins the two must say so. CY has one source, so nothing checks either era.

energy-charts began to publish MD, CY and GE again on 2026-08-23. MD had no record at all
before that day, so the store holds 34 countries since it, and it held 33 before it. A count
of countries in a document with an earlier date is the count of that date. 2 of the 36 zones
still hold no record: IE and MK. `sources/zones.json` gives the reason for each.

CY and GE stayed. At this morning's run CY is 5.5 hours behind and GE is 10.5 hours behind,
which is the ordinary tail of an hourly publisher. MD did not stay. It answered for 21 days,
2026-08-25 to 2026-09-14, and it went silent again on 2026-09-15.

This morning's run wrote 9 empty days for it. MD is 205.5 hours behind the run, which is the
longest tail in the store by a factor of 8. `atlas status` prints a fail row only, and an
empty day is not a fail, so no command names that silence.

The other 30 countries run from their own first day to the newest day, and 26 of them start on
2015-05-31. Two of the 30 are thin, and the next subsection measures them.

### Montenegro and Great Britain are thin, in two different ways

Measured on 2026-09-23. ME is short by 15,873 records. 14,232 of them are 593 whole days with
no record, in 32 separate runs, and 654 more are 33 part days. The longest run is 236 days,
2025-04-01 to 2025-11-22, and 6 more runs hold 25 to 66 days. Every one of those days carries
the run status `empty`, and not `fail`, so `atlas status` names none of them. ME has one
source, so nothing fills the 32 runs.

energy-charts GB is short by 13,358 records. 11,280 of them are 235 whole days, and one hole
of 226 days holds 10,848 of those: 2021-06-15 to 2022-01-26. NESO covers the same window.
Section 1, *A gap is a gap*, measures why a patch from NESO makes the series worse and not
better.

### The newest hour holds one country

On 2026-09-23 the newest timestamp in the store is 2026-09-23T05:15Z, and 1 country of 34 has
a record at it. The measurement below is of 2026-09-22, and it gives the shape of the tail
behind that newest timestamp.

Measured on 2026-09-22. The publishers do not finish at the same time. The newest timestamp
in the store was 2026-09-18T09:45Z, and 1 country of 33 held a record at it. 5 hours before
it, at 04:45Z, 2 countries held one, and the hour from 04:00 to 05:00 held 3. Only RTE, NESO
and Energinet ran on 2026-09-18. The newest timestamp that 29 of the 33 held together was
2026-09-17T05:00Z, more than a day before.

The portal opens on the newest hour that holds at least 90 % of the records of the best hour
of the last 3 days. It always states the count on screen.

⚠ A query that you write yourself must make the same allowance. A ranking at `max(ts_utc)`
ranks one country.

### A part day is not a day

The last day of the store is always in progress. A mean of it is a mean of the hours that
arrived. The export gives `n`, the count of records in the day, so a part day is visible.

The portal calculator compares only the regions that report every hour of the run, and
it names the regions that it leaves out. A sum across "the hours that this region has" gives
a region with fewer hours a smaller total, and that is not a saving. The measured size of
that error: the same run gave 222.8 kg on a part day, and 647.4 kg on the complete day
before it.

### A hole inside a day marked `ok` is frozen after 2 days

⚠ `config.RECENT_DAYS` is 2. `atlas daily` asks for a day that already carries an `ok` run
row only while that day is younger than 2 days. No scheduled run reads the day after that, so
the hole stays and the run row still says `ok`. Only an operator who gives
`atlas backfill --redo-ok` a window reads that day again. So a part day in the store is not a
statement about the publisher today. It is a statement about the publisher at the one moment
that read that day.

`store.days_to_collect` gives back a day that carries an `ok` row only while
`day > today - force_recent_days`. `atlas daily` passes `config.RECENT_DAYS`, which is 2, so
it reaches 2 days. `atlas backfill` passes 0 and reaches none, whatever `--from` gives.

`atlas backfill --redo-ok` is the one repair. It sets `force_recent_days` to the span from
`--from` to today, plus 1 day. So the command asks for every day of the window again, and a
day with an `ok` row no longer stops it. The flag needs `--from`.
Without it the command stops with exit code 1, before it takes the lock. A re-read of the
whole history is about 2 hours 47 minutes over the network.

### The repair of the frozen day 2026-09-18, and what it proved

The largest frozen day was 2026-09-18. The run of that day reached the middle of it and wrote
an `ok` row. Energinet DK then held 132 stamps of 288, NESO GB 20 of 48 and RTE FR 40 of 96.
That is 240 records that `atlas daily` was not able to reach.

The owner ran one command for each of the 3 frozen series on 2026-09-23:

```
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source energinet-eds --country DK
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source neso-carbon-intensity --country GB
python -m atlas backfill --redo-ok --from 2026-09-18 --to 2026-09-18 --source rte-eco2mix-odre --country FR
```

The 3 commands took about 10 seconds and 3 requests. Energinet DK gave 156 new records. NESO
GB gave 28 new records and 12 revisions. RTE FR gave 56 new records. That is 240 new records,
which is the count that the gap analysis predicted. `atlas export` then wrote the 78 portal
files again.

2026-09-18 now holds Energinet DK 288 of 288, NESO GB 48 of 48 and RTE FR 96 of 96. All three
series are complete for that day. A daily mean of 2026-09-18 from those three sources is the
mean of a whole day again.

The run proved three things:

1. `--redo-ok` reaches a day with an `ok` row against live publishers, and not on a fixture
   alone. The gap analysis predicted 240 records, and the publishers gave 240.
2. A re-read of a settled day corrects values and fills holes. NESO returned 12
   changed values for a day that was 5 days old. Section 1 holds that result.
3. The cost is small when the window names one source and one day.

Smaller frozen days stay, and the same flag reaches each one. energy-charts GB 2026-09-14
holds 44 of 48, and LT 2026-09-15 holds 87 of 96.

⚠ A re-read separates a collection gap from a publisher gap, and only the first one fills.
Six energy-charts countries were short on 2026-09-22. The flag read that day again on
2026-09-23, before the 2-day window closed, and took 48 new records and 3 revisions. GE and
LU became complete, at 24 of 24 and 96 of 96.

BA, BG, GB and SK did not move. They hold 20 of 24, 8 of 24, 46 of 48 and 20 of 24. The
publisher served the same short day a second time. So those four hours are absent at the
source, and no command in this program can get them.

One command with no `--source` repairs a day across every series. It asks all 6 sources and
the 34 collected energy-charts countries. That is 39 requests for one day, and about 20
minutes at 2 requests each minute. `backfill` does not export, so run
`python -m atlas export` after the repair. `RUNNING.md` §3 gives the operator procedure.

### Lithuania publishes small negative forecast values

8 forecast points of 98, from −0.9 to −14.6 g, beside a curve that reaches 81.7 g. The
actual series of Lithuania holds no negative value, and no stored energy-charts value of the
5.1 million is below 3.0 g. The 6 NESO zeros above are the only lower values in the store.

The collector drops the 8 points and names them in the run row. The store holds 89 of the 98,
because the horizon rule drops one more point that comes before the capture. See the two bands
in section 6.

### 5 country codes give no forward curve at energy-charts

CY, GB, GE, MD and XK return no energy-charts forecast. So 29 of the 33 countries of the
store of 2026-09-17 hold an energy-charts curve. NESO gives GB one. NESO advertises 48 h, and
the capture of 2026-09-18 spans 50.67 h. See `FORECASTS.md`.

---

## 3. The store on disk

Two layers, and nothing else. No SQLite, no Parquet tier, no second database.

```
  API ──▶ raw file ──▶ record table ──▶ record_current ──▶ portal JSON
          the bytes    as the           the newest         the files
          + sha256     publisher        revision           a browser reads
                       gave it          a SQL view
                            │                   ▲
                            └──── build again ──┘
```

`atlas rebuild` walks the first arrow again. It reads each raw file, checks its sha256, parses
it through the collector that wrote it, and fills a new `record` table. The second arrow is a
SQL view, and `atlas daily` builds it again at the end of each run.

| Path | What | Why |
|---|---|---|
| `store/atlas.duckdb` | One DuckDB file, 377 MB on 2026-09-23. Three tables and one view: `meta`, `record`, `run`, and `record_current`. | One writer, one reader, no server. DuckDB is the store and the analysis engine at one time. |
| `store/raw/<source>/<yyyy-mm>/<yyyymmddThhmmssZ>-<ISO>[-snap].json.gz` | The payload, as it arrived, with its sha256. 47.7 MB gzipped across 364 files on 2026-09-23. | The evidence. Every number traces back to it, and `atlas rebuild` makes the DuckDB file again from it. |
| `store/log/` | The log of each run. | What the last run did. |
| `portal/data/*.json` | The files the portal reads. | The portal makes no query and no network request. |

That path is the one the collector writes today. No snapshot on disk carries it yet, because
the older code gave a snapshot its own source directory. So the 37 snapshot payloads sit under
`store/raw/energy-charts-co2eq-snap/` (36 files) and `store/raw/neso-carbon-intensity-snap/`
(1 file), with a plain `<yyyymmddThhmmssZ>-<ISO>.json.gz` name.

`store/raw/` is the part to back up. `atlas verify` reads every payload again and compares its
sha256 with the store, and `atlas rebuild --into <dir>` parses every payload again into a new
DuckDB file. The full run of 2026-09-23 read 364 payloads and wrote 6,590,611 records in 2 min
43 s, with no network request. `RUNNING.md` §4 holds the recipe.

⚠ A rebuilt store is not the collected store. The measurement values are the same, to the
digit. 6,586,289 of the 6,586,295 actual rows of `record_current` join by key, and 0 of them
differ in value, unit, basis, scope, granularity or zones. Four things do differ, and each one
changes a number that a reader can see:

1. The 6 rows that hold 0.0 are absent, because a guard that is newer than the payload drops
   them. Section 2 of this document names all 6.
2. `collected_at` and `raw_ref` name another payload in 659,826 rows, which is 10.0 %. The
   value is equal in every one of them.
3. The `run` table holds no `fail` day, so `health.json` reads `days_fail` 0 against 6,990.
4. A forecast `run_at` is the collection time of one payload, and not the instant of the
   snapshot pass. So the forecast series holds 3,852 rows against 3,695, and a panel that
   counts runs counts payloads.

`RUNNING.md` §4 holds the table of all 7 differences, and `atlas/rebuild.py` sections 3 and 4
hold the full contract. `atlas backfill` over the network is the other way back, and it cannot
reproduce the periods that now answer HTTP 500.

---

## 4. The record table

One row for each value.

| Field | Note |
|---|---|
| `country`, `source_id` | From `sources/zones.json` and `sources/sources.json`. |
| `metric` | `intensity`, `power` or `load`. |
| `fuel` | The production type for `power`. Empty for the others. |
| `ts_utc`, `value`, `unit` | The timestamp, the reading and its unit. |
| `basis`, `scope`, `granularity`, `zones` | The provenance. See section 1. |
| `kind`, `run_at`, `horizon_min` | `actual` or `forecast`. See section 7. |
| `collected_at`, `revision`, `raw_ref` | The run time, the revision count, the raw file and its hash. |

The key is `(country, source_id, metric, fuel, ts_utc, kind, run_at)`.

The store keeps the step of the publisher. Energinet gives one value every 5 minutes, RTE one
every 15, NESO one every 30, and the two Elia series one each hour. energy-charts gives 15, 30
or 60 minutes. The collector never resamples on the way in, because a resample cannot be
undone.

Each country has its own step, and `sources/sources.json` holds the observed steps. The
collector derives the real step from each payload and never assumes it.

### The two queries you need

```sql
-- the newest revision of everything
SELECT * FROM record_current WHERE kind = 'actual';

-- the daily mean of one country, with the record count of each day
SELECT CAST(ts_utc AS DATE) AS day, count(*) AS n, avg(value) AS mean_unweighted
FROM record_current
WHERE country = 'DE' AND metric = 'intensity' AND kind = 'actual' AND value IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

Always filter on `kind`. A query with no `kind` filter mixes a measurement with a forecast.

---

## 5. The run table

One row for each source, country, day and kind that the program tried to collect.

| Field | Purpose |
|---|---|
| `source_id`, `country`, `day`, `kind` | What it tried. |
| `status` | `ok`, `empty` or `fail`. |
| `rows`, `http_status`, `error`, `raw_ref` | The evidence and the failure text. |

This table is the to-do list. `atlas daily` asks one question: which pairs have no `ok`
row? That one question replaces a job table, a watermark table and a backoff state. It makes
the program idempotent and restartable, and it lets the program catch up after a stop.

`empty` is not `fail`. A source that answers HTTP 404 for a window before its first day
gives `empty`, and that day does not come back. A `fail` day comes back on the next run. An
`empty` day younger than 7 days also comes back, because the publisher can still fill it.

`atlas daily` leaves an old failed day alone. It tries a failed day again only for the
last 30 days. Without this rule, a period of 2017 that always fails takes 12 requests from
every daily run, for ever. `atlas backfill` tries every failed day again.

Every point that a guard drops is named in the run row, and the status stays `ok`. A value
that the store does not hold must never be invisible.

---

## 6. The collector, and the four guards

Each source is one module. It gives `countries`, `fetch` and `parse`, and the runner calls
only those three. The five modules in the repository run from 233 to 341 lines.

1. `fetch(http, country, start, end)` — one HTTP request. It returns the status and the bytes.
2. `parse(payload, country, context)` — it returns records.

The shared runner owns everything else:

- the rate limit from the register, and the tries,
- the raw write, and the window grouping,
- the split on a server error, and the run row.

Four guards live in `parse`.

| Guard | Rule | On a failure |
|---|---|---|
| 1. The field set | A hash of the field names. | The parse stops. It never writes a null in silence. |
| 2. The range | Two bands. See below. | The point or the payload. |
| 3. UTC only | The parser takes the UTC column, and it fails if that column is absent. | The parse stops. |
| 4. One timestamp, one value | A timestamp two times in one payload. | It depends on the values. See below. |

### Guard 2 has two bands

| Band | Limits | What happens |
|---|---|---|
| The store band | 0 to 1500 g/kWh | The point does not go in the store. The run row names it. |
| The absurd band | −50 to 5000 g/kWh | More than 1 % of the points outside it stops the whole payload. |

One band is not enough. A forecast curve that the program does not capture is lost for ever,
so a small negative artefact must not destroy a payload. A unit error moves a value by a
factor of 1000, and it still writes nothing.

### Guard 4 asks which kind of repeat it is

A publisher breaks the rule in two ways, and the two need different answers. Both were
measured on 2026-09-18, the day the store went from one source to six.

| What came back | Example | What happens |
|---|---|---|
| One timestamp, equal values | RTE labels the hour of the spring time change with the local hours 02:00 and 03:00. Both rows hold one UTC instant and the same number. | One measurement written two times. The program keeps one copy. |
| One timestamp, different values | NESO returned `2021-04-19T19:00Z` with `actual` 303 and `actual` 295 in one answer. | No rule says which one is right. The program stores neither, and the run row names both. |

The first form of this guard stopped the whole window. It cost 90 days of GB and 5,358 days
of FR in one afternoon, for 5 bad half hours. A guard must drop what it cannot trust, and it
must keep what it can. It stops the payload only when more than 1 % of the timestamps
conflict, because that is a format change.

energy-charts is the exception, and `base.py` names it as one. That API gives a UTC epoch.
So the two local labels of a time change cannot make a repeat there, and a conflict is a
format fault. An equal repeat keeps one copy, and a repeat with two different values stops
the payload with no share test.

### Guard 1 asks for the names it reads

Measured on 2026-09-18: 17 of the 1,441 periods of one 30-day NESO window of 2025 hold `actual` and
`index` and no `forecast` key at all. A hash of the whole field set called that a format
change and refused a month of measurements. A field that is absent is not a format change. A
field name that the collector does not know is one, and it still stops the parse.

### The split on a server error

energy-charts answers HTTP 500 for some periods and HTTP 200 for other periods of the same
country. It is not a rate limit and not a size limit. `dk` for 2024 gives 8,784 points in
2 seconds. `dk` for 2015 to 2026 fails after 17 seconds.

A window that gets 500, 502, 503 or 504 goes again as two halves, so the good years stay.
Three limits hold the cost down:

1. A window of 8 days or fewer does not split again.
2. One top window has a budget of 12 extra requests.
3. A window that the runner can split gets one try. A try costs 30 seconds of
   rate limit, and a smaller question is the better answer to a server error.

---

## 7. The forecast model

A forecast record is a measurement record with three more fields: `kind`, `run_at` and
`horizon_min`. The key holds `run_at`, so one hour has one actual and many forecasts.

The design holds two kinds of forecast row, because the publishers do not agree on what a past
forecast is. The program writes kind B only.

| Kind | `run_at` | It answers | Where it comes from |
|---|---|---|---|
| A. Published history | empty, lead not known | "How near is this publisher across 9 years?" | Not collected. `atlas/runner.py:233` sets `kind="actual"` on the measurement path, so the backfill stores actual rows only. Energinet publishes such a history back to 2016, and NESO back to 2018. See section 10. |
| B. Own snapshot | the fetch time, so the horizon is exact | "How near is it at 6 h, and at 24 h?" | `atlas snap`. It grows from the first run forward. |

Kind B is the only forecast row that energy-charts, Electricity Maps and WattTime can
ever give. They publish a forward curve and keep no history of it. A run that
`atlas snap` does not capture is lost for ever. This makes the snapshot more urgent than
the measurement collection.

The horizon depends on the capture time and on the publisher's daily cut-off, and only then on
the country. One capture across the 29 energy-charts countries that return a curve gives 8.0 h,
for RO, to 57.0 h, for AT. A later capture of the same day gives less. Germany gives 15.5 h at
07:32 UTC and 9.0 h at 12:44 UTC, and both curves stop at 21:45 UTC. The collector derives the
horizon from the returned array and never assumes it. See `FORECASTS.md`.

The program takes four snapshots each day, 6 hours apart. With one snapshot at a fixed hour,
the lead and the hour of the day become the same axis. A lead of 2 h is then always the same
hour of the night. The error of a long lead cannot be separated from the error of a solar
hour. Six hours between snapshots break that tie.

`ops/register-tasks.ps1` sets the trigger at 00, 06, 12 and 18 in the local time of the host.
The absolute UTC hours move with summer time.

---

## 8. The export contract

`atlas export` writes the files that the portal reads. It runs at the end of `atlas daily`.
Nothing in `portal/data/` is written by hand.

Ten files hold every country. Two files hold one country each. The sizes were measured on
2026-09-23.

| File | Shape | Size |
|---|---|---|
| `meta.json` | The sources, the countries, the row counts, the stored range, and the unit and the granularity of each country and source. | 13 kB |
| `register.json` | `sources/sources.json` and `sources/zones.json`, copied whole. | 44 kB |
| `latest.json` | The newest value of each country, with its age in hours and a stale flag. | 3 kB |
| `monthly.json` | country × source × month: mean, lowest, highest, median. | 309 kB |
| `daily_all.json` | Each source and country, a dense array of the last 400 daily means, with the record count of each day. | 316 kB |
| `hours.json` | Each source and country, a dense array of the last 30 days of hourly means. | 161 kB |
| `profile.json` | Each source and country, a 12 × 24 grid: month by hour of the day, all years. | 70 kB |
| `forecast.json` | The newest captured forward curve of each country. | 150 kB |
| `health.json` | The run table: days ok, empty and failed, for each country. Each series also gives the records held, the records expected and the count absent. It gives the step in minutes and the largest hole. It gives the newest message of a run that did not fail. 18 fields. ⚠ An export from a rebuilt store reads `days_fail` 0, because a failed request wrote no payload. Section 3. | 13 kB |
| `pairs.json` | Each pair of sources that share a country: the shared hours, the two means, the gap, the ratio, the correlation and the cleanest-hour test. Sections 9b and 9c. | 4 kB |
| `daily/<ISO>.json` | One country, every day of its history. | 1 kB to 516 kB |
| `recent/<ISO>.json` | One country, the last 14 days at the step of the publisher. | 17 kB to 260 kB |

A panel that ranks 34 countries must not read 34 files. So three files are dense. Each
one holds one array for each source and country, and the portal indexes into it. A dense array
also costs less than a row list, because it carries no country code and no timestamp.

⚠ A dense file carries an index and not a key, so a value in the wrong cell is silent.
The tests in `tests/test_s1.py` put a known value at a known time and read the cell back.

The three dense files are keyed by source first, and by country second.

```
daily_all.json   sources[<source_id>][<ISO>].mean_unweighted[day index]
hours.json       sources[<source_id>][<ISO>][hour index]
profile.json     sources[<source_id>][<ISO>].grid[month][hour]
```

Two publishers give a different number for the same hour of the same country, and that
difference is the measurement this program exists for. A query that groups by country alone
averages the two into one cell, and the difference disappears without a trace. Over the hours
that both publishers report, such a query gives 207.9 g for GB. That is neither the 243.8 g
of energy-charts nor the 172.0 g of NESO. Those three numbers are of 2026-09-23, after the
repair of 2026-09-18, and section 9b holds them.

No query in `export.py` averages a value across sources, and a test holds that line.

`pairs.json` reports that difference instead of hiding it. `atlas/analyse.py` writes the
file, `atlas export` calls it, and `atlas measure` prints the same table to the terminal.

The file holds one object for each pair of sources that share a country. Its `method` field
names the query in one sentence. Section 9b and section 9c below give the shape of the result
and the date of the run. The file gives the value of today.

The page loads the 10 shared files at start, which is about 1.08 MB on 2026-09-23. It reads a
per-country file only when a panel asks for that country.

---

## 9. What the first full run measured

The collection ran on 2026-09-17. These numbers are the base for any capacity question.

| Measurement | Result |
|---|---|
| Germany, the full backfill | 2015-05-31 to 2026-09-17, 396,141 records, 40 seconds, one request |
| All 34 country codes, 33 of which return data | 107 windows, 2 hours 23 minutes, 5.1 million records |
| One forecast snapshot of 34 country codes | 16.5 minutes at 2 requests each minute |
| The export | 4.5 seconds and 75 files. The export of 2026-09-23 writes 78 files that hold 10.9 MB, and the largest is `daily/FR.json` at 516 kB. The count rose by 3: `pairs.json` is new, and MD came back and takes a `daily/` and a `recent/` file. |
| The step of Germany across 11 years | 15 minutes, with no gap |
| The yearly time mean of Germany | 558 g in 2015 over 8 months, 375 g in 2026 over 9 months. The first and last complete years are 544 g in 2016 and 388 g in 2025. |

Three measurements changed the code.

1. The batch load uses `COPY`, and not `executemany`. `executemany` binds one row at a
   time, and it needed more than 600 seconds for 375,000 rows. The store writes a temporary
   CSV file and loads it with one `COPY`. The same rows take 0.9 seconds.
2. The publisher counts a day in local time, and the store counts a day in UTC. The
   last UTC day of a window was 2 hours short, and the runner marked it `ok`. The collector
   now adds one day at each end of the request.
3. DuckDB gives the file to one process, and that rule holds for a reader too.
   `atlas status` cannot open the file while a backfill runs. It now gives a plain message
   with the path of the store and the DuckDB error. That message holds no process number,
   because a reader never takes the lock. A second writer gets the process number from the
   lock instead.

---

## 9b. What the second, third and fourth source measured

The collection of 2026-09-18 added NESO for GB, RTE for FR and Energinet for DK. The store
then held two independent series for three countries, and that made the first discrepancy
measurable.

### The store after that run

| Source | Countries | Rows in `record_current` | From | Collection |
|---|---|---|---|---|
| energy-charts `/co2eq` | 33 | 5,105,530 | 2015-05-31 | 107 windows, 2 hours 23 minutes |
| Energinet | DK | 1,020,908 | 2016-12-31 | 22 windows, 4 minutes 54 seconds |
| RTE through ODRE | FR | 261,758 | 2011-12-31 | 34 windows, 5 minutes 44 seconds |
| NESO | GB | 151,951 | 2017-12-31 | 112 windows, 13 minutes 24 seconds |

The four sources hold 6,540,147 rows in `record_current`. The captured forecast rows are not in
that total. The `record` table holds every revision, so it holds 5,105,674 actual
energy-charts rows. The difference of 144 rows is the superseded revisions.

A full backfill of the six sources takes about 2 hours 47 minutes. Plan for that. CY, GE and MD
need 53 of the 107 energy-charts windows, and section 6 says why a window splits.

### The two publishers of one country disagree by 28 % to 53 % of the larger mean

One hourly mean from each source, over every hour that both of them report.

Measured on 2026-09-23 by `atlas measure`, which writes `portal/data/pairs.json`. Every
`atlas daily` writes that file again. So the table below is the shape of the result, and the
file holds the value of today.

The table names each pair by its publisher, with energy-charts first. The file names each pair
by `source_id` in alphabetical order, so DK reads in the other direction there.

| Country | Second source | Hours | energy-charts | The other | Mean gap | Ratio | Gap as a share of energy-charts | Correlation |
|---|---|---|---|---|---|---|---|---|
| DK | Energinet | 85,195 | 284.2 | 134.5 | 149.7 g | 2.11× | 52.7 % | 0.74 |
| FR | RTE | 99,108 | 62.8 | 37.9 | 24.8 g | 1.66× | 39.6 % | 0.96 |
| GB | NESO | 69,570 | 243.8 | 172.0 | 71.8 g | 1.42× | 29.4 % | 0.49 |

energy-charts is higher in all three, on every measure. The register expected 20 to 40 g for
GB, from the difference between direct and lifecycle factors. The measurement is 71.8 g on the
mean gap, and 84.0 g on the mean of the absolute gap. The absolute gap is 34.4 % of the
energy-charts mean. The factor scope does not explain that alone.

⚠ A share needs its denominator. The share column above divides the mean gap by the
energy-charts mean. That is the larger mean of each of these three pairs.

The `gap_share_pct` field of `pairs.json` divides by the same number. `atlas/analyse.py` takes
the larger of `mean_a` and `mean_b`, and the file states the choice in the top-level field
`denominator`. So the `range` field of the file reads 28.0 % to 52.7 %, which is the range
above.

The sign is a property of the alphabet and not of the size. `a` is the alphabetically first
`source_id`. It holds the smaller mean for DK and for the two Belgian method pairs, so those
3 rows carry a minus sign. `mean_a`, `mean_b` and `ratio` are in the file, so another form is
one division away. Always say which mean is the denominator.

The range over the larger mean covers the five method pairs of the file. The lowest is the
Belgian pair energy-charts against Elia production at 28.0 %. The highest is DK at 52.7 %,
which is the same pair as the first row of the table. The other Belgian method pair is 28.9 %.
The two Elia series are a basis pair, and section 9c holds them.

⚠ Two of those five pairs are not in a clone of this repository. The DK pair needs the
Energinet series and the GB pair needs the NESO series, and `LICENSE-DATA.md` holds both
inside Wirtek. A store that a reader rebuilds from the shipped payloads gives 4 pairs. They
are the two Belgian method pairs at -28.9 % and -28.0 %, the FR pair at 39.6 %, and the
Belgian basis pair at -1.3 %. Those 4 read the same as the live store, number for number,
measured 2026-09-23.

So a reader of a clone can repeat 3 of the 5 method pairs, and not the largest one. Do not
quote the 28 % to 53 % range from a rebuilt clone.

### What moved between 2026-09-18 and 2026-09-23

The first measurement of this table was a hand query on the store of 2026-09-18. `atlas daily`
added five days after it, and the repair of 2026-09-23 completed 2026-09-18. The shared hours
rose by 137 for DK, by 139 for FR and by 138 for GB. The five days give 124, 125 and 125 of
those, and the repair gives the other 13, 14 and 13. Every mean moved by 0.2 g or less, and
every correlation is the same to 2 decimal places. Three cells moved more than the new hours
explain:

1. FR names the same cleanest hour on 43.2 % of days, against 40.1 % before. The hand query
   broke a tie between two hours of one value in an arbitrary order. `analyse.py` gives the
   earliest hour of the tie.
2. GB comes within one hour on 45.9 %, against 48.1 % before. `analyse.py` takes the plain
   difference of the two hours. The earlier query treated hour 23 and hour 00 as one hour
   apart. The file does not wrap, and `REFERENCE.md` section 10 holds that open point.
3. The DK share read −111.3 % in the file of the morning of 2026-09-23, and it reads −52.7 %
   in the file of that afternoon. The denominator changed to the larger mean on that day.
   The data did not change.

⚠ The gap is not a constant offset. The GB correlation is 0.49. The two series do not
agree about *when* the British grid is clean. A test on a shift of −2 to +2 hours peaks at
zero, so the timestamps are aligned and the disagreement is real.

### The choice of source changes the decision

For each complete day that both sources cover with 24 hours, which hour did each one call
the cleanest? Measured on 2026-09-23 by `atlas measure`. The `days`, `same_hour_pct` and
`within_one_hour_pct` fields of `portal/data/pairs.json` hold the value of today.

| Country | Complete days | The same hour | Within one hour |
|---|---|---|---|
| GB | 2,344 | 28.7 % | 45.9 % |
| DK | 3,535 | 38.0 % | 52.1 % |
| FR | 4,100 | 43.2 % | 62.1 % |

Each of the three pairs gained one complete day on 2026-09-23. The test needs 24 hours from
both sources, and 2026-09-18 was a part day until the repair.

Two series that agree by chance alone name the same hour on 4.17 % of days, and come within
one hour on 12.5 %. The `chance` field of the file holds those two numbers, so a panel never
gives an agreement rate with no baseline beside it. So these three pairs are far above chance
and far below agreement.

A scheduler on energy-charts and a scheduler on the national operator pick a different hour on
71.3 % of days for GB. The rate is 62.0 % for DK and 56.8 % for FR. Neither publisher is
wrong. They answer different questions, with different factor tables, on different bases.

Within one hour is the plain difference of the two hours. It does not wrap, so hour 23 and
hour 00 are 23 hours apart in this count. Section 10 holds that open point.

---

## 9c. What Belgium separated

The collection of 2026-09-18 added the two Elia series. Elia is the only publisher in the
register that gives two accounting bases for the same hour of the same country. The two
series share the unit and the factor table. Section 9b measured three pairs in which the
basis, the scope and the factor table all differ together. No pair of section 9b can say which
one causes the gap. This pair can.

| Source | Country | Rows on 2026-09-18 | From | Collection |
|---|---|---|---|---|
| Elia `ods192` production | BE | 14,995 | 2024-09-30 | 2 windows, 13 seconds |
| Elia `ods192` consumption | BE | 14,953 | 2024-09-30 | 2 windows, 12 seconds |

284 zeros were dropped from the production series and 326 from the consumption series, with
the reason in the run rows. No day failed. The store then held 6,571,986 current rows from
6 sources: 6,570,095 measurements and 1,891 captured forecast points. Four countries have two
or more sources: BE 3, DK 2, FR 2 and GB 2.

On 2026-09-23, after the repair of 2026-09-18, the two Elia series hold 15,093 and 15,051
rows. The store holds 6,589,990 current rows: 6,586,295 measurements and 3,695 captured
forecast points. The repair gave 240 of the measurements. The snapshot of that morning gave
1,804 of the forecast points, and the 1,891 older points stay. `meta.json` gives the row count
of each source, and `atlas status` prints it.

### The three pairs of Belgium

Hourly means, over every hour that both members of the pair report. Measured on 2026-09-23 by
`atlas measure`. The three pairs carry `country` `BE` in `portal/data/pairs.json`, and the
first of them is the only pair of the file with `kind` `basis`.

| Pair | What differs | Mean | Ratio | Mean absolute difference | Correlation |
|---|---|---|---|---|---|
| Elia production vs Elia consumption | the basis only | 145.1 / 143.2 | 1.01× | 35.0 g | 0.82 |
| energy-charts vs Elia production | the method only | 201.3 / 144.9 | 1.39× | 60.3 g | 0.93 |
| energy-charts vs Elia consumption | both | 201.4 / 143.2 | 1.41× | 62.2 g | 0.79 |

The Elia series stop at 2026-09-22 17:00 UTC, and the other five sources reach 2026-09-23. So
the Belgian pairs gained 98 shared hours since 2026-09-18, and the other three pairs gained
about 138 each. No mean of this table moved by more than 0.3 g in those five days. The repair
of 2026-09-18 touched DK, FR and GB only, so no Belgian pair changed.

### Which hour did each one call the cleanest?

For each day that the pair covers with 24 hours. The days and the shares are of 2026-09-23,
and `pairs.json` holds them. The worst single hour is not in that file, and its column is the
hand measurement of 2026-09-18.

| Pair | Complete days | The same hour | The worst single hour |
|---|---|---|---|
| the basis only | 555 | 38.2 % | 427.3 g |
| the method only | 572 | 68.9 % | 365.2 g |
| both | 555 | 30.6 % | 372.7 g |

### Three results, and two of them were not expected

Each number below is of 2026-09-23, and `portal/data/pairs.json` holds it again after each
`atlas daily`. The three results held on 2026-09-18 with the same numbers to 1 decimal place.

1. The basis moves the schedule, and it does not move the mean. The two bases differ by
   1.3 % across 2 years. Hour by hour they differ by 35.0 g, and the worst hour differs by
   427.3 g, which is the hand measurement of 2026-09-18. A yearly report cannot see the
   basis. An hourly scheduler cannot ignore it.

2. Of the two causes this pair can separate, the basis moves the chosen hour more than the
   method does, and by a factor near 2. The method pair names the same cleanest hour on
   68.9 % of days, and the basis pair on 38.2 %. The register treated the basis as one cause
   among several.

3. The method gap stays when the basis is held constant. energy-charts and Elia both give a
   production-based number in gCO₂eq/kWh for Belgium, and they differ by 1.39×. The basis
   accounts for 1.3 % of the mean, so the factor table and the model are the candidates for
   the rest. This pair does not measure their shares.

This weakens a sentence that the portal builds from the register. The rule names the
basis and the scope as causes of a discrepancy. For Belgium the basis does not cause the
size of the gap. It causes the disagreement about which hour to pick. The two are different
claims, and a panel must not merge them. See `ARCHITECTURE.md`, *Rules for the rule*.

---

## 10. What is not built

This system runs and collects. The table holds six parts of the design. The first two were
built on 2026-09-23, and each row gives what is still absent.

| Part | The state today | What it needs |
|---|---|---|
| The discrepancy measurement | Built on 2026-09-23. `atlas/analyse.py` holds the query, `atlas measure` prints it, `atlas export` writes `portal/data/pairs.json`, and section 8c of `tests/test_s1.py` checks the arithmetic on a fixture. It measures each pair of sources that share a country: 6 pairs today. | Nothing. |
| The discrepancy panel | Built on 2026-09-23. The Source discrepancy tab reads `pairs.json`. It draws the 6 pairs, the unit mark of each pair, the cleanest-hour test against the chance rate, and the Belgian basis pair. It gives no row for each country and hour. | A panel that gives the spread of each hour, the widest pair of that hour, and the size of the spread against the mean. |
| The basis panel | Belgium holds both accounting bases from one publisher. `pairs.json` marks that pair `kind` `basis` and every other pair `method`, so the two effects are already two records. The Source discrepancy tab gives the basis pair its own card and names the two effects there. No rule writes the sentence. | A rule that reports the basis effect and the method effect as two claims. Section 9c says why they must not merge. |
| The forecast score | The store holds the captured curve of energy-charts and of NESO, and no error. | Many captured runs. NESO also publishes its own past forecast beside each measurement, and that gives a score without a wait. See below. |
| A second source for the other 30 countries | BE, DK, FR and GB have two or more. The other 30 have one, counted on 2026-09-23. | The ENTSO-E key. It is the only source in the register that reaches every country. |
| The generation mix, and the load-weighted country value | The store holds no mix. Every row is `native`, except the Danish roll-up. | The `/public_power` collector, and a factor set for a computed intensity. |

The cheapest next step is the NESO forecast history. Each NESO period carries `forecast`
beside `actual`, so the publisher states what it predicted for an hour that is now measured.
That is 152,182 pairs already in the raw files, counted on 2026-09-23. The collector reads
the `forecast` column
today in a snapshot run only, because the runner asks for one kind in a measurement run. A
`kind` argument on the measurement pass turns 8 years of British forecast into a score.

Two decisions are still open, and both are recorded in `SOURCES.md`:

1. The roll-up weighting for ES, FR, IT, NO, PT and SE. DK is settled. The Danish country
   value is the mean of DK1 and DK2. The weight is the gross consumption of each area in that
   hour, from the same publisher. `SOURCES.md` §9.
2. The emission-factor set for a computed intensity. IPCC AR5 Annex III is the
   recommendation. Only ENTSO-E needs it. `SOURCES.md` §8 and §0.1.

The pair measurement of 2026-09-23 opened two more, and both are arithmetic and not data. The
first of the two is closed, and this entry keeps the record of it:

3. The denominator of `gap_share_pct`. Closed on 2026-09-23. The field divides by the larger
   of `mean_a` and `mean_b`, and `pairs.json` states it in the field `denominator`. The
   `range` field of the file reads 28.0 % to 52.7 %, which is the form that section 9b
   reports. A division by `mean_a` gave 29.4 % to 111.3 % on the same six gaps, and no file
   of this system prints that form now.
4. The wrap of `within_one_hour_pct`. The count takes the plain difference of the two hours,
   so hour 23 and hour 00 count as 23 hours apart. The hand query of 2026-09-18 used a
   circular distance, and it gave 48.1 % for GB where the file gives 45.9 % today. That is one
   line of SQL in `atlas/analyse.py`. Nobody made that choice yet.

`atlas rebuild` opened a fifth one on 2026-09-23, and it is a decision about the store and not
about a query:

5. The `run_at` of a forecast in a rebuilt store. A rebuild gives each payload its own
   `run_at`, so one snapshot pass becomes many runs, and the Forecast tab reads 61 runs
   against 4. A fix exists: group the payloads of one snapshot pass and give the group the
   earliest `collected_at`. It changes what the store holds, so the owner decides it.
