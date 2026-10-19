"""The log.

The program runs from the task scheduler with `pythonw.exe`, so there is no
console. Every line goes to `store/log/atlas-<yyyy-mm-dd>.log`. The same line
goes to the standard error when a console is present.
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from . import config

_READY = False


def setup(level: int = logging.INFO) -> logging.Logger:
    """Make the logger. It is safe to call this many times."""
    global _READY
    logger = logging.getLogger("atlas")
    if _READY:
        return logger

    config.ensure_dirs()
    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    path = config.LOG_DIR / f"atlas-{date.today().isoformat()}.log"
    to_file = logging.FileHandler(path, encoding="utf-8")
    to_file.setFormatter(fmt)
    logger.addHandler(to_file)

    if sys.stderr is not None:
        to_console = logging.StreamHandler(sys.stderr)
        to_console.setFormatter(fmt)
        logger.addHandler(to_console)

    _READY = True
    return logger


def get(name: str = "atlas") -> logging.Logger:
    setup()
    return logging.getLogger(name)
