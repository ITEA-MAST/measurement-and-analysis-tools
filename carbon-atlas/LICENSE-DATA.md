# Licence of the collected data

The `LICENSE` file covers the code. It does not cover the data. This file covers the data in
`store/` and in `portal/data/`, and any copy of a number that came out of them.

Copyright 2026 Wirtek A/S, for the parts named below.

## The short form

| Part | Terms |
|---|---|
| The database: the selection of sources, the country model, the record schema, the roll-up rules, and the derived fields that this program computes | CC BY 4.0 |
| Each collected series | The terms of its publisher. `NOTICE.md` holds the table |
| The raw payloads in `store/raw/` that this repository ships | The terms of the publisher of each one. The next section names all 5 directories |
| The Great Britain series from NESO, and the Denmark series from Energinet | Terms not recorded. Do not redistribute them outside Wirtek. They are not in this repository |

Attribution for the database: carbon-atlas, Wirtek A/S, CC BY 4.0. Give this attribution, and
also the attribution that each publisher asks for. It does not replace it.

## What this repository redistributes

The repository ships raw payloads. That is a redistribution of the data of 3 other publishers,
and this section states the terms of each one. Counted on 2026-09-23: 223 files under
`store/raw/`, 32.0 MB in the working tree and 20.9 MB to download, in decimal MB. A payload is
the bytes as the publisher served them, gzipped, with no change.

| Directory | Publisher and data | The terms of the redistribution | Files |
|---|---|---|---|
| `store/raw/energy-charts-co2eq/` | Fraunhofer ISE, energy-charts `/co2eq`, 34 countries from 2015-05-31 | CC BY 4.0. Name Energy-Charts.info as the source. | 145 |
| `store/raw/energy-charts-co2eq-snap/` | The same publisher and the same endpoint. The captured forward forecast curves. | CC BY 4.0. The same attribution. | 36 |
| `store/raw/rte-eco2mix-odre/` | RTE, eCO2mix national, France from 2011-12-31, through ODRÉ | Licence Ouverte v2.0 (Etalab). Name RTE / ODRE. | 36 |
| `store/raw/elia-co2-production/` | Elia, dataset ods192, Belgium, production basis, from 2024-09-30 | Elia Open Data Licence. Name Elia Open Data. | 3 |
| `store/raw/elia-co2-consumption/` | The same dataset, consumption basis. The two directories hold the same bytes. | Elia Open Data Licence. The same attribution. | 3 |

`NOTICE.md` holds the exact attribution string of each publisher and the URL of each licence.
A reuser of these payloads owes the publisher the same attribution that a reuser of the
database owes. The payload is the data of the publisher, and not a work of this program.

⚠ Nobody read the Elia licence text word by word. The probe read the licence name from the
catalogue metadata of dataset ods192, and the licence page renders from JavaScript. Read that
page in a browser before you rely on the two Belgian directories. `NOTICE.md` states the same.

### What this repository does not ship, and why

| Directory | Publisher and data | Files |
|---|---|---|
| `store/raw/energinet-eds/` | Energinet, Energi Data Service, Denmark from 2016-12-31 | 24 |
| `store/raw/neso-carbon-intensity/` | NESO, Carbon Intensity API, Great Britain from 2017-12-31 | 116 |
| `store/raw/neso-carbon-intensity-snap/` | The same publisher. The captured forecast curve. | 1 |

Those 141 files hold 15.8 MB. They are collected, they are complete, and `.gitignore` keeps
every one of them out of the repository.

⚠ The absence of the Denmark series and the Great Britain series is a licence decision, and
not a hole in the data. The live store holds 1,022,288 Energinet DK rows, 152,182 NESO GB
measurements and 203 NESO GB forecast points on 2026-09-23. Every one of them was collected
and none is absent. A reader who finds no Energinet file in a clone must not read that as a
collection failure. It is also not a statement about the quality of either series. The next
section gives the reason.

Denmark and Great Britain are still in a clone. energy-charts publishes both countries, and
energy-charts is licensed. What a clone loses is the second publisher of each: DK falls from
1,140,752 rows to 118,464 and GB from 337,176 to 184,994. `README.md` holds the table.

## Why CC BY 4.0

The strictest upstream term decides the terms this program can offer, and the upstream set
holds three licences:

1. energy-charts, from Fraunhofer ISE, publishes `/co2eq` under CC BY 4.0 and asks for
   attribution. 34 of the 34 countries in the store come from it, counted on 2026-09-23.
2. RTE publishes eCO2mix through ODRÉ under Licence Ouverte v2.0. Etalab states that this
   licence is compatible with CC BY 4.0.
3. Elia publishes ods192 under the Elia Open Data Licence, which asks for attribution.

All three ask for attribution and none of the three asks for a share-alike. So CC BY 4.0 is
the one licence that satisfies every publisher. It asks the reuser for nothing that the
publishers do not ask for already, and a research audience can act on it without a lawyer.
CC0 is more permissive, and it gives a right that this program does not hold: this program
cannot waive the attribution that energy-charts requires.

## What you must do to reuse the data

1. Name carbon-atlas and Wirtek A/S, and link the licence.
2. Name the publisher of every series you use. `NOTICE.md` gives the exact string for each.
3. Keep the `source_id` with the value. A carbon intensity without its source is not a
   measurement, because the publishers of one country disagree by 28 % to 53 % of the larger
   mean. `portal/data/pairs.json` states the range and the denominator. ⚠ A store rebuilt
   from the payloads of a clone measures 3 of those 5 pairs, and not the largest one. The DK
   pair and the GB pair need the two series above. `README.md` and `REFERENCE.md` §9b.
4. Keep the unit with the value. The store holds two units, gCO₂eq/kWh and gCO₂/kWh, and they
   are not the same quantity.
5. State the date you took the data. The store changes each day, and a correction can change a
   value that a publisher already served.

## The two series you must not redistribute yet

`sources/sources.json` marks NESO and Energinet `licence_status: not recorded`. Nobody read
the reuse terms of either publisher. Both are free to read and open to the public, and that
says nothing about the right to republish.

Until somebody reads those terms and records them in the register, the Great Britain series
and the Denmark series stay inside Wirtek. The portal shows the marker, so a reader can see
which two series carry it. The source register in a clone also names both sources, with 0 rows
behind them and the same marker.

`.gitignore` holds the rule. It denies every directory under `store/raw/` and allows one
source with one line, so a new source is private until a person states its terms. The 3
directories of NESO and Energinet are named again after the allow lines, because a rule that
comes later wins. Never use `git add -f` under `store/`, and read
`git status --porcelain --ignored -uall` before each `git add`.

⚠ A git history keeps a file after a delete. One Energinet payload or one NESO payload in one
commit costs a history rewrite. That is the failure to avoid above every other one here.

To publish either series:

1. Read the reuse terms of the publisher.
2. Record them in `sources/sources.json` and in the table of `NOTICE.md`.
3. Add the `!store/raw/<source>/` line to `.gitignore`, above the 3 named directories.
4. Add the directory to the redistribution table of this file.

## The Wirtek brand assets

`portal/assets/` is not data and this file does not cover it. See `LICENSE`.
