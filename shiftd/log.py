"""Logging setup. stderr always, file when configured.

Format is line oriented and greppable:

    2026-09-15T22:10:03Z INFO  engine  event=reconcile.apply blocklist=social via=cli

Fields come from the `event()` helper so a log line can be split on spaces and
parsed without a regex per call site.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Any, Optional

LOGGER_NAME = "shiftd"

_MAX_BYTES = 2 * 1024 * 1024
_BACKUPS = 3


class _UTCFormatter(logging.Formatter):
    converter = time.gmtime

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", self.converter(record.created))


def setup(log_file: Optional[Path] = None, verbose: bool = False) -> logging.Logger:
    """Configure the shiftd logger. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    fmt = _UTCFormatter("%(asctime)s %(levelname)-5s %(name)s %(message)s")

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            rotating = logging.handlers.RotatingFileHandler(
                str(log_file), maxBytes=_MAX_BYTES, backupCount=_BACKUPS
            )
            rotating.setFormatter(fmt)
            logger.addHandler(rotating)
        except OSError as exc:
            # A missing log file must never stop enforcement.
            logger.warning("event=log.file_unavailable path=%s error=%s", log_file, exc)
    return logger


def get(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def _fmt_value(value: Any) -> str:
    text = "null" if value is None else str(value)
    if text == "":
        return '""'
    return text.replace(" ", "_").replace("\n", "\\n")


def kv(event: str, **fields: Any) -> str:
    """Render a structured message: event=name key=value ..."""
    parts = [f"event={event}"]
    for key, value in fields.items():
        parts.append(f"{key}={_fmt_value(value)}")
    return " ".join(parts)
