import asyncio
import json
from dataclasses import replace
from pathlib import Path

from conftest import FakeProvider

from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.providers.base import ProviderError
from cleanroom.services.chunking import ChunkedDetector
from cleanroom.services.evaluation_service import (
    EvaluationService,
    EvaluationThresholds,
    threshold_failures,
)


def test_evaluation_metrics_and_reports(tmp_path: Path, policy) -> None:
    cases, expected, output = tmp_path / "cases", tmp_path / "expected", tmp_path / "results"
    cases.mkdir()
    expected.mkdir()
    text = "Contact test@example.test."
    (cases / "email.txt").write_text(text)
    (expected / "email.json").write_text(json.dumps({"findings": [{
        "category": "EMAIL", "text": "test@example.test", "start": 8, "end": 25,
        "required": True}]}))
    service = EvaluationService(RegexDetector(), ChunkedDetector(FakeProvider(), 1000, 10, 10), policy)
    summary = asyncio.run(service.evaluate(cases, expected, output, "regex"))
    assert summary.precision == summary.recall == summary.f1 == 1
    assert summary.false_positives == summary.false_negatives == 0
    assert (output / "summary.json").exists()
    assert (output / "summary.md").exists()
    case_report = (output / "cases/email.json").read_text()
    assert "test@example.test" not in case_report


def test_evaluation_records_invalid_provider_output_without_plaintext(tmp_path: Path, policy) -> None:
    cases, expected, output = tmp_path / "cases", tmp_path / "expected", tmp_path / "results"
    cases.mkdir()
    expected.mkdir()
    (cases / "failure.txt").write_text("Synthetic private@example.test")
    (expected / "failure.json").write_text('{"findings":[]}')

    class InvalidProvider(FakeProvider):
        async def detect(self, text, active_policy):
            raise ProviderError("unterminated output containing private@example.test")

    service = EvaluationService(RegexDetector(), ChunkedDetector(
        InvalidProvider(), 1000, 10, 10), policy)
    summary = asyncio.run(service.evaluate(cases, expected, output, "ollama"))
    assert summary.invalid_model_findings == 1
    case_report = (output / "cases/failure.json").read_text()
    assert "ProviderError" in case_report
    assert "private@example.test" not in case_report


def test_quality_gate_reports_stable_failure_codes(tmp_path: Path, policy) -> None:
    cases, expected, output = tmp_path / "cases", tmp_path / "expected", tmp_path / "results"
    cases.mkdir()
    expected.mkdir()
    (cases / "clean.txt").write_text("Synthetic clean text.")
    (expected / "clean.json").write_text('{"findings":[]}')
    service = EvaluationService(RegexDetector(), ChunkedDetector(FakeProvider(), 1000, 10, 10), policy)
    summary = asyncio.run(service.evaluate(cases, expected, output, "regex"))
    assert threshold_failures(summary, EvaluationThresholds()) == ()
    degraded = replace(summary, precision=.1, required_finding_recall=.2,
        exact_span_accuracy=.3, verification_pass_rate=.4, invalid_model_findings=1)
    assert threshold_failures(degraded, EvaluationThresholds()) == (
        "PRECISION_BELOW_MINIMUM",
        "REQUIRED_RECALL_BELOW_MINIMUM",
        "EXACT_SPAN_ACCURACY_BELOW_MINIMUM",
        "VERIFICATION_PASS_RATE_BELOW_MINIMUM",
        "INVALID_FINDINGS_ABOVE_MAXIMUM",
    )
