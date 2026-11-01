from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_RESERVED_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id = request_id_ctx.get()
        suffix = f" request_id={request_id}" if request_id else ""
        base = (
            f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} "
            f"{record.levelname:<8} {record.name}: {record.getMessage()}{suffix}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else HumanFormatter())
    root.addHandler(handler)
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "botocore", "boto3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
