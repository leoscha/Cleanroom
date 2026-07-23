import re

from cleanroom.models.finding import Finding
from cleanroom.models.policy import Action, SanitizationPolicy


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


class PlaceholderFactory:
    def __init__(self, policy: SanitizationPolicy) -> None:
        self.policy = policy
        self.mapping: dict[tuple[str, str], str] = {}
        self.counts: dict[str, int] = {}

    def for_finding(self, finding: Finding) -> str | None:
        action = self.policy.actions[finding.category]
        if action == Action.IGNORE or (
            action == Action.REVIEW and not self.policy.review_behavior.auto_replace
        ):
            return None
        label = self.policy.placeholders[finding.category]
        if action == Action.REDACT:
            return f"[REDACTED_{label}]"
        key = (finding.category.value, normalized(finding.text))
        if key not in self.mapping:
            self.counts[label] = self.counts.get(label, 0) + 1
            self.mapping[key] = f"[{label}_{self.counts[label]}]"
        return self.mapping[key]
