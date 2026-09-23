"""Small dependency-free logger with secret redaction for report attachments."""
import logging
import re
from typing import Any

_REDACT_KEYS = re.compile(
    r'"(authorization|token|access_token|refresh_token|refreshtoken|password|otp|pin|hmac_secret|x-hmac-signature)"'
    r'\s*:\s*"([^"]*)"',
    re.IGNORECASE,
)


def redact(text: str) -> str:
    """Mask likely-sensitive values in a JSON-ish string before it's logged
    or attached to a report."""
    if not text:
        return text
    return _REDACT_KEYS.sub(lambda m: f'"{m.group(1)}":"***REDACTED***"', text)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def safe_repr(value: Any, limit: int = 2000) -> str:
    text = redact(str(value))
    return text if len(text) <= limit else text[:limit] + "...(truncated)"
