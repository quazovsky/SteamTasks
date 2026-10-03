"""Structured logging: JSON lines to a file, readable lines to the console."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Attributes present on every ``LogRecord``. The stdlib raises ``KeyError`` when
#: ``extra=`` tries to overwrite one of these, so :class:`SafeLogger` renames
#: collisions instead of letting a call site blow up at runtime.
RESERVED_KEYS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
    }
)


class SafeLogger(logging.Logger):
    """A ``Logger`` that tolerates reserved names in ``extra=``.

    ``log.info("x", extra={"name": ...})`` raises ``KeyError`` in the stdlib. Here
    the colliding key is prefixed with ``ctx_`` so the value is still emitted.
    """

    def makeRecord(  # noqa: PLR0913 - signature fixed by the stdlib
        self,
        name,
        level,
        fn,
        lno,
        msg,
        args,
        exc_info,
        func=None,
        extra=None,
        sinfo=None,
    ):
        if extra:
            extra = {
                (f"ctx_{key}" if key in RESERVED_KEYS else key): value
                for key, value in extra.items()
            }
        return super().makeRecord(name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Greppable and machine-readable."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "process_id": record.process,
        }
        for key, value in record.__dict__.items():
            if key in RESERVED_KEYS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Compact human output: ``HH:MM:SS LEVEL event key=value ...``"""

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        extras = " ".join(
            f"{key}={value}"
            for key, value in record.__dict__.items()
            if key not in RESERVED_KEYS and not key.startswith("_")
        )
        line = f"{stamp} {record.levelname:<7} {record.getMessage()}"
        if extras:
            line = f"{line}  {extras}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def get_logger(name: str = "worthlesstask") -> SafeLogger:
    """Return the package logger, upgrading it to :class:`SafeLogger` if needed."""
    logger = logging.getLogger(name)
    if not isinstance(logger, SafeLogger):
        logger = SafeLogger(name)
        logging.Logger.manager.loggerDict[name] = logger
    if not logger.handlers:
        # Without a handler the stdlib falls back to lastResort and prints
        # warnings to stderr, which is noise for a library surface.
        logger.addHandler(logging.NullHandler())
    return logger


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    console: bool = True,
    logger_name: str = "worthlesstask",
) -> SafeLogger:
    """Configure and return the package logger.

    Idempotent: repeated calls reset handlers instead of stacking them.
    """
    logger = get_logger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    numeric = getattr(logging, str(level).upper(), logging.INFO)

    if console and sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(numeric)
        stream.setFormatter(ConsoleFormatter())
        logger.addHandler(stream)

    if log_file and str(log_file) != "-":
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    return logger
