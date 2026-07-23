import asyncio
from pathlib import Path

import pytest

from cleanroom.config.policies import load_policy
from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.models.finding import Category, Finding
from cleanroom.sanitizers.placeholder_parser import parse_placeholders
from cleanroom.services.verification_service import VerificationService

SANITIZED_REGRESSION = """Customer Record

[PERSON_1] lives at [ADDRESS_1].

His personal email is [EMAIL_1] and his phone number is
[PHONE_1].

Social Security number: [REDACTED_SSN]

Internal project name: [PROJECT_1]

The customer's account concerns a specialized heavy-haul operator located
next to the refinery in Texas City.

Support [REDACTED_PASSWORD]
API token: [REDACTED_API_KEY]
"""


class PlaceholderReportingProvider:
    async def detect(self, text, policy):
        return []

    async def verify(self, text, policy):
        values = [
            ("[PERSON_1]", Category.PERSON_NAME),
            ("[ADDRESS_1]", Category.ADDRESS),
            ("[EMAIL_1]", Category.EMAIL),
            ("[PHONE_1]", Category.PHONE),
            ("[REDACTED_SSN]", Category.SSN),
            ("[PROJECT_1]", Category.PROJECT_NAME),
            ("[REDACTED_PASSWORD]", Category.PASSWORD),
            ("[REDACTED_API_KEY]", Category.API_KEY),
        ]
        return [Finding(text=value, category=category, confidence=.99, source="ollama",
                        start=text.index(value), end=text.index(value) + len(value), reason="model")
                for value, category in values]


def test_live_placeholder_regression_passes() -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    result = asyncio.run(VerificationService(
        RegexDetector(), PlaceholderReportingProvider()).verify(
            SANITIZED_REGRESSION, [], policy, True))
    assert result.passed
    assert result.ignored_placeholder_findings >= 8
    assert result.remaining_findings_count == 0
    assert result.malformed_placeholders == 0


def test_parser_valid_adjacent_repeated_and_malformed() -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    parsed = parse_placeholders(
        "[PERSON_1][EMAIL_2] [PERSON_1] [REDACTED_SSN] [EMAIL_0] [BOGUS_1] [PHONE_",
        policy,
    )
    assert len(parsed.spans) == 4
    assert parsed.malformed_count == 3


@pytest.mark.parametrize("remaining", ["real@example.com", "password = hunter2"])
def test_real_sensitive_content_outside_placeholder_fails(remaining: str) -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    result = asyncio.run(VerificationService(RegexDetector()).verify(
        f"[EMAIL_1] {remaining}", [], policy, False))
    assert not result.passed
    assert result.deterministic_remaining_findings == 1


def test_original_value_and_normalized_ssn_remaining_fails() -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    original = Finding(text="123-45-6789", category=Category.SSN, confidence=1,
                       source="regex", start=0, end=11, reason="test")
    result = asyncio.run(VerificationService(RegexDetector()).verify(
        "SSN: 123 45 6789", [original], policy, False))
    assert not result.passed
    assert result.original_values_remaining == 1


def test_lowercase_field_label_is_not_treated_as_a_remaining_secret() -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    text = "Support password = [REDACTED_PASSWORD]"

    class FieldLabelProvider:
        async def detect(self, source, active_policy):
            return []

        async def verify(self, source, active_policy):
            start = source.index("password =")
            return [Finding(text="password =", category=Category.PASSWORD,
                confidence=.99, source="ollama", start=start, end=start + 10,
                reason="field label")]

    result = asyncio.run(VerificationService(RegexDetector(), FieldLabelProvider()).verify(
        text, [], policy, True))
    assert result.passed
    assert result.ignored_placeholder_findings >= 1


def test_category_field_label_with_colon_is_ignored() -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    text = "Phone: [PHONE_1]"

    class PhoneLabelProvider:
        async def detect(self, source, active_policy):
            return []

        async def verify(self, source, active_policy):
            return [Finding(text="Phone:", category=Category.PHONE, confidence=.99,
                source="ollama", start=0, end=6, reason="field label")]

    result = asyncio.run(VerificationService(RegexDetector(), PhoneLabelProvider()).verify(
        text, [], policy, True))
    assert result.passed


def test_placeholder_and_reordered_field_label_composite_is_ignored() -> None:
    policy = load_policy(Path("config/default-policy.yaml"))
    text = "[PHONE_1] Phone:"

    class CompositeProvider:
        async def detect(self, source, active_policy):
            return []

        async def verify(self, source, active_policy):
            return [Finding(text=source, category=Category.PHONE, confidence=.99,
                source="ollama", start=0, end=len(source), reason="generated composite")]

    result = asyncio.run(VerificationService(RegexDetector(), CompositeProvider()).verify(
        text, [], policy, True))
    assert result.passed
    assert result.ignored_placeholder_findings >= 1
