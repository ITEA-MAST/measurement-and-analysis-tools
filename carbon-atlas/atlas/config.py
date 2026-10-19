"""Paths, constants and the two register files.

This module makes no network request and opens no database. It is safe to import
from any other module.

The registers are the single definition of a source and of a country. No module
writes a URL or a country list of its own. See `README.md`, rule 1.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

# --- Paths -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

STORE_DIR = Path(os.environ.get("ATLAS_STORE", ROOT / "store"))
DB_PATH = STORE_DIR / "atlas.duckdb"
RAW_DIR = STORE_DIR / "raw"
LOG_DIR = STORE_DIR / "log"
TMP_DIR = STORE_DIR / "tmp"
LOCK_PATH = STORE_DIR / "atlas.lock"

PORTAL_DATA_DIR = ROOT / "portal" / "data"

SOURCES_JSON = ROOT / "sources" / "sources.json"
ZONES_JSON = ROOT / "sources" / "zones.json"

# --- Constants ---------------------------------------------------------------

# The second process waits this long for the lock. Then it stops with exit
# code 2 and one line in the log. It writes no run row, because the store file
# belongs to the other process. RUNNING.md section 5.
LOCK_WAIT_SECONDS = 600

# `atlas daily` always collects these last days again. An overlap catches a
# correction from the publisher.
RECENT_DAYS = 2

# A day with status `empty` is final after this age. A younger empty day is
# collected again, because the publisher can still fill it.
EMPTY_RETRY_DAYS = 7

# `atlas daily` tries a failed day again only while the day is this young.
# `atlas backfill` tries every failed day again. A source that answers with a
# server error for a period of 2017 must not take requests from the daily run.
DAILY_RETRY_FAIL_DAYS = 30

# The number of tries for one request. REFERENCE.md section 6.
HTTP_TRIES = 3
HTTP_TIMEOUT_SECONDS = 180

# Guard 2 has two bands. REFERENCE.md section 6.
#
# The store band. A value outside it does not go in the store.
INTENSITY_MIN = 0.0
INTENSITY_MAX = 1500.0

# The absurd band. A value outside THIS band is a unit error or a new factor
# table, and not a defect of one point. Values 1000 times too large land here.
INTENSITY_ABSURD_LOW = -50.0
INTENSITY_ABSURD_HIGH = 5000.0

# The share of absurd points that stops the whole payload.
OUT_OF_RANGE_LIMIT = 0.01

# Why two bands. The forecast numbers are the measurement of 2026-09-17, and
# the store numbers are the measurement of 2026-09-23.
#
# energy-charts publishes a small negative intensity in the Lithuania forecast.
# 8 of 98 points, from -0.9 to -14.6 gCO2eq/kWh, beside a curve that reaches
# 81.7 g. That is a modelling artefact near zero. The actual series of Lithuania
# holds no negative value. No stored energy-charts actual value of the 5,119,413
# in the store is below 3.0 g. That distance is what the two bands need: the
# artefact sits near zero, and the data of that publisher starts at 3.0 g.
#
# ⚠ The floor of 3.0 g is true of energy-charts. It is not true of the store.
# The store holds 6,586,007 actual rows, and the smallest value of all of them
# is 0.0. 6 rows hold exactly 0.0, and all 6 are `neso-carbon-intensity` GB. The
# smallest stored actual value above zero is 3.0 g. A query that ranks the store
# by the lowest value gets one of those 6 zeros, and not 3.0 g.
#
# The 6 zeros change nothing in the band design. They are an outage of the
# publisher, and the two bands accept them, because `INTENSITY_MIN` is 0.0 and a
# true zero is possible for another grid. `zero_guard()` in
# `atlas/collectors/base.py` is the guard that stops the next one. REFERENCE.md,
# section *6 records hold 0.0, and all 6 are NESO GB*.
#
# With one band and a 1 % share, that payload stops, and Lithuania loses its
# forecast curve at every snapshot, for ever. With two bands the program drops
# the 8 points, keeps the 90, and writes the reason in the run row. A unit
# error still stops the payload, because it lands outside the absurd band.

# A value that moves less than this is the same value, and it makes no revision.
VALUE_EPSILON = 1e-9

# The CA file for the HTTP client. httpx uses certifi when this is empty.
# Set it to the CA file of the proxy on a machine that breaks TLS.
CA_BUNDLE = os.environ.get("ATLAS_CA_BUNDLE", "")


def ensure_dirs() -> None:
    """Make the store directories. It is safe to call this many times."""
    for path in (STORE_DIR, RAW_DIR, LOG_DIR, TMP_DIR, PORTAL_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)


# --- The registers -----------------------------------------------------------


@lru_cache(maxsize=1)
def _sources_file() -> dict:
    return json.loads(SOURCES_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _zones_file() -> dict:
    return json.loads(ZONES_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sources() -> dict[str, dict]:
    """The source register, keyed by `id`."""
    return {entry["id"]: entry for entry in _sources_file()["sources"]}


def source(source_id: str) -> dict:
    """One source register entry. It raises `KeyError` for an unknown id."""
    try:
        return sources()[source_id]
    except KeyError:
        raise KeyError(f"source_id {source_id!r} is not in {SOURCES_JSON}") from None


def requests_per_minute(source_id: str) -> float:
    """The published rate limit of a source. The default is 2 requests."""
    limit = source(source_id).get("rate_limit") or {}
    return float(limit.get("requests_per_minute", 2))


@lru_cache(maxsize=1)
def countries() -> list[dict]:
    """The 36 country entries of `sources/zones.json`, in file order."""
    return list(_zones_file()["countries"])


@lru_cache(maxsize=1)
def countries_by_iso() -> dict[str, dict]:
    return {entry["iso"]: entry for entry in countries()}


def country(iso: str) -> dict:
    """One country entry. It raises `KeyError` for an unknown ISO code."""
    try:
        return countries_by_iso()[iso.upper()]
    except KeyError:
        raise KeyError(f"country {iso!r} is not in {ZONES_JSON}") from None
