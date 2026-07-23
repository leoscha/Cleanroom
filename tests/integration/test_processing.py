import asyncio
import json
import logging
from pathlib import Path

import pytest
from conftest import FakeProvider

from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
from cleanroom.logging import RedactionFilter
from cleanroom.models.finding import Category, Finding
from cleanroom.models.job import JobStatus
from cleanroom.models.policy import Action
from cleanroom.services.processing_service import DuplicateFileError, ProcessingService


def repository(url: str) -> JobRepository:
    engine = create_db_engine(url)
    initialize_database(engine)
    return JobRepository(session_factory(engine))


def test_complete_vertical_slice(settings, policy) -> None:
    source = settings.dirty_dir / "customer.txt"
    original = "John Smith emailed john@example.com. John Smith called 312-555-0199.\n"
    source.write_text(original)
    findings = [
        Finding(text="John Smith", category=Category.PERSON_NAME, confidence=.98,
                source="ollama", start=0, end=10, reason="private name"),
        Finding(text="John Smith", category=Category.PERSON_NAME, confidence=.98,
        source="ollama", start=37, end=47, reason="private name"),
    ]
    repo = repository(settings.database_url)
    service = ProcessingService(settings, policy, repo, FakeProvider(findings))
    job = asyncio.run(service.process(source))
    assert job.status == JobStatus.COMPLETED.value
    output = Path(job.output_path)
    assert output.exists()
    cleaned = output.read_text()
    assert cleaned.count("[PERSON_NAME_1]") == 2
    assert "[EMAIL_1]" in cleaned and "[PHONE_1]" in cleaned
    processed = Path(job.source_path)
    assert processed.read_text() == original and not source.exists()
    report_text = Path(job.report_path).read_text()
    assert "John Smith" not in report_text and "john@example.com" not in report_text
    report = json.loads(report_text)
    assert report["verification"]["passed"] is True
    markdown = Path(report["markdown_report_path"])
    assert markdown.exists() and "# Cleanroom Report" in markdown.read_text()
    assert "John Smith" not in markdown.read_text()
    stored = repo.get(job.id)
    assert stored is not None and stored.status == "completed"
    database_bytes = Path(settings.database_url.removeprefix("sqlite:///")).read_bytes()
    assert b"John Smith" not in database_bytes and b"john@example.com" not in database_bytes
    assert not (settings.reports_dir / "private-review").exists()


def test_duplicate_hash_rejected(settings, policy) -> None:
    repo = repository(settings.database_url)
    service = ProcessingService(settings, policy, repo, FakeProvider())
    first = settings.dirty_dir / "one.txt"
    first.write_text("safe")
    assert asyncio.run(service.process(first)).status == "completed"
    second = settings.dirty_dir / "two.txt"
    second.write_text("safe")
    with pytest.raises(DuplicateFileError):
        asyncio.run(service.process(second))


def test_failed_lifecycle_retry_and_secret_sanitization(settings, policy, caplog) -> None:
    source = settings.dirty_dir / "bad.txt"
    source.write_text("secret=value")
    repo = repository(settings.database_url)
    caplog.set_level(logging.ERROR)
    caplog.handler.addFilter(RedactionFilter())
    failed = asyncio.run(ProcessingService(settings, policy, repo, FakeProvider(fail=True)).process(source))
    assert failed.status == "failed" and Path(failed.source_path).parent == settings.failed_dir
    report = Path(failed.report_path).read_text()
    assert "do-not-store" not in report and "do-not-store" not in caplog.text
    assert repo.eligible_retries()[0].id == failed.id


def test_quarantine_on_verification_failure(settings, policy) -> None:
    source = settings.dirty_dir / "remain.txt"
    source.write_text("hello")
    residual = Finding(text="hello", category=Category.PERSON_NAME, confidence=.9,
                       source="ollama", start=0, end=5, reason="identifier")

    class VerificationOnly(FakeProvider):
        calls = 0
        async def detect(self, text, active_policy):
            self.calls += 1
            return [] if self.calls == 1 else [residual]

    settings.ollama_verify = True
    job = asyncio.run(ProcessingService(settings, policy, repository(settings.database_url),
                                        VerificationOnly()).process(source))
    assert job.status == "quarantined"
    assert Path(job.output_path).parent == settings.quarantine_dir
    assert Path(job.source_path).parent == settings.processed_dir


def test_private_review_diff_requires_explicit_opt_in(settings, policy) -> None:
    settings.write_review_diff = True
    source = settings.dirty_dir / "review.txt"
    source.write_text("Email private@example.test")
    job = asyncio.run(ProcessingService(settings, policy, repository(settings.database_url),
                                        FakeProvider()).process(source))
    assert job.status == "completed"
    diffs = list((settings.reports_dir / "private-review").glob("*.diff"))
    assert len(diffs) == 1 and "private@example.test" in diffs[0].read_text()


def test_review_finding_quarantines_without_revealing_text(settings, policy) -> None:
    sensitive = "the only operator beside the refinery"
    source = settings.dirty_dir / "indirect.txt"
    source.write_text(sensitive)
    policy.actions[Category.INDIRECT_IDENTIFIER] = Action.REVIEW
    finding = Finding(text=sensitive, category=Category.INDIRECT_IDENTIFIER, confidence=.9,
                      source="ollama", start=0, end=len(sensitive), reason="indirect identifier")

    class ReviewProvider(FakeProvider):
        async def verify(self, text, active_policy):
            return []

    job = asyncio.run(ProcessingService(settings, policy, repository(settings.database_url),
                                        ReviewProvider([finding])).process(source))
    assert job.status == "quarantined"
    report = Path(job.report_path).read_text()
    assert sensitive not in report and "INDIRECT_IDENTIFIER" in report
