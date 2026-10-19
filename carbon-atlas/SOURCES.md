# Source register

Compiled 2026-09-16, and cut to 12 entries on 2026-09-18. The Elia entry became two entries on
the same day, so the file holds 13 entries from 11 publishers. Every entry marked verified
live was called on 2026-09-16 or 2026-09-18 from this machine, and the response is quoted.

The machine-readable form is `sources/sources.json`. That file is authoritative for the
collectors and for the portal. This file explains the choices, and it keeps the research on the
sources that the register no longer holds.

Sections 0.x hold the results, newest first. Section 0 is the oldest sweep.

The forecast side of these sources is in `FORECASTS.md`, probed 2026-09-17.

---

## 0.3 Belgium separates the basis from the method

Collected on 2026-09-18. Elia publishes a production-based and a consumption-based intensity
for the same hour of the same country, in the same unit, from the same factor table. It is the
only source in the register that does this. Every other pair in the store moves the basis, the
scope and the factor table together. Only the Belgian pair can say which one causes the gap.
It gives three results.

`REFERENCE.md` §9c holds the measurement itself, and its figures are of 2026-09-23. It gives
the three pairs, the row counts, the means, the ratios and the correlations. It also gives the
share of days on which each pair names the same cleanest hour.

`portal/data/pairs.json` holds the value of today, and the three Belgian pairs carry `country`
`BE` in it. Quote a dated figure from `REFERENCE.md` §9c, and a current figure from the file.
This section holds what they mean for the register.

1. The basis moves the schedule, and it does not move the mean. The two bases differ by
   1.3 % across 2 years, and hour by hour they differ far more. So a yearly report cannot see
   the basis, and an hourly scheduler cannot ignore it.
2. Of the two causes this pair can separate, the basis moves the chosen hour more than the
   method does, and by a factor near 2. The register treated the basis as one cause among
   several.
3. A method gap of 1.39× stays after the basis is held constant. energy-charts and Elia both
   give a production-based number in gCO₂eq/kWh for Belgium. That gap is 28.0 % of the
   energy-charts mean and 38.9 % of the Elia mean, so state the ratio or name the mean. The
   basis accounts for 1.3 % of the mean, so the factor table, the model and the scope are the
   candidates for the rest. This register cannot separate them, because neither publisher
   states its factors.

This weakens a sentence the portal builds from the register. The rule names the basis and the
scope as causes of a discrepancy. For Belgium the basis does not cause the size of the gap. It
causes the disagreement about which hour to pick. The two are different claims, and the panel
must not merge them. See `ARCHITECTURE.md`, *Rules for the rule*.

---

## 0.2 What the second, third and fourth source measured

Collected on 2026-09-18. NESO for GB, RTE for FR and Energinet for DK. Every open source in
the register that publishes a sub-hourly national carbon-intensity series is now in the store.
`REFERENCE.md` §9b holds the measurement of 2026-09-23, and it names the query. It gives the
hourly means of each pair, the shared-hour counts, the ratios and the correlations. It also
gives the share of days on which the two publishers name the same cleanest hour.

`portal/data/pairs.json` holds the value of today, and `atlas measure` prints it. Quote a
dated figure from `REFERENCE.md` §9b, and a current figure from the file. The three results
that change how a number from this system must be read:

1. The two publishers of one country differ by 28 % to 53 % of the larger mean, measured
   2026-09-23. The national operator is lower in all three. Each share is the mean gap over
   the energy-charts mean, which is the larger mean of each of these three pairs. The
   `gap_share_pct` field of `portal/data/pairs.json` divides by that same larger mean, and the
   file names the choice in its `denominator` field. Name the denominator with the number. The
   register predicted 20 to 40 g for GB from the scope of the factors. The measurement is
   71.8 g.
2. The gap is not a constant. The GB correlation between the two series is 0.49. A shift test
   of −2 to +2 hours peaks at 0, so the timestamps line up and the disagreement is real. The
   two sources do not agree about when the British grid is clean.
3. The source changes the decision. On complete days the two publishers pick a different
   cleanest hour on most days, for all three countries.

Neither publisher is wrong. They answer different questions: a different basis, a different
factor table, and CO₂ against CO₂eq. Which one is right for a report depends on the reporting
standard, and that decision is open.

---

## 0.1 The register keeps 13 entries of 27

Decision of 2026-09-18. The register holds a source only when that source can be collected.
15 entries were removed. The sections below keep the research on each one, because a removal is
cheap to undo and the probe result is the reason not to.

The 13 entries come from 11 publishers. Elia gives two accounting bases from one dataset, and
each one needs its own source id. Fraunhofer ISE gives `/co2eq` and `/v2/public_power`. See
[§1.6](#16-elia-open-data-belgium--two-bases-one-dataset).

| Removed | Why | Research |
|---|---|---|
| REE apidatos (ES) | HTTP 400 on the probe of 2026-09-16. | §6 |
| Terna (IT) | HTTP 596 on the probe of 2026-09-16. | §6 |
| NED.nl (NL) | HTTP 401. It needs a key that nobody asked for. | §6 |
| Fingrid (FI) | HTTP 403. The same. | §6 |
| Ember | HTTP 403 without a key. Annual and monthly only. | §2.4 |
| EEA emission intensity | Never called. Annual only. | §4 |
| ECON-PowerCI | Never called. A paper. It has no API. | §4 |
| WattTime | Never called. Marginal factors, and they cannot be validated. | §1.8 |
| IONOS Sustainability Report 2025 | A PDF. The PUE of 1.39 stays in the calculator. | §5 |
| Cloud Carbon Footprint | A model. It computes an estimate. | §5 |
| Boavizta | Never called. Embodied carbon, which this program does not compute. | §5 |
| IPCC AR5 Annex III factors | A table in a report. No endpoint. | §3 |
| UNECE 2022 factors | The same. | §3 |
| IEA upstream factors 2024 | The same. | §3 |
| Unnewehr et al. factors | The same. | §3 |

ENTSO-E stays, because it is the only source that reaches every country in the zone model. It
needs a key. The request is still open, and §8 holds it as the one item with a lead time.

The prune of 2026-09-18 has two consequences.

1. The factor tables left the register. ENTSO-E gives a generation mix, and a mix is not an
   intensity. To convert one to the other needs a factor table. §3 and §8 hold that research, and
   the recommendation is still IPCC AR5 Annex III. The chosen table must come back into the
   register on the day a mix collector starts. A stored value must name the table that made it.
2. Four countries lost their national source. ES, IT, NL and FI pointed at REE, Terna, NED.nl
   and Fingrid. `sources/zones.json` now says `national: null` for all four, with the reason.
   ENTSO-E is the only route to a second value for them.

---

## 0. What changed against the previous investigation

The `carbon-aware 1/` investigation used two carbon sources and three regions
(energy-charts for DE, FR, ES; NESO for GB). Three findings from this sweep change the
scope of what is possible.

#### (a) The undocumented endpoint serves 34 countries, not 3

`carbon-aware 1/` fetched `/co2eq` for `de`, `fr` and `es` only. All 37 country codes in the
energy-charts enum, plus the `eu` aggregate, were called on 2026-09-16 over the window
`start=2026-09-10&end=2026-09-11`. 34 of the 37 returned HTTP 200 with real values, and
so did `eu`.

Sorted by mean intensity on that window, in gCO₂eq/kWh:

| Country | Mean | Res. | | Country | Mean | Res. |
|---|---:|---|---|---|---:|---|
| `ch` Switzerland | 20.6 | 60 min | | `hu` Hungary | 180.8 | 15 min |
| `se` Sweden | 22.6 | 15 min | | `hr` Croatia | 254.7 | 15 min |
| `lv` Latvia | 27.2 | 60 min | | `md` Moldova | 296.8 | 60 min |
| `no` Norway | 29.6 | 15 min | | `lu` Luxembourg | 303.4 | 15 min |
| `si` Slovenia | 36.8 | 60 min | | `it` Italy | 303.9 | 15 min |
| `fi` Finland | 50.5 | 15 min | | `be` Belgium | 312.9 | 60 min |
| `lt` Lithuania | 66.7 | 15 min | | `gr` Greece | 321.3 | 60 min |
| `sk` Slovakia | 90.1 | 60 min | | `bg` Bulgaria | 345.6 | 60 min |
| `at` Austria | 96.2 | 15 min | | `ro` Romania | 376.9 | 15 min |
| `uk` Great Britain | 122.5 | 30 min | | `cz` Czechia | 508.8 | 15 min |
| `ge` Georgia | 126.4 | 60 min | | `nl` Netherlands | 521.8 | 15 min |
| `ee` Estonia | 132.8 | 15 min | | `pl` Poland | 676.5 | 15 min |
| `pt` Portugal | 147.5 | 60 min | | `cy` Cyprus | 720.6 | 60 min |
| `dk` Denmark | 163.0 | 15 min | | `rs` Serbia | 921.2 | 60 min |
| | | | | `me` Montenegro | 1013.1 | 60 min |
| `eu` aggregate | 278.2 | 60 min | | `ba` Bosnia and Herzegovina | 1056.9 | 60 min |
| | | | | `xk` Kosovo | 1126.0 | 60 min |

`de`, `fr` and `es` are the three the previous work already had. All three run at 15 minutes,
and they are not in the table above. So the table shows 31 countries and the `eu` row.

Not available: `ie` HTTP 404, `ua` HTTP 404. `mk` (North Macedonia) returns HTTP 200, but
every actual value is null and only the forecast array is populated. MK stays in the country
list. It carries no usable carbon data until another source covers it.

The sweep of 2026-09-16 has three consequences.

1. The spread is 55×, not 8×. The previous investigation compared a 377 g country
   against a 46 g country. The real European range on a single day runs from Switzerland at
   20.6 g to Kosovo at 1126 g. Any claim about the value of moving a workload has to be
   restated against this range.
2. Neighbours diverge. Slovenia 36.8 against Croatia 254.7. Latvia 27.2 against
   Estonia 132.8. These are adjacent, interconnected grids. A country-level average is not a
   safe proxy for a nearby one.
3. The `eu` aggregate is free. 278.2 g on that window, from the same endpoint and the same
   method. It is the denominator for "how much better than average is this region", and it
   costs one request.

⚠ Resolution is not uniform: 15 minutes for 18 countries, 30 minutes for `uk`, and 60 minutes
for the other 15. The `eu` aggregate is also 60 minutes. The counts come from
`sources/sources.json`, key `resolution_minutes_observed`. The resolution also appears to
change between windows for the same country. Always derive the resolution from the returned
`unix_seconds` array. Never assume it.

Any cross-country statistic must resample to a common grid first. The previous analysis
intersected raw timestamp sets. That cut the sample count from 35,014 to 17,457 in silence,
as soon as GB came into the comparison.

⚠ The forecast field is real but only forward. Every response carries the keys `co2eq`,
`co2eq_forecast` and `deprecated`, but on a historical window `co2eq_forecast` is all null.
Checked on a forward window (`2026-09-16` to `2026-09-18`) on 2026-09-16:

| Country | Actual non-null | Forecast non-null | Forecast range |
|---|---:|---:|---|
| `de` | 27 | 69 | 240–598 g |
| `se` | 27 | 69 | 22–23 g |
| `pl` | 27 | 69 | 376–697 g |

So the native forecast is populated for ordinary countries too, and it reaches past DE, FR
and ES. Those 69 points are about 17 hours. `FORECASTS.md` §3 measured 8 h to 57 h per
country on 2026-09-17, so the horizon must come from the returned array. The collector must
fetch history and forecast on separate windows and store them as separate series.

#### (b) A second source exists for the same country from the same vendor

`energy-charts` serves `uk`, and NESO serves GB. The two use different methods on the same
grid. `energy-charts` reported a 122.5 g mean for 2026-09-10; NESO publishes its own value
for the same period. That is a free, direct, single-country measurement of vendor
disagreement, which is what this program is built to quantify. The same pair exists for FR
(`energy-charts` against RTE éCO2mix) and for DK (`energy-charts` against Energinet).

#### (c) The region count rises from 4 to 36, and the sub-national detail becomes an input

The unit of analysis is the country. Decided 2026-09-16, recorded in `sources/zones.json`,
explained in [§9](#9-zone-model). The sub-national zones below are not separate entities in
this program. They are what a country value is aggregated *from*.

Electricity Maps publishes its zone list without authentication. The call on 2026-09-16
returned 71 European zone keys, 61 of them TIER_A, and 33 of those are sub-national
bidding zones:

```
DK-DK1 DK-DK2 ES-CE ES-CN-FV ES-CN-GC ES-CN-HI ES-CN-IG ES-CN-LP ES-CN-LZ
ES-CN-TE ES-IB-FO ES-IB-IZ ES-IB-MA ES-IB-ME ES-ML FR-COR GB-NIR IT-CNO
IT-CSO IT-NO IT-SAR IT-SIC IT-SO NO-NO1 NO-NO2 NO-NO3 NO-NO4 NO-NO5
PT-MA SE-SE1 SE-SE2 SE-SE3 SE-SE4
```

Norway and Sweden split into 5 and 4 price zones. Italy splits into 6. Denmark into 2. NESO
does the same for GB with 14 distribution regions.

Seven countries need a weighted roll-up: DK, ES, FR, IT, NO, PT and SE. A direct read does not
serve them. See [§9](#9-zone-model).

---

## 1. Carbon intensity — time series

### 1.1 energy-charts `/co2eq` (Fraunhofer ISE)

- Verified live, 2026-09-16. `GET https://api.energy-charts.info/co2eq?country=de&start=2026-09-10&end=2026-09-11` → HTTP 200.
- Gives: `co2eq`, `co2eq_forecast`, `deprecated`. Quarter-hourly to hourly, by country.
- Licence: CC BY 4.0, attribution to energy-charts.info. Traced 2026-09-18 to
  `GET https://api.energy-charts.info/openapi.json`, `info.description`, section *Data License*:
  "Unless stated otherwise, the data provided by the Energy-Charts API is licensed under the
  CC BY 4.0 license. Proper attribution to Energy-Charts.info as the source is required."
  `info.license` points to `https://energy-charts.info/publishing-notes.html`.
  The `llms-full.txt` documentation states no licence, and the `/price` endpoints carry a
  different licence for each bidding zone. The rule applies to each endpoint on its own.
- Cost: free. No key.
- Rate limit: 2 requests per minute, burst 4, per IP and per endpoint, adjusted down
  under server load. Honour `Retry-After` on HTTP 429.

This endpoint is undocumented and has no v2 form. Re-verified on 2026-09-16:

- `GET /v2` returns a catalogue of 19 endpoints. None is carbon-related.
- `GET /openapi.json` returns 37 paths. None is carbon-related.
- `GET /v2/co2eq` returns HTTP 404, while `GET /co2eq` returns HTTP 200 with
  `deprecated: false`.

Every other energy-charts endpoint has both a legacy and a `/v2/` form. This one has only
the legacy form and no specification. There is no published emission-factor table, no
statement of scope, and no version. The program must treat it as a source that can
disappear without notice, and must never depend on it alone.

Accounting basis: almost certainly production-based. energy-charts exposes cross-border flows
as separate endpoints (`/cbet`, `/cbpf`), which implies `/co2eq` does not flow-trace imports.
The name implies CO₂-equivalent, so the factors are probably lifecycle. The publisher
documents none of this, so both readings are inferences.

#### What the full backfill measured on 2026-09-17

The collector read every country from 2015-06-01 to 2026-09-17. On 2026-09-22 the `record`
table of `store/atlas.duckdb` holds 5,105,674 actual rows from this source, and the
`record_current` view holds 5,105,530 actual rows. The captured forecast rows are not in
either total. The 144-row difference is superseded revisions. `REFERENCE.md` §9b
counts the current rows, so quote 5,105,530 unless you mean every revision ever written.
Two results change what this register can claim.

⚠ A country that returns a value for today can hold no history. The probe of 2026-09-16
called every country code for one day, and 34 answered. That probe tests the present day
only. Four of the 34 give little or nothing:

| Country | What the backfill got |
|---|---|
| MD Moldova | 527 records, 2026-08-23 to 2026-09-14, and nothing before. 2,981 days fail and 1,146 days return an empty list. The probe value of 296.8 g for 2026-09-10 now has a series behind it: 24 records of that day, with a mean of 289.4 g. The store holds 23 days of MD. |
| CY Cyprus | 2015-07-25 to 2017-06-10, then nothing until 2026-08-23. 27,925 records in total. 3,516 days fail. Not usable as a time series. |
| GE Georgia | 2021-12-25 to 2025-04-20, with holes, then nothing until 2026-08-23. 28,975 records in total. 548 days fail. |
| XK Kosovo | 2021-08-22 onward, 44,526 records. 16 days fail. Usable from 2021. |

The other 30 countries run from their own first day to the newest day. 26 of them start on
2015-05-31. The later starts are ME 2015-06-08, RS 2016-12-22, BA 2017-02-28 and
HR 2018-12-31. Two of the 30 are thin: ME holds 86 % of the days of its span, and GB 94 %.
MD held no record until 2026-08-23, so this source covered 33 countries then, and the counts
of `REFERENCE.md` §9 are those 33. It covers 34 since that day, counted on 2026-09-23.

The API answers HTTP 500 for some periods and HTTP 200 for other periods of the same
country. It is not a rate limit and not a size limit. `dk` for 2024 returns 8,784 points
in 2 seconds. `dk` for 2015 to 2026 fails after 17 seconds.

A collector that makes one request for the whole history loses the whole country. The atlas
collector splits a window on a 5xx status and keeps the good halves. See
`REFERENCE.md` §6.

#### What the portal found on 2026-09-17

⚠ Georgia sits at a floor of 3.0 gCO₂eq/kWh for whole months. The season panel of the
portal shows a swing of 80.8× between the months of Georgia. The cause is not thin
coverage. 8 months, from 2022-05 to 2024-07, hold between 665 and 744 records each, which is
89 % to 100 % of their hours. The lowest of the 8 holds 89 %, so they are not all complete
months. Each one of them holds a mean below 8 g, and a minimum of exactly 3.0 g.

| Month | Records | Mean | Lowest | Median |
|---|---:|---:|---:|---:|
| 2022-05 | 744 | 3.19 | 3.0 | 3.2 |
| 2023-05 | 741 | 4.03 | 3.0 | 3.2 |
| 2024-05 | 665 | 3.19 | 3.0 | 3.2 |

No lifecycle factor table gives 3 g to a national grid. Hydro alone is near 24 g in IPCC
AR5 Annex III. The next lowest month from energy-charts is CH at 10.9 g, from the same
publisher and in the same unit. That value is plausible for Swiss hydro and nuclear. RTE
reports French
months as low as 8.5 gCO₂/kWh, in another unit and on another basis, so that figure does not
rank against these two. So the Georgian series is an artefact of the model of the
publisher, and not a measurement of Georgia.

A guard cannot catch it, because 3.0 g is inside every sensible range band. Only a second
source can score it. See §8 and the Source discrepancy tab of the portal.

### 1.2 NESO Carbon Intensity API (Great Britain)

- Verified live, 2026-09-16. Three endpoints, all HTTP 200, no key:
  - `/intensity` → `{"forecast":95,"actual":135,"index":"moderate"}` for the half hour from 05:00Z.
  - `/generation` → the fuel mix as percentages: `biomass 11.4, coal 0, imports 7.6, gas 27.4, …`
  - `/regional` → the same for 14 distribution regions (`North Scotland`, and so on).
- Published methodology, published factors, open source on GitHub, operated by the system
  operator. Every step behind a value can be traced.
- Includes interconnector imports, transmission and distribution losses, and embedded wind
  and solar. Most sources omit at least one of the three.
- Licence: none is recorded. `sources/sources.json` sets `licence_status` to `not recorded`
  for this entry, and the four licence keys stay absent on purpose. Read the publisher terms
  before any external publication.

⚠ Direct/operational factors, not lifecycle. Nuclear, wind, solar and hydro are all
zero. The register predicted that GB reads 20 to 40 g below a lifecycle series such as
energy-charts. The measurement of 2026-09-18 is 71.9 g on the mean of 69,432 shared hours.
See §0.2. The scope of the factors does not explain the whole gap.

Biomass is the largest single uncertainty: consumption-based estimates put it at
120 ± 120 gCO₂/kWh, and GB burns a lot of it.

⚠ Provenance must be kept. `/intensity` returns `forecast` and `actual` as separate
fields. The previous pipeline wrote `actual or forecast`, which discards which one was used
and also misreads a legitimate zero as missing. Store both fields.

### 1.3 Electricity Maps

- Zone list verified live, 2026-09-16: `GET https://api.electricitymap.org/v3/zones` →
  HTTP 200, no key. 71 European zone keys, 61 TIER_A.
- The data API requires a token: `GET /v3/carbon-intensity/latest?zone=DE` → HTTP 401
  `"Invalid auth-token"`.
- The one source with consumption-based flow tracing (Tranberg et al. 2019, peer
  reviewed) and one method applied to every zone. That property is what removes
  cross-source bias from a multi-country comparison.
- A free data portal publishes historical CSV by hour, day, month and year. The web pages
  return HTTP 403 to automated fetches, so the download stays a manual step.
- The free API tier covers a limited set of zones and history. Commercial access is about
  €4,500 per year.

Verdict: take the free tier and the portal CSV, and use it as the reference frame against
which the other sources are compared.

### 1.4 Energinet Energi Data Service (Denmark)

- Verified live, 2026-09-16. `GET https://api.energidataservice.dk/dataset/CO2Emis?limit=3` →
  HTTP 200, no key. Returns 5-minute records per price area (`DK1`, `DK2`).
- 5-minute resolution, the finest in this register. Useful for a separate question:
  how much signal does quarter-hourly sampling lose?
- `ProductionConsumptionSettlement` also returns HTTP 200 and gives settled production and
  consumption per price area.
- Free, open, no authentication. That is a statement about access only.
- Licence: none is recorded. `sources/sources.json` sets `licence_status` to `not recorded`
  for this entry. Read the publisher terms before any external publication.

### 1.5 RTE éCO2mix through ODRÉ (France)

- Verified live, 2026-09-16.
  `GET https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-national-tr/records` →
  HTTP 200, no key. 15-minute records, `total_count` 7,584 in the real-time dataset.
- Two datasets: `eco2mix-national-tr` (real time) and `eco2mix-national-cons-def`
  (consolidated and definitive). The second is the one to use for history.
- Gives consumption, generation per source, CO₂ rate, and cross-border exchanges.
- Licence: Licence Ouverte v2.0 (Etalab), at
  `https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf`.
  Traced 2026-09-18 to `metas.default.license` of the dataset. Attribution: RTE / ODRE.
- The ground truth of the TSO for France. So it is the check on the FR series. The whole
  previous conclusion rested on that series.

### 1.6 Elia Open Data (Belgium) — two bases, one dataset

> The register entry was wrong until 2026-09-18. It filed this source under
> *generation mix* and gave one line of verification. The dataset that the entry named,
> `ods192`, is titled *"Production-Based CO2 Intensity and Consumption-Based CO2 Intensity
> Belgium"*. It is a carbon-intensity source, and it answers the question the programme asks.
> The entry is now two entries: `elia-co2-production` and `elia-co2-consumption`.

- Verified live, 2026-09-18. `GET /ods192/exports/json?select=datetime,production,consumption`
  → HTTP 200, 15,279 rows and 1.3 MB in one request, no key.
- Three fields: `datetime` (the start of the interval), `production`, `consumption`. One value
  each hour. The publisher refreshes it daily, to the day before the fetch.
- The publisher states the unit in the field annotation of each column: `gCO2eq/kWh`. That
  is the unit of energy-charts, so a comparison of the two needs no conversion.
- The publisher states the basis of each column, in its own words:
  - `production`: "the amount of carbon dioxide equivalents emitted per unit of generated
    electricity … Cross-border flows are not taken into account in the calculation."
  - `consumption`: "… per unit of consumed electricity … Cross-border flows are taken into
    account in the calculation."
- The two quotations differ in one condition. The production column leaves the cross-border
  flows out, and the consumption column counts them. That condition is the difference between
  the two bases.
- The publisher states no scope. The unit says CO₂ equivalents, so the number counts more than
  CO₂. It does not say lifecycle, and it does not say direct combustion.
- Licence: the catalogue metadata gives Elia Open Data Licence at
  `https://opendata.elia.be/pages/licence`. That page renders from JavaScript, so the terms
  were not read character by character. Read it in a browser before any external publication.
- Same OpenDataSoft platform as ODRÉ, so the RTE collector was the template.

Why the source gives two entries. The key of the record table is (country, source_id,
metric, fuel, ts_utc, kind, run_at). `basis` is not in that key. So two values of one hour
under one source id collide. The store then writes the second one as revision 2 of the
first. A revision means "the publisher corrected the number", and that is false here.

Each column gets its own source id, its own entry and its own request. The portal then shows
them as two sources on the Source control, and it never averages them.

#### A value of exactly 0.0 is an outage, and not a clean hour

Measured on 2026-09-18 across the whole series:

| What | Count |
|---|---|
| Rows in the export | 15,279 |
| Rows with 0.0 in `production` | 284 |
| Rows with 0.0 in `consumption` | 326 |
| Rows with 0.0 in both columns | 284 |
| Rows with 0.0 in `consumption` only | 42 |

Every production zero is also a consumption zero. The store keeps 14,995 production rows and
14,953 consumption rows, so the consumption series lost 326 values and the production series
lost 284. `REFERENCE.md` §9c counts the same drops.

The zeros come in blocks. The blocks repeat at 18:00 to 21:00 UTC on days that follow each
other — 2025-12-05 to 09, and 2026-09-11 to 16. That is a fixed local evening window. Three
measurements say the zeros are not measurements:

1. energy-charts reports a mean of 218.5 gCO₂eq/kWh for those same 284 hours, and it never
   reports below 82.4.
2. The mean of energy-charts across the whole period is 203.9, so the zero hours are dirtier
   than the mean.
3. The smallest value that Elia itself publishes above zero is 17.4 gCO₂eq/kWh.

⚠ A zero is worse than a gap. Guard 2 accepts it, because `INTENSITY_MIN` is 0.0 and a true
zero is possible for another country. A gap shows as "no record" on the portal. A zero becomes
the cleanest hour of the day, in the hours when the grid is at its dirtiest. It then moves the
answer of the workload calculator to the wrong hour.

The collector drops every zero and writes the reason in the run row. It stops the whole payload
only above a share of half (`ZERO_SHARE_LIMIT`). A share that high points to a change at the
publisher.

#### Two more limits

- The series has holes. 15,279 hours of the 17,204 between the first and the last record.
  The largest hole runs 70 days, from 2025-12-10T18:00Z to 2026-02-18T23:00Z. A second runs
  10 days from 2025-10-30.
- The history is short. The first record is 2024-09-30T22:00Z. That is 2 years, against
  11 years of energy-charts. Compare the two on the period that both hold.
- `ods191` carries the same title, 0 records and no declared fields. Probed 2026-09-18.
  `ods192` is the live one.

What this source measured is in [§0.3](#03-belgium-separates-the-basis-from-the-method).

### 1.7 ENTSO-E Transparency Platform

- Probed live, 2026-09-16: `GET https://web-api.tp.entsoe.eu/api?documentType=A75…` →
  HTTP 401 with an IEC 62325 acknowledgement document. The endpoint is alive and the
  request shape is right. The token is the only part that is absent.
- Free. The token needs a registered account and an email to `transparency@entsoe.eu` with
  subject "RESTful API access". Granted in about 3 working days.
- Gives actual generation per production type (`documentType=A75`), load, and physical
  cross-border flows, for every European bidding zone, as XML market documents.
- This is the upstream that both Fraunhofer and Electricity Maps consume.

What ENTSO-E adds. ENTSO-E generation and a published emission-factor set (§3) let the
program compute its own carbon intensity. That turns "the vendors disagree" into "here is
how much of the disagreement is method and how much is physics". No other source makes that
decomposition possible. The request for the token is item 1 of §8.

### 1.8 WattTime

> Not in the register since 2026-09-18. See §0.1. This section is the research only.

- Documented only. A free tier exists, limited; commercial above it.
- Gives marginal emission factors. It answers "what does one more kWh cause?"
- Marginal factors cannot be directly measured, so they cannot be validated. They are
  unsuitable for Scope 2 reporting. A 65-grid comparison found Electricity Maps (average,
  flow-traced) and WattTime (marginal) statistically different with very low correlation.
- Keep it as a fourth axis of disagreement only. It is unfit for a reporting series.

### 1.9 emissions.dev

- Verified live, 2026-09-16. `GET https://api.emissions.dev/` → HTTP 200,
  `{"name":"emissions.dev API","api_version":"v1","release":"1.0.6","status":"operational"}`.
  The electricity path in the search result was wrong; the correct one is listed in the root
  response.
- Gives annual grid intensity for 100+ countries, all 50 US states, and AWS, GCP and Azure
  region factors. Every response carries a `source_trail` naming the dataset used.
- It is an aggregator of other datasets. Its own stated sources are Ember, the EEA and
  Electricity Maps, all of which are already in this register. Annual resolution only.
- Use it for one thing: a cross-check of the cloud-region mapping. Do not treat it as an
  independent source, because it is not independent.

---

## 2. Generation mix by production type

The user requirement is "what type of energy each country generates and in what
proportion". Four sources, at four resolutions.

### 2.1 energy-charts `/v2/public_power` — the primary

- Verified live, 2026-09-16 (catalogue read from `GET /v2`).
- Net public electricity production in MW, one series per production type, plus
  `renewable_share_of_load`.
- 37 country codes accepted, plus the aggregates `eu` and `all`:

```
at ba be bg ch cy cz de dk ee es fi fr ge gr hr hu ie it lt lu lv md me mk
nl no pl pt ro rs se si sk ua uk xk   (plus the aggregates eu and all)
```

- The same envelope, licence and rate limit as `/co2eq`. This endpoint is documented. It has
  a v2 form, and it declares its units and resolution inline.
- More endpoints in the same catalogue:
  - `/v2/installed_power` — the capacity per production type.
  - `/v2/total_power` — it includes the industrial self-supply.
  - `/v2/cbet` and `/v2/cbpf` — cross-border trade and physical flows.
  - `/v2/public_power_forecast` and `/v2/ren_share_forecast` — the forecasts.
  - `/v2/solar_share`, `/v2/wind_onshore_share` and `/v2/wind_offshore_share`.
  - The daily average of each share.

The share endpoints matter for the seasonality requirement: `solar_share_daily_avg` over a
year is the seasonal curve of a solar-heavy country, directly, without derivation.

### 2.2 ENTSO-E `A75` actual generation per production type

The authoritative version of the same thing. It reports one value for each bidding zone, and
a country value is then a roll-up. Needs the token. See §1.7.

### 2.3 Eurostat `nrg_cb_pem`

- Verified live, 2026-09-16.
  `GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_cb_pem?format=JSON&geo=DE&lastTimePeriod=2` →
  HTTP 200, JSON-stat, `"updated":"2026-09-15T23:00:00+0200"`.
- Net electricity generation by type of fuel, monthly, official statistics.
- The `sinceTimePeriod` parameter rejected `2025M01`; use `lastTimePeriod` or the explicit
  `time` filter.
- Monthly is too coarse to schedule against. It is exactly right as the anchor. It says if
  the sub-hourly sources add up to the official national account over a year.

### 2.4 Ember

> Not in the register since 2026-09-18. It refuses without a key. See §0.1.

- Verified live, 2026-09-16. `GET https://api.ember-energy.org/` → HTTP 200.
  `GET /v1/carbon-intensity/monthly?entity_code=DEU…` → HTTP 403 `{"detail":"No API key set"}`.
  An OpenAPI schema is served at `/openapi.json` and Swagger docs at `/v1/docs`.
- Free, CC BY 4.0, key required. Yearly data back to 1985, monthly back to 2010, about 88
  areas with monthly detail.
- Gives generation by fuel (TWh), capacity (GW), emissions (MtCO₂), CO₂ intensity
  (gCO₂/kWh) and demand, in one consistent series.
- An anchor for annual and monthly figures, and heavily cited in policy work.

---

## 3. Emission factors — needed to compute our own intensity

> No factor set is in the register since 2026-09-18. A factor table is a table in a report,
> and not an endpoint. See §0.1. The chosen table must come back into the register on the day a
> generation-mix collector starts. A stored value must name the table that made it.

If the program computes carbon intensity from generation mix, it must state which factor set
it used. The choice moves the answer by more than most of the effects being studied.

| Set | What it is | Note |
|---|---|---|
| IPCC AR5 Annex III | The standard lifecycle medians per technology. | The default in most tools. AR5 GWP values. |
| UNECE 2022, *Carbon Neutrality in the UNECE Region* | Integrated lifecycle assessment of electricity sources, published March 2022. Gives nuclear at 5.1–6.4 gCO₂eq/kWh. | Newer than AR5 and more detailed on ranges. |
| IEA Life Cycle Upstream Emission Factors 2024 | Upstream fuel-supply emissions, with AR6 GWP. | AR6 alignment matters for ESRS reporting. |
| NESO published factors | Coal 937, French interconnector 53, Dutch interconnector 474, biomass 120 gCO₂/kWh. | Direct factors. Zero for nuclear, wind, solar and hydro. |
| Unnewehr et al. 2022 bottom-up set | Built from EU-ETS plant-level emissions matched to 595 fossil units, per European country. | The reference for how large the method gap is: country-level divergence from −19 % (Norway) to +53 % (Lithuania). |

⚠ Unnewehr et al. compared three defensible methods on Norway. They got IEA 29.1, top-down
19.45 and bottom-up 16.31 gCO₂/kWh, a 1.8× spread with no method wrong. The program must
report an uncertainty band around every absolute figure. The fixed ±30 g band of the previous
investigation is the wrong shape. The band must scale with the level, because 1.8× of a
coal-heavy country is hundreds of grams.

---

## 4. Annual reference series — for validating the sub-hourly sources

> Our World in Data is the only one of these in the register since 2026-09-18. EEA,
> ECON-PowerCI and Ember were removed. See §0.1.

| Source | Gives | Access |
|---|---|---|
| EEA, greenhouse-gas emission intensity of electricity generation | Official per-country intensity for EU states, from UNFCCC national submissions and Eurostat energy balances. 1990, 2000, 2010, 2024 with early estimates. | Free, web download |
| Our World in Data, `carbon-intensity-electricity` | Verified live, 2026-09-16. The grapher CSV endpoint returns HTTP 200 with no key, per country and year. It carries an `original_year` column that shows how old each figure is. | Free CSV, CC BY |
| ECON-PowerCI (Nature *Scientific Data*, 2025) | Near-real-time daily consumption-based carbon intensity for Europe, net imports accounted, peer reviewed. | Free |
| Ember yearly and monthly | See §2.4. | Free, key |

The EEA and OWID series are annual, so they cannot schedule anything. Their value is that
they are independent of every real-time vendor. If the program's own annual mean for a
country lands far from both, examine the pipeline first.

---

## 5. Cloud-region mapping

> Two entries below stay in the register since 2026-09-18: Google `region-carbon-info` and
> emissions.dev. IONOS, Cloud Carbon Footprint and Boavizta left it on the same day. The PUE
> of 1.39 stays in the portal calculator, and the IONOS report is its source. See §0.1.

Needed for the portal's comparison view, because the practical question is "which region
do I run in".

| Source | Gives | State |
|---|---|---|
| Google `region-carbon-info` | Grid carbon intensity and hourly CFE% for all Google Cloud regions, machine readable, in a public GitHub repository. Verified live 2026-09-16 (page fetched). | The best-documented of the three hyperscalers |
| emissions.dev | AWS, GCP and Azure region factors in one API. See §1.9. | Aggregator |
| IONOS Sustainability Report 2025 | PUE 1.39, 100 % renewable electricity. The datacentre parameters the previous work used. | PDF |
| Green Web Foundation `grid-intensity-cli` | Not data. A tool that already integrates WattTime, Ember and Electricity Maps behind one interface. | Not in the register. It wraps three vendor APIs |

Google, AWS and Azure use different methodologies, boundaries and vintages. A
cross-provider table is not a like-for-like comparison, and the portal must say so on the
panel.

⚠ A second limit applies to the whole program. An operator that buys 100 % renewable
electricity has a market-based Scope 2 of zero. The same renewable generation also sits
inside the location-based grid average that the program optimises against. Maji et al.
(2023) looked at 123 regions. They found that 66 % of renewable generation is
double-countable, which implies an error of 194 % in the worst case.

The error flatters the consumer. The defensible frame is 24/7 hourly-matched carbon-free
energy.

---

## 6. Sources that did not respond

> None of these is in the register since 2026-09-18. See §0.1. They come back when a probe
> answers, or when a key arrives.

Recorded so nobody repeats the try. All probed 2026-09-16.

| Source | Result | Reading |
|---|---|---|
| REE `apidatos.ree.es` (Spain) | HTTP 400, "The requested data is currently unavailable" | Endpoint shape looks right. Retry. |
| Terna (Italy) | HTTP 596 | Needs registration. |
| NED.nl (Netherlands) | HTTP 401 | Free key required. |
| Fingrid (Finland) | HTTP 403 | Free key required. |
| Electricity Maps web pages | HTTP 403 | Bot protection. Manual download. |
| Ember web pages | HTTP 403 | Bot protection. The API works. |
| ENTSO-E API guide page | HTTP 400 | Read the Postman collection instead. |
| Energinet `DeclarationEmissionHour` | HTTP 404, "dataset not found" | The dataset was renamed. Find the current name in the catalogue. |

---

## 7. Literature to read before the analysis is designed

| Work | Why |
|---|---|
| Unnewehr et al., *Open-data based carbon emission intensity signals for European countries — top down vs bottom up*, arXiv 2110.07999 | The method-gap numbers in §3. The closest existing work to this program. |
| Maji et al., *Untangling Carbon-free Energy Attribution and Carbon Intensity Estimation*, arXiv 2308.06680 | Double counting, 66 % / 194 %. |
| Tranberg et al. 2019, flow tracing | The basis of consumption-based accounting. |
| *Moving Beyond Marginal Carbon Intensity*, arXiv 2507.11377 | Marginal against average. |
| *The Sunk Carbon Fallacy*, SoCC 2024, arXiv 2410.15087 | Servers draw more than 30 % of peak power at 0 % use. |
| West et al., arXiv 2508.14625 (August 2025 preprint) | Temporal shifting of scientific workflows. States that low-variance regions show minimal gains. |
| *CarbonEdge*, arXiv 2502.14076 | Mesoscale spatial carbon-intensity variation. Directly relevant to the sub-national zones in §0(c). |
| Green Software Foundation SCI, ISO/IEC 21031 | The vocabulary to express results in. |

---

## 8. What to do next

1. Request the ENTSO-E token. It takes about 3 working days and it is the only
   item in this register with a lead time. `sources/sources.json` carries the entry as
   `key-required`.
2. ~~Write the NESO and the Energinet collector.~~ Done 2026-09-18. The RTE collector and
   the two Elia collectors were written on the same day. Every open source in the register
   that publishes a national carbon-intensity series is now collected. §0.2 and §0.3.
3. Download the Electricity Maps portal CSV manually for the target zones, because the
   pages block automated fetch.
4. ~~Decide the zone list.~~ Decided 2026-09-16: country level, 36 countries. See
   [§9](#9-zone-model) and `sources/zones.json`. Open sub-decision: confirm that load
   weighting is the wanted rule for the seven roll-up countries.
5. Decide the factor set for the program's own computed intensity, from §3. This decision
   must be recorded in `sources.json` and shown in the portal, because it moves every
   absolute number.

---

## 9. Zone model

Decided 2026-09-16. The unit of analysis is the country, and the list holds 36 of them. The
canonical list, with per-source mapping, is `sources/zones.json`. That file is authoritative;
this section explains it.

Identifiers are ISO 3166-1 alpha-2, uppercase. Two exceptions are recorded in the file:
`GB` means Great Britain, not the United Kingdom, because that is what every electricity
source actually reports; and energy-charts spells it `uk`, so the ingest maps `uk` → `GB`.

### 9.1 Why a country value is a transformation

Four incompatible geographies exist in the sources, and they do not nest:

| Geography | What it is | Sources that use it |
|---|---|---|
| Country | Political and statistical | energy-charts, Eurostat, EEA, Ember, OWID |
| Bidding zone | Market area with one clearing price | ENTSO-E, Energinet, Electricity Maps sub-national |
| Control area | TSO balancing responsibility | ENTSO-E |
| Distribution region | DNO licence area | NESO, 14 GB regions |

So a country value is often a transformation. Every stored value carries a granularity tag
that says which:

| Tag | Meaning |
|---|---|
| `native` | The source reports this exact country. No transformation. |
| `aggregated` | Rolled up from finer zones with a stated weighting. |
| `group` | The source reports one value for an area covering several countries. That value is replicated to each member. It is not a measurement of the country. |
| `proxy` | Borrowed from a different area. Last resort, needs a written justification. |

The portal must show a badge for `aggregated`, `group` and `proxy`, and the collapsible
source block must explain the transformation. A generated report must do the same in text.

### 9.2 Aggregating up, for DK, ES, FR, IT, NO, PT and SE

```
CI_country = Σ (CI_zone × load_zone) / Σ load_zone
```

Load-weighted by default. Generation-weighted where per-zone load is not published.

⚠ An unweighted mean of intensities must never be stored. Carbon intensity is a ratio, so it
carries no level of its own. An unweighted mean gives a sparse zone the same influence as the
zone carrying most of the national load. Sweden is the clearest case: `SE-SE3` carries Stockholm and
`SE-SE1` carries almost nothing. If neither load nor generation is available per zone, store
the zones and leave the country value null.

The member zones, the weight series and the `source_id` of the weight series are all
recorded with the value.

### 9.3 Replicating down, for multi-country areas

Where a source reports one value for an area spanning several countries, that value is
written to each member country and tagged `group`.

⚠ Two countries that share a group value are not independent. They must never be shown
as a comparison, and a ranking must collapse them into one row. A league table that puts
Germany and Luxembourg in two rows off one ENTSO-E series is reporting the same number
twice.

Three groups are recorded so far:

| Group | Members | Defined by | State |
|---|---|---|---|
| `DE-LU` | DE, LU | ENTSO-E bidding zone | pending verification |
| `SEM` | IE, GB-NIR | All-island market | pending verification |
| `EU` | EU member states | energy-charts `country=eu` | verified live, 278.2 g on 2026-09-10 |

⚠ The DE-LU conflict is a finding waiting to happen. Germany and Luxembourg share one
bidding zone, so one price and one physical grid. energy-charts reports them 488.0 and
303.4 gCO₂eq/kWh on the same day, a 185 g gap. Either energy-charts models
Luxembourg from something other than the grid it connects to, or the shared-zone
assumption is wrong. ENTSO-E settles it as soon as the token arrives.

### 9.4 What this costs

Collection cost scales with the number of sources. One energy-charts collector covers all 34
of its countries.

Measured on 2026-09-17, and cheaper than this section first estimated. One request carries
the full 11 years for a country with a clean history. The backfill of `/co2eq` for 34
countries took 2 hours 23 minutes. The run table holds 107 windows for it, because a 5xx
splits a window and each half is a new request. CY, GE and MD account for 53 of the 107.

The first estimate here was 3.4 hours, because it assumed monthly windows. The estimate for
`/v2/public_power` stays open until a `/v2/public_power` collector measures it. See
`REFERENCE.md` §9.

Electricity Maps is the exception. Its pages return HTTP 403 to an automated fetch. The CSV
download is manual, and so it is per zone. A limit to the countries that need it keeps
that cost down.

### 9.5 Where the discrepancy analysis can actually run

Two independent sources on the same country. All four are collected since 2026-09-18. The
shared hours are of 2026-09-23, and the `hours` field of `portal/data/pairs.json` holds the
count of today:

| Country | Source A | Source B | Source C | Shared hours |
|---|---|---|---|---|
| GB | energy-charts `uk` | NESO | — | 69,570 |
| FR | energy-charts `fr` | RTE éCO2mix through ODRÉ | — | 99,108 |
| DK | energy-charts `dk` | Energinet, aggregated from DK1 and DK2 | — | 85,195 |
| BE | energy-charts `be` | Elia `ods192` production-based | Elia `ods192` consumption-based | three pairs, below |

Belgium holds three sources, so it holds three pairs. Each pair shares its own count of hours.
energy-charts against Elia production is 15,093. energy-charts against Elia consumption is
15,051, and Elia production against Elia consumption is 15,051.

Belgium is the only country in this table that can separate the basis from the method. Its
two Elia series share a publisher, a unit, a scope and a factor table. `pairs.json` marks that
one pair `kind` `basis`, and every other pair `method`. The measurement is in `REFERENCE.md`
§9c, and [§0.3](#03-belgium-separates-the-basis-from-the-method) says what it means for this
register.

This list grows when the ENTSO-E token arrives. ENTSO-E is now the only route to a second value
for ES, IT, NL and FI, because their national sources left the register on 2026-09-18. See
§0.1. The other 30 countries in the store have one source each, counted on 2026-09-23.
