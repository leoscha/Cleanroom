from conftest import FakeProvider
from fastapi.testclient import TestClient

from cleanroom.api.app import create_app
from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
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
