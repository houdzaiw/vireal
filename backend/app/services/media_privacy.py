"""Keep bearer media grants out of access logs and error/tracing telemetry."""

import logging
import re
from typing import Any

TOKEN = re.compile(
    r"""(^|[?&])(?:t|%74)(?:o|%6f)(?:k|%6b)(?:e|%65)(?:n|%6e)=[^&\s"']*""",
    re.IGNORECASE,
)


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return TOKEN.sub(lambda m: m.group(1) + "token=[REDACTED]", value)
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() == "token" else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, tuple):
        return tuple(scrub(v) for v in value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class MediaTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.msg)
        record.args = scrub(record.args)
        return True


def scrub_event(event: dict, _hint: dict) -> dict:
    return scrub(event)


def install_log_filters() -> None:
    for name in ("uvicorn.access", "httpx"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, MediaTokenFilter) for f in logger.filters):
            logger.addFilter(MediaTokenFilter())
