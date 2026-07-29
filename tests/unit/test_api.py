import json

from conftest import FakeProvider
from fastapi.testclient import TestClient

from cleanroom.api.app import create_app
from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
from cleanroom.models.job import JobCreate, JobStatus
from cleanroom.runtime import Runtime
from cleanroom.services.processing_service import ProcessingService
from cleanroom.services.scan_service import ScanService


def test_metadata_api_ready_config_policies_and_request_id(settings, policy) -> None:
    engine = create_db_engine(settings.database_url)
    initialize_database(engine)
    repository = JobRepository(session_factory(engine))
    provider = FakeProvider()
    processing = ProcessingService(settings, policy, repository, provider)
    runtime = Runtime(settings, repository, provider, processing,
                      ScanService(processing, settings.dirty_dir))
    client = TestClient(create_app(runtime))
    response = client.get("/jobs?limit=1&status=completed", headers={"X-Request-ID": "test-id"})
    assert response.status_code == 200 and response.headers["X-Request-ID"] == "test-id"
    assert client.get("/ready").json()["ready"] is True
    config = client.get("/config").json()
    assert "ollama_base_url" not in config and config["ollama_network"] == "tailscale"
    assert {item["name"] for item in client.get("/policies").json()} >= {"default", "strict", "ai-safe"}


def test_review_ui_is_loopback_only_escaped_and_privacy_safe(settings, policy) -> None:
    engine = create_db_engine(settings.database_url)
    initialize_database(engine)
    repository = JobRepository(session_factory(engine))
    provider = FakeProvider()
    processing = ProcessingService(settings, policy, repository, provider)
    runtime = Runtime(settings, repository, provider, processing,
                      ScanService(processing, settings.dirty_dir))
    report = settings.reports_dir / "review-report.json"
    report.write_text(json.dumps({
        "findings_by_category": {"EMAIL": 1},
        "quarantine_reason": "PDF_TEXT_VERIFICATION_FAILED",
        "private_value": "never-render-this@example.test",
    }))
    row = repository.create(JobCreate(source_filename="escaped-<script>.txt",
        source_path="processed/escaped.txt", source_hash="b" * 64, model="test",
        policy_name="default", policy_version=1))
    repository.update(row.id, JobStatus.QUARANTINED, report_path=str(report),
                      findings_count=1, verification_result=False)
    local = TestClient(create_app(runtime), base_url="http://127.0.0.1")
    dashboard = local.get("/review")
    assert dashboard.status_code == 200
    assert "escaped-&lt;script&gt;.txt" in dashboard.text and "<script>" not in dashboard.text
    assert dashboard.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in dashboard.headers["content-security-policy"]
    detail = local.get(f"/review/jobs/{row.id}")
    assert "PDF_TEXT_VERIFICATION_FAILED" in detail.text
    assert "never-render-this@example.test" not in detail.text
    remote = TestClient(create_app(runtime), base_url="http://192.0.2.10")
    assert remote.get("/review").status_code == 403
