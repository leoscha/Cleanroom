import hashlib
from dataclasses import dataclass

from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.models.report import ReplacementReport
from cleanroom.sanitizers.placeholders import PlaceholderFactory


@dataclass
class SanitizationResult:
    text: str
    replacements: list[ReplacementReport]
    replaced_values: set[str]


def sanitize_text(text: str, findings: list[Finding], policy: SanitizationPolicy) -> SanitizationResult:
    output = text
    factory = PlaceholderFactory(policy)
    replacements: list[ReplacementReport] = []
    values: set[str] = set()
    planned: list[tuple[Finding, str]] = []
    for finding in sorted(findings, key=lambda item: item.start):
        placeholder = factory.for_finding(finding)
        if placeholder is None or finding.confidence < policy.threshold_for(finding.category):
            continue
        planned.append((finding, placeholder))
        values.add(finding.text)
        replacements.append(ReplacementReport(category=finding.category,
            original_hash=hashlib.sha256(finding.text.encode()).hexdigest(), placeholder=placeholder,
            sources=sorted(finding.sources), confidence=finding.confidence))
    for finding, placeholder in reversed(planned):
        output = output[: finding.start] + placeholder + output[finding.end :]
    return SanitizationResult(output, replacements, values)
