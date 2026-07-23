import asyncio
from pathlib import Path

import pytest

from cleanroom.config.policies import PolicyError, load_policy
from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.models.finding import Category
from cleanroom.models.policy import Action


@pytest.mark.parametrize("name", ["default-policy.yaml", "strict-policy.yaml", "ai-safe-policy.yaml"])
def test_bundled_policies_are_valid(name: str) -> None:
    policy = load_policy(Path("config") / name)
    assert policy.schema_version == 1
    assert set(policy.actions) == set(Category)


def test_policy_category_threshold_and_review() -> None:
    policy = load_policy(Path("config/ai-safe-policy.yaml"))
    assert policy.threshold_for(Category.API_KEY) == .5
    assert policy.actions[Category.INDIRECT_IDENTIFIER] == Action.REVIEW
    assert policy.review_behavior.quarantine


def test_policy_schema_and_action_rejection(tmp_path: Path) -> None:
    for body in (
        "schema_version: 99\nname: bad\nversion: 1\nminimum_confidence: .7\nactions: {}",
        "name: bad\nversion: 1\nminimum_confidence: .7\nactions: {EMAIL: destroy}",
        "name: bad\nversion: 1\nminimum_confidence: .7\nactions: {UNKNOWN: replace}",
    ):
        path = tmp_path / "bad.yaml"
        path.write_text(body)
        with pytest.raises(PolicyError):
            load_policy(path)


@pytest.mark.parametrize("source,value,category", [
    ("password = value!", "value!", Category.PASSWORD),
    ("password: 'quoted value!'", "quoted value!", Category.PASSWORD),
    ('api_key="abc-123!"', "abc-123!", Category.API_KEY),
    ("token: value.with.punctuation!", "value.with.punctuation!", Category.API_KEY),
    ("password:\nnext-line", "next-line", Category.PASSWORD),
])
def test_assignment_detectors_preserve_labels(policy, source: str, value: str,
                                               category: Category) -> None:
    findings = asyncio.run(RegexDetector().detect(source, policy))
    finding = next(item for item in findings if item.category == category)
    assert finding.text == value
    assert source[finding.start:finding.end] == value


def test_multiple_assignments_one_line(policy) -> None:
    text = "password=one; api_key=two"
    findings = asyncio.run(RegexDetector().detect(text, policy))
    assert {(item.category, item.text) for item in findings} >= {
        (Category.PASSWORD, "one"), (Category.API_KEY, "two")}
