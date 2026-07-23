import asyncio
import json
from pathlib import Path

import pymupdf as fitz
from conftest import FakeProvider

from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
from cleanroom.files.pdf_handler import create_synthetic_pdf
from cleanroom.models.finding import Category, Finding
from cleanroom.services.processing_service import ProcessingService


def repository(url: str) -> JobRepository:
    engine = create_db_engine(url)
    initialize_database(engine)
    return JobRepository(session_factory(engine))


def test_complete_synthetic_pdf_vertical_slice(settings, policy) -> None:
    source = settings.dirty_dir / "customer.pdf"
    create_synthetic_pdf(source)
    original = source.read_bytes()
    job = asyncio.run(ProcessingService(
        settings, policy, repository(settings.database_url), FakeProvider()
    ).process(source, check_stability=False))
    assert job.status == "completed"
    output = Path(job.output_path)
    assert output.parent == settings.spotless_dir
    with fitz.open(output) as document:  # type: ignore[no-untyped-call]
        extracted = "".join(
            document[index].get_text("text")  # type: ignore[no-untyped-call]
            for index in range(document.page_count)
        )
        assert document.metadata.get("title", "") == ""
    for value in ("jane@example.test", "312-555-0199", "TestingOnly123!"):
        assert value not in extracted
    processed = Path(job.source_path)
    assert processed.parent == settings.processed_dir
    assert processed.read_bytes() == original
    report_text = Path(job.report_path).read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["document_type"] == "pdf"
    assert report["page_count"] == 1
    assert report["mapped_findings_count"] == 3
    assert report["structural_verification"]["passed"] is True
    assert report["verification"]["passed"] is True
    assert report["pdf_security"]["metadata_removed"] is True
    assert all(value not in report_text for value in (
        "jane@example.test", "312-555-0199", "TestingOnly123!"
    ))
    database = Path(settings.database_url.removeprefix("sqlite:///")).read_bytes()
    assert b"jane@example.test" not in database


def test_pdf_ollama_placeholder_finding_is_ignored(settings, policy) -> None:
    class PlaceholderReportingProvider(FakeProvider):
        async def verify(self, text, active_policy):
            placeholder = "[EMAIL_1]"
            start = text.index(placeholder)
            return [Finding(text=placeholder, category=Category.EMAIL, confidence=1,
                source="ollama", start=start, end=start + len(placeholder),
                reason="synthetic model mistake")]

    settings.ollama_verify = True
    source = settings.dirty_dir / "placeholder.pdf"
    create_synthetic_pdf(source)
    job = asyncio.run(ProcessingService(settings, policy, repository(settings.database_url),
        PlaceholderReportingProvider()).process(source, check_stability=False))
    assert job.status == "completed"
    report = json.loads(Path(job.report_path).read_text(encoding="utf-8"))
    assert report["verification"]["ignored_placeholder_findings"] == 1
    assert report["verification"]["ollama_remaining_findings"] == 0
