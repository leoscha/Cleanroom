import re
from dataclasses import dataclass

from cleanroom.models.policy import Action, SanitizationPolicy

BRACKETED_TOKEN = re.compile(r"\[[^\]\r\n]*\]")


@dataclass(frozen=True)
class PlaceholderSpan:
    start: int
    end: int
    text: str
    label: str
    redacted: bool


@dataclass(frozen=True)
class PlaceholderParseResult:
    spans: tuple[PlaceholderSpan, ...]
    malformed_count: int


def parse_placeholders(text: str, policy: SanitizationPolicy) -> PlaceholderParseResult:
    replace_labels = {policy.placeholders[category] for category, action in policy.actions.items()
                      if action == Action.REPLACE or (
                          action == Action.REVIEW and policy.review_behavior.auto_replace)}
    redact_labels = {policy.placeholders[category] for category, action in policy.actions.items()
                     if action == Action.REDACT}
    spans: list[PlaceholderSpan] = []
    malformed = 0
    for match in BRACKETED_TOKEN.finditer(text):
        token = match.group()
        numbered = re.fullmatch(r"\[([A-Z][A-Z0-9_]*)_([1-9]\d*)\]", token)
        redacted = re.fullmatch(r"\[REDACTED_([A-Z][A-Z0-9_]*)\]", token)
        if numbered and numbered.group(1) in replace_labels:
            spans.append(PlaceholderSpan(match.start(), match.end(), token, numbered.group(1), False))
        elif redacted and redacted.group(1) in redact_labels:
            spans.append(PlaceholderSpan(match.start(), match.end(), token, redacted.group(1), True))
        elif re.fullmatch(r"\[(?:REDACTED_[A-Z][A-Z0-9_]*|[A-Z][A-Z0-9_]*_\d+)\]", token):
            malformed += 1
    # Unclosed placeholder-looking brackets fail closed.
    stripped = BRACKETED_TOKEN.sub("", text)
    malformed += len(re.findall(r"\[(?:REDACTED_)?[A-Z][A-Z0-9_]*", stripped))
    return PlaceholderParseResult(tuple(spans), malformed)


def inside_placeholder(start: int, end: int, spans: tuple[PlaceholderSpan, ...]) -> bool:
    return any(start >= span.start and end <= span.end for span in spans)


def without_placeholders(text: str, spans: tuple[PlaceholderSpan, ...]) -> str:
    chars = list(text)
    for span in spans:
        chars[span.start:span.end] = " " * (span.end - span.start)
    return "".join(chars)
