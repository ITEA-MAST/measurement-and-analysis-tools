# Forecasts

Probed 2026-09-17. All calls in this note were made on that date, with no key. Figures read
from the store carry their own capture date.

Three open sources publish a forward carbon curve. This program collects two of them today:
energy-charts and NESO. The Energinet prognosis is in the register with
`has_forecast_curve = False`, and it is the next collector to write. A fourth path, ENTSO-E,
is open but needs a token and needs a computation step.

A forecast is only of use if the program keeps it. A publisher replaces its forecast with the
next run and does not keep the old one. If the collector stores only the newest run, the
program can never measure how good the forecast was. So the store must keep each run.

## 1. Sources that publish a forecast

| Source | What it forecasts | Horizon | Step | New run | Access | Countries |
|---|---|---|---|---|---|---|
| energy-charts `/co2eq` | carbon intensity | 8.0 h to 57.0 h in one capture, set by the publisher cut-off (§3) | 15 min | every 15 min | open | 29 of 34 in the first capture; CY, GB, GE, MD and XK gave none |
| NESO Carbon Intensity | carbon intensity | 48 h advertised, 50.67 h in the 2026-09-18 capture (§3) | 30 min | every 30 min | open | Great Britain, and 14 regions |
| Energinet `CO2EmisProg` | carbon intensity | about 15 h | 5 min | every 5 min | open, and not collected yet | DK1 and DK2 |
| ENTSO-E Transparency | generation and load by type | 48 h (day-ahead) | 60 min | day-ahead, plus intraday | token | the whole synchronous area |
| Electricity Maps | carbon intensity | 24 h | 60 min | hourly | paid plan | all zones on the plan |
| WattTime | marginal intensity | 24 h | 5 min | every 5 min | registration, paid for most regions | partial in Europe |

### What the probe returned

energy-charts — `GET https://api.energy-charts.info/co2eq?country=de`

The same response carries `co2eq` and `co2eq_forecast`, at a 15-minute step. At 07:32 UTC the
actual values stopped at 06:00 UTC and the forecast ran from 06:15 to 21:45 UTC. The forecast
array spans 15.5 h. It reaches 15.75 h past the last actual value, and 14.2 h past the clock.

Two more endpoints give the inputs of that curve. Both are open:

- `/ren_share_forecast?country=de` — renewable share, solar share, wind share. 15 min, to
  21:45 UTC.
- `/public_power_forecast?country=de&production_type=solar` — MW by production type.

NESO — `GET https://api.carbonintensity.org.uk/intensity/<from>/fw48h`

97 half-hour periods, 48 h ahead, each one `{"forecast": 64, "actual": null, "index": "low"}`.
The regional endpoint `/regional/intensity/<from>/fw48h/regionid/13` gives the same 48 h for
each of 14 regions, with the forecast generation mix by fuel. 48 h is the figure NESO
advertises. The one capture in the store, `run_at` 2026-09-18 10:19:47 UTC, holds 102 points
and spans 50.67 h. NESO is the only source that gives a forecast mix with the forecast
intensity.

⚠ The `/intensity` endpoint returns `forecast` and `actual` as two fields of one record.
Never write `actual or forecast` into one column. The program must keep which one it used.
(`SOURCES.md` §NESO records this as a defect of the previous pipeline.)

Energinet — `GET https://api.energidataservice.dk/dataset/CO2EmisProg`

A 5-minute prognosis for DK1 and DK2. At 07:25 UTC the newest actual was 07:25 and the
prognosis ran to 21:55 UTC, which is 14.5 h ahead.

This dataset keeps its past prognoses. A query sorted by time ascending returns records from
2016-12-31, so a score against the actual needs no wait for the store to fill. The collector
is not written: `atlas/collectors/energinet_eds.py` sets `has_forecast_curve = False`, and
`atlas snap` skips Denmark. The dataset gives no run time, so this history can give a score
of the level across 9 years, and never a score by lead.

ENTSO-E — not a carbon forecast. It publishes the day-ahead forecast of generation by
production type (`A69` wind and solar, `A71` generation), and the load forecast (`A65`). This
program must multiply the forecast mix by a factor table, in the same way it computes the
actual intensity. Two results follow:

1. It is the only open path to a forecast for every country in the zone model.
2. The forecast and the actual then use the same factor table, so an error in the table
   cancels. The comparison measures the forecast of the mix. That is a better test.

## 2. What no source gives

- No open source forecasts a week ahead. The longest curve measured here is 57.0 h (§3). A
  workload that must move next week has no carbon forecast. It has a seasonal pattern, which
  is a different thing.
- No source forecasts a month. For a monthly plan the program must use its own history.
- Only NESO forecasts regions. For the other countries the forecast is national.
- Marginal and average are different questions. WattTime forecasts the marginal intensity:
  what one more kWh causes. The other sources forecast the average. Do not compare them.

## 3. How a forecast is stored

A forecast record is a measurement record with three more fields.

| Field | Purpose |
|---|---|
| `kind` | `actual` or `forecast`. One column, never a mixed one. |
| `run_at` | The time this program captured the curve. No open endpoint gives its own run time, so the lead is measured from the capture. One sweep writes one `run_at`, so a country fetched late in the sweep carries up to 16.5 minutes of offset. |
| `horizon_min` | `ts_utc` − `run_at`, in minutes. |

The other fields do not change: `country`, `source_id`, `ts_utc`, `value`, `basis`, `scope`,
`granularity`, `zones`, `collected_at`, `revision`.

Two rules follow from the field list:

1. The key is (country, source, ts_utc, kind, run_at). One hour has one actual and many
   forecasts. A forecast must not overwrite an older forecast of the same hour.
2. A forecast is never a fallback for a missing actual. If the collector has no actual, the
   row is a gap. The portal shows "no record". It does not show the forecast in its place.

### What the first real snapshot measured, 2026-09-17

`atlas snap` asked all 34 energy-charts countries. The store records `run_at`
2026-09-17T12:44:30Z for that sweep, with 28 countries and 1,654 forecast points. Lithuania
carries a curve from a second run at 13:05:13Z, which makes 29 countries. The raw payload
names run from `20260917T124430Z` to `20260917T130100Z`, so the sweep took 16.5 minutes at 2
requests each minute. An earlier draft of this note gave the time as 15:44 UTC, which was the
local EEST clock of the author. `runs_in_store` in `portal/data/forecast.json` holds the run
times and the point counts.

⚠ The horizon depends on the capture time and on the publisher's daily cut-off, and only then
on the country. In this capture 23 of the 29 curves end at 21:00 or 21:45 UTC, on the same
day or the next. Germany gives 15.5 h in the 07:32 probe above and 9.0 h in this 12:44
capture. Both curves stop at 21:45 UTC of the same day.

| Countries | Points in the curve | Hours ahead |
|---|---:|---:|
| AT | 229 | 57.0 |
| FI | 141 | 35.0 |
| ES, HU, LU, NL, NO | 133 | 33.0 |
| BE, BG, RS | 33 | 32.25 |
| GR | 32 | 31.25 |
| CZ | 93 | 29.0 |
| LT | 89 | 22.65 |
| FR | 40 | 9.75 |
| DE, DK, EE, HR, IT, PL, SE | 37 | 9.0 |
| BA, CH, LV, ME, PT, SI, SK | 9 | 8.25 |
| RO | 33 | 8.0 |

So the collector must derive the horizon from the returned array. It must never assume one.
The lead analysis must bin on `horizon_min`.

5 country codes give no forward curve at energy-charts: CY, GB, GE, MD and XK. For GB, NESO
gives a forecast that it advertises as 48 h, and the 2026-09-18 capture of it spans 50.67 h.
The longest horizon measured in this register is AT at 57.0 h, from energy-charts. The other
4 codes have little or no history at energy-charts. See `SOURCES.md` §1.1.

⚠ Lithuania carries negative forecast values. 8 points of 98, from −0.9 to −14.6 gCO₂eq/kWh,
beside a curve that reaches 81.7 g. The actual series of Lithuania holds no negative value,
and no actual value of energy-charts in the store is below 3.0 g. The collector drops the 8
points. The store holds 89 of the 98, because the horizon rule drops one more point that
precedes the capture. See `REFERENCE.md` §6.

### Two kinds of forecast history

A probe on 2026-09-17 found that the sources do not agree on what a past forecast is.

| Source | What a past period gives | Lead of that value |
|---|---|---|
| Energinet `CO2EmisProg` | One row for each 5-minute step, back to 2016-12-31. | Not known. The dataset has 4 columns and none of them is a run time. |
| NESO | `forecast` beside `actual` for each 30-minute step, back to 2018-05-11. | Not known. The API gives no run time. |
| energy-charts `/co2eq` | `co2eq_forecast` is empty for a past period. 288 actual values and 0 forecast values across 2 days of March 2024. | No history at all. |

So the design holds two kinds of forecast row. The program writes kind B only.

| Kind | `run_at` | What it answers | Where it comes from |
|---|---|---|---|
| A. Published history | empty, so the lead is not known | "How near is this publisher, across 9 years?" | Not collected yet. `atlas/runner.py:233` sets `kind="actual"` on the measurement path, so the backfill stores actual rows only. See `REFERENCE.md` §10. |
| B. Own snapshot | the time of the fetch | "How near is this publisher at 6 h, and at 24 h?" | Each `atlas snap` run. It accumulates from day 1 forward. |

⚠ Kind B is the only forecast record that energy-charts, Electricity Maps and WattTime can
ever give. Those sources publish a forward curve and keep no history of it. A run that the
program does not capture is lost for ever. The forecast collector must be running before the
measurement collection is complete.

### The volume, and why the lead set is not necessary

NESO at a 30-minute step, 48 h ahead, 48 times each day, is about 4600 records each day for
one country. That volume comes from a 30-minute collection. A program that collects 4 times
each day stores 4 full curves each day, which is about 3 million rows each year for all
sources. The full curve of each run is then affordable, and the program does not need a set
of leads.

## 4. How a forecast will be scored

This section is the design of the analysis step. No analysis code is in the program today.

The analysis step will run after each collection. For each (country, source, lead) it will
compute:

| Measure | What it says |
|---|---|
| MAE, mean absolute error, in g | The mean size of the error. |
| Bias, mean error with its sign | A publisher that always runs low is correctable. A random error is not. |
| MAE as a share of the mean | Makes two countries comparable. 10 g is large in France and small in Poland. |
| Skill against persistence | The error of the forecast, divided by the error of the rule that the next hour is the same as this hour. A value above 1 means the forecast is worse than no forecast. |

The last one is the one that matters. The portal states the same baseline, so the two agree.

### The decision test

A workload scheduler does not need the correct number. It needs the correct order. So the
analysis will also compute, for each day:

- did the forecast pick the hour that was in fact the cleanest?
- if not, how close was the hour it picked, as a percentage of the best hour?
- how much carbon did the wrong choice cost, in g/kWh?

The last figure is the one to report. It states the cost of the forecast error in the unit of
the decision. A forecast that seldom picks the exact hour can still serve a scheduler, if the
hour it picks is near the best one. The analysis step will give the shares when it runs.

## 5. What this will give the program

1. A scheduler will be able to plan. A workload can go in the cleanest hour of the next 24 h.
2. The claim can be audited. A claim of the form "we moved the workload and we saved 40
   g/kWh" is a claim about a forecast. With the store it is a measurement.
3. The publishers can be compared on skill and on level. The discrepancy score compares the
   present. The forecast score compares the future.

## 6. Open points

1. 4 snapshots each day are registered by `ops/register-tasks.ps1`, at 00:00 and then every 6
   hours.
   ⚠ The trigger is local time, so summer time moves the capture hour twice each year. The
   lead analysis must bin on `run_at` in UTC, and not on the scheduled hour. One snapshot
   each day makes the lead and the hour of the day the same axis, so the two effects cannot
   be separated. See `REFERENCE.md` §7.
2. The factor table for the ENTSO-E computed forecast is the same open decision as for the
   actual series. See `SOURCES.md` §8 item 5.
3. Retention of the forecast rows is not selected. The measurement series is kept for ever. A
   forecast older than one year has little use after it is scored.
4. A forecast of this program's own, from the ENTSO-E mix forecast and from weather, is
   possible. It is not in scope until the collectors run.
