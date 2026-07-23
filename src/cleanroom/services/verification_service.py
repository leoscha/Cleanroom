import re
from collections import Counter

from cleanroom.detectors.merge import merge_findings
from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.models.finding import Category, Finding
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.models.report import VerificationReport
from cleanroom.providers.base import DetectionProvider
from cleanroom.sanitizers.placeholder_parser import (
    PlaceholderSpan,
    inside_placeholder,
    parse_placeholders,
    without_placeholders,
)
from cleanroom.services.chunking import ChunkedDetector

STRUCTURED_DIGITS = {Category.PHONE, Category.SSN, Category.CREDIT_CARD, Category.BANK_ACCOUNT}


class VerificationService:
    def __init__(self, regex: RegexDetector, provider: DetectionProvider | None = None,
                 chunker: ChunkedDetector | None = None) -> None:
        self.regex, self.provider, self.chunker = regex, provider, chunker

    async def verify(
        self,
        output: str,
        originals: set[str] | list[Finding],
        policy: SanitizationPolicy,
        use_ollama: bool = True,
        allowed_review_values: set[str] | None = None,
    ) -> VerificationReport:
        parsed = parse_placeholders(output, policy)
        visible = without_placeholders(output, parsed.spans)
        original_count = self._remaining_originals(visible, originals)

        deterministic = await self.regex.detect(output, policy)
        deterministic, ignored_deterministic = self._filter_generated(
            deterministic, parsed.spans, policy
        )
        ignored_review = 0
        if allowed_review_values:
            kept = [item for item in deterministic if item.text not in allowed_review_values]
            ignored_review += len(deterministic) - len(kept)
            deterministic = kept

        contextual: list[Finding] = []
        ignored_contextual = 0
        error_code: str | None = None
        if use_ollama and self.provider is not None:
            try:
                if self.chunker is not None:
                    contextual = (await self.chunker.detect(
                        output, policy, verification=True)).findings
                else:
                    verifier = getattr(self.provider, "verify", self.provider.detect)
                    contextual = await verifier(output, policy)
                contextual, ignored_contextual = self._filter_generated(
                    contextual, parsed.spans, policy
                )
                if allowed_review_values:
                    kept = [item for item in contextual if item.text not in allowed_review_values]
                    ignored_review += len(contextual) - len(kept)
                    contextual = kept
            except Exception as exc:
                error_code = type(exc).__name__

        deterministic = self._accepted(output, deterministic, policy)
        contextual = self._accepted(output, contextual, policy)
        all_remaining = merge_findings(output, deterministic + contextual).findings
        counts = Counter(item.category for item in all_remaining)
        total = original_count + len(all_remaining) + parsed.malformed_count
        passed = total == 0 and error_code is None
        return VerificationReport(
            passed=passed,
            original_values_remaining=original_count,
            deterministic_remaining_findings=len(deterministic),
            ollama_remaining_findings=len(contextual),
            ignored_placeholder_findings=ignored_deterministic + ignored_contextual,
            ignored_policy_review_findings=ignored_review,
            malformed_placeholders=parsed.malformed_count,
            remaining_findings_count=total,
            error_code=error_code,
            categories=dict(counts),
        )

    @staticmethod
    def _remaining_originals(visible: str, originals: set[str] | list[Finding]) -> int:
        if isinstance(originals, set):
            return sum(value in visible for value in originals)
        remaining = 0
        for finding in originals:
            if finding.text in visible:
                remaining += 1
                continue
            if finding.category in STRUCTURED_DIGITS:
                digits = re.sub(r"\D", "", finding.text)
                visible_digits = re.sub(r"\D", "", visible)
                if len(digits) >= 7 and digits in visible_digits:
                    remaining += 1
        return remaining

    @staticmethod
    def _filter_generated(
        findings: list[Finding],
        spans: tuple[PlaceholderSpan, ...],
        policy: SanitizationPolicy,
    ) -> tuple[list[Finding], int]:
        labels = {category.value for category in Category}
        labels.update(policy.placeholders.values())
        tokens = {span.text for span in spans}
        retained: list[Finding] = []
        ignored = 0
        for finding in findings:
            normalized_label = (
                finding.text.strip("[] \t\r\n:=").upper().replace(" ", "_")
            )
            if (
                finding.text in tokens
                or normalized_label in labels
                or VerificationService._is_assignment_label(finding.text)
                or VerificationService._is_generated_composite(
                    finding.text, tokens, labels
                )
                or inside_placeholder(finding.start, finding.end, spans)
            ):
                ignored += 1
            else:
                retained.append(finding)
        return retained, ignored

    @staticmethod
    def _is_assignment_label(value: str) -> bool:
        return bool(re.fullmatch(
            r"(?i)\s*(?:password|passwd|pwd|api[ _-]?(?:key|token)|token|secret)\s*[:=]\s*",
            value,
        ))

    @staticmethod
    def _is_generated_composite(value: str, tokens: set[str], labels: set[str]) -> bool:
        residual = value
        removed = False
        for token in tokens:
            if token in residual:
                residual = residual.replace(token, " ")
                removed = True
        if not removed:
            return False
        normalized = residual.strip("[] \t\r\n:=").upper().replace(" ", "_")
        return not normalized or normalized in labels or VerificationService._is_assignment_label(
            residual
        )

    @staticmethod
    def _accepted(
        output: str, findings: list[Finding], policy: SanitizationPolicy
    ) -> list[Finding]:
        return [
            item
            for item in merge_findings(output, findings).findings
            if item.matches(output) and item.confidence >= policy.threshold_for(item.category)
        ]
