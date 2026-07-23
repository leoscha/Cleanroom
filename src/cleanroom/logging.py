import logging
import re

SECRET = re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+|Bearer\s+\S+")


def safe_message(value: object) -> str:
    return SECRET.sub(lambda m: m.group(0).split(":", 1)[0].split("=", 1)[0] + "=[REDACTED]",
                      str(value))[:500]


def safe_diagnostic(error: BaseException) -> str:
    """Return an allowlisted diagnostic that cannot contain exception payload data."""
    return f"Processing failed safely ({type(error).__name__})"


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = safe_message(record.getMessage())
        record.args = ()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactionFilter())
    handler.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'))
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
