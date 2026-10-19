"""One writer at a time.

DuckDB gives write access to one process. `atlas daily` and `atlas snap` take
this lock file. The second process waits, and it stops after 10 minutes.
This is the only concurrency rule in the program. RUNNING.md section 5.

A lock file from a process that is dead is stale. One waiter renames it to a
private name, and only the waiter that the rename gives the file removes it.
The rename is atomic, so two waiters cannot both take the lock.

A lock file with no readable process id counts as held, and not as stale. A
live holder writes the file in two steps: it makes the file, and then it writes
the body. A waiter that reads the file between the two steps must not remove
it. The program removes such a file only after `UNREADABLE_GRACE_SECONDS`.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import config, log

# A lock file with no readable process id is held for this long. After this age
# it is stale. The value is much larger than the moment between the make step
# and the write step, and much smaller than `config.LOCK_WAIT_SECONDS`.
UNREADABLE_GRACE_SECONDS = 60


class LockBusy(RuntimeError):
    """Another process holds the lock, and the wait time ran out."""


def _process_is_alive(pid: int) -> bool:
    """True when a process with this id runs now."""
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    # Windows: OpenProcess with SYNCHRONIZE. A handle means the process lives.
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _age_seconds(path: Path) -> float | None:
    """The age of the file in seconds. `None` when the file is not there."""
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


def _take(path: Path, holder: str) -> bool:
    """Make the lock file. It returns False when the file is already there."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    body = json.dumps(
        {
            "pid": os.getpid(),
            "holder": holder,
            "since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
    return True


def _claim_stale(path: Path, logger, reason: str) -> bool:
    """Remove a stale lock file. It returns True when this process removed it.

    The rename is the handshake. A second waiter that renames the same file
    gets an error, so one waiter only removes the file and tries again.
    """
    private = path.with_name(f"{path.name}.stale-{os.getpid()}-{uuid4().hex}")
    try:
        os.rename(path, private)
    except OSError:
        return False  # Another waiter took the file first, or it is in use.
    logger.warning("%s The program removes it.", reason)
    try:
        os.unlink(private)
    except OSError as error:
        logger.warning("the stale lock file stays at %s: %s", private, error)
    return True


def _release(path: Path, logger) -> None:
    """Remove the lock file, but only when this process made it."""
    if _read(path).get("pid") != os.getpid():
        logger.warning("the lock file at %s is not from this process. It stays.", path)
        return
    try:
        path.unlink()
    except OSError as error:
        logger.warning("the lock file at %s stays: %s", path, error)


@contextmanager
def hold(holder: str, wait_seconds: int | None = None):
    """Hold the store lock for the length of the block.

    It raises `LockBusy` when the wait time runs out.
    """
    config.ensure_dirs()
    logger = log.get("atlas.lock")
    path = config.LOCK_PATH
    limit = config.LOCK_WAIT_SECONDS if wait_seconds is None else wait_seconds
    deadline = time.monotonic() + limit
    announced = False

    while True:
        if _take(path, holder):
            break

        other = _read(path)
        pid = int(other.get("pid", 0) or 0)
        age = _age_seconds(path)
        reason = None
        if pid and not _process_is_alive(pid):
            reason = f"stale lock from pid {pid}."
        elif not pid and age is not None and age > UNREADABLE_GRACE_SECONDS:
            reason = f"the lock file gives no process id, and it is {age:.0f} s old."
        if reason and _claim_stale(path, logger, reason):
            continue

        if time.monotonic() >= deadline:
            raise LockBusy(
                f"{other.get('holder', 'another process')} (pid {pid}) holds the "
                f"store lock. The wait of {limit} s ran out."
            )
        if not announced:
            logger.info(
                "%s (pid %s) holds the store lock. This process waits.",
                other.get("holder", "another process"),
                pid,
            )
            announced = True
        time.sleep(5)

    try:
        yield
    finally:
        _release(path, logger)
