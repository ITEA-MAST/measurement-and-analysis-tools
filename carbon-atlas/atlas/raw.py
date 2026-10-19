"""The raw payload on disk.

The program keeps the bytes that the API returned, gzipped, with a sha256.
Every number traces back to one of these files. `atlas verify` reads each file
again and compares the hash with the `raw_ref` of the row. REFERENCE.md
section 3.

`atlas rebuild` reads these files again and makes a new DuckDB file from them,
with no network request. `atlas/rebuild.py` holds the command, and its
docstring states what a rebuild reproduces exactly and what it can not.

The path is `store/raw/<source>/<yyyy-mm>/<yyyymmddThhmmssZ>-<country>.json.gz`.
A forecast snapshot writes `<country>-snap` in the place of the country, so
every directory name is a source id. The `raw_ref` in a record is
`<relative path>#sha256:<hex>`.

⚠ Older code gave a snapshot a directory of its own, and a plain file name.
So `store/raw/energy-charts-co2eq-snap/` and
`store/raw/neso-carbon-intensity-snap/` are also on disk, and a directory name
there is not a source id. A reader of the tree must accept both forms.
`RUNNING.md` section 4 and `atlas/rebuild.py` section 5 say the same.
"""

from __future__ import annotations

import gzip
import hashlib
import re
from datetime import datetime
from pathlib import Path

from . import config

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def write(source_id: str, country: str, payload: bytes, at: datetime) -> str:
    """Write one payload and return its `raw_ref`."""
    config.ensure_dirs()
    digest = hashlib.sha256(payload).hexdigest()
    folder = config.RAW_DIR / _SAFE.sub("-", source_id) / at.strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{at.strftime('%Y%m%dT%H%M%SZ')}-{_SAFE.sub('-', country)}.json.gz"
    path = folder / name

    # Two payloads in one second get a counter, so no file is lost.
    counter = 1
    while path.exists():
        counter += 1
        stem = name[: -len(".json.gz")]
        path = folder / f"{stem}-{counter}.json.gz"

    with gzip.open(path, "wb", compresslevel=6) as handle:
        handle.write(payload)

    return ref_of(path, digest)


def ref_of(path: Path, digest: str) -> str:
    """The `raw_ref` of one payload: the relative path and the sha256.

    `write` and `atlas rebuild` both call this, so the two spell a reference in
    one way. The path is relative to `config.STORE_DIR`, and it uses forward
    slashes on every platform.
    """
    relative = path.relative_to(config.STORE_DIR).as_posix()
    return f"{relative}#sha256:{digest}"


def read(raw_ref: str) -> bytes:
    """Read a payload back, and compare its hash with the one in the `raw_ref`.

    It raises `ValueError` when the two do not agree. A `raw_ref` with no hash
    gets no check.
    """
    relative, _, tail = raw_ref.partition("#sha256:")
    path = config.STORE_DIR / relative
    with gzip.open(path, "rb") as handle:
        payload = handle.read()
    digest = hashlib.sha256(payload).hexdigest()
    if tail and digest != tail:
        raise ValueError(f"{path} does not match its hash in the record")
    return payload


def path_of(raw_ref: str) -> Path:
    relative = raw_ref.partition("#sha256:")[0]
    return config.STORE_DIR / relative
