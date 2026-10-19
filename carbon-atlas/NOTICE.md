# NOTICE

carbon-atlas collects grid-carbon data from other publishers. Every record keeps the terms of
its publisher. This file names those publishers and the attribution that each one asks for.

`sources/sources.json` holds the same facts for each source, with the probe that read them.
This file is the short form.

Part of the data is in the source tree. `.gitignore` denies everything under `store/` and
`portal/data/`, and it allows the raw payloads of the 5 directories whose reuse terms are
recorded. So this repository redistributes the data of 3 publishers, as the bytes they served.
`LICENSE-DATA.md`, section "What this repository redistributes", names every directory and the
terms of each one.

The terms below apply to those payloads, to any copy of `store/` and `portal/data/`, and to a
portal that shows them.

## Publishers of the collected data

Six register entries from five publishers give every record in the store. Two of the entries
belong to one Elia dataset, one entry for each accounting basis.

| Publisher | Data | Licence | Attribution to show | Licence terms | Terms verified |
|---|---|---|---|---|---|
| Fraunhofer ISE | energy-charts `/co2eq`, 34 countries | CC BY 4.0 | energy-charts.info | https://energy-charts.info/publishing-notes.html | 2026-09-18 |
| RTE (FR TSO), through ODRÉ | eCO2mix national, France | Licence Ouverte v2.0 (Etalab) | RTE / ODRE | https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf | 2026-09-18 |
| Elia (BE TSO) | ods192, Belgium, production basis | Elia Open Data Licence | Elia Open Data | https://opendata.elia.be/pages/licence | 2026-09-18 |
| Elia (BE TSO) | ods192, Belgium, consumption basis | Elia Open Data Licence | Elia Open Data | https://opendata.elia.be/pages/licence | 2026-09-18 |
| NESO (GB) | Carbon Intensity API, Great Britain | not recorded | not recorded | — | — |
| Energinet (DK TSO) | Energi Data Service, Denmark | not recorded | not recorded | — | — |

The first 4 rows are the redistributed ones. Their payloads are in `store/raw/`, in this
repository, under the licence of each row: 223 files on 2026-09-23. A reuser of those files
owes the publisher the attribution of the row. That is the same attribution that a reuser of a
number owes. The last 2 rows are collected and not redistributed. Their payloads stay on disk
inside Wirtek.

## What the recorded terms ask for

energy-charts states, in `GET https://api.energy-charts.info/openapi.json`, section *Data
License*: "Unless stated otherwise, the data provided by the Energy-Charts API is licensed
under the CC BY 4.0 license. Proper attribution to Energy-Charts.info as the source is
required." A reader of the portal must see that attribution. A field in
`sources/sources.json` does not satisfy it.

The energy-charts rule is per endpoint. The `/price` endpoints carry a different licence for
each bidding zone. This repository collects `/co2eq` only.

The Elia licence page renders from JavaScript. The probe read the licence name from the
catalogue metadata of dataset ods192, and nobody read the licence text word by word. Read it
in a browser before you publish the Belgian series.

## Terms that are not established

Two publishers of collected data carry no recorded terms on 2026-09-23. `sources/sources.json`
marks both of them `licence_status: not recorded`, and it marks no other source that way:

- NESO Carbon Intensity API, the Great Britain series.
- Energinet Energi Data Service, the Denmark series. The register calls this source "free,
  open, no authentication". That sentence describes access. It says nothing about reuse.

Both series are collected, and neither is in this repository. `.gitignore` names the 3
directories that hold them, after the allow lines of the other sources, so a widened allow
line still leaves them out. Their absence from a clone is this licence decision, and not a
gap in the collection. `LICENSE-DATA.md` gives the row counts that a clone loses.

`sources/zones.json` also holds the Electricity Maps zone key of each country, as a mapping
table. The register records no licence for Electricity Maps.

Read the publisher terms, record them in `sources/sources.json`, then add them to the table
above. Do this before the data goes outside Wirtek.

## Brand assets

`portal/assets/` holds the Wirtek logo, the Wirtek symbol and two background images. They come
from the Wirtek brand pack and they are company property. This notice and the LICENSE file
give no right to them. Remove them before you reuse the portal.
