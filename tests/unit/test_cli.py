from pathlib import Path

from conftest import FakeProvider
from typer.testing import CliRunner

from cleanroom.cli import commands
from cleanroom.database.repository import JobRepository
from cleanroom.database.session import create_db_engine, initialize_database, session_factory
from cleanroom.files.pdf_handler import create_synthetic_pdf
from cleanroom.runtime import Runtime
from cleanroom.services.processing_service import ProcessingService
from cleanroom.services.scan_service import ScanService

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(commands.app, ["version"])
    assert result.exit_code == 0, result.stdout
    assert result.stdout.strip() == "Cleanroom v0.4.0.dev0"


def _runtime(settings, policy, provider=None) -> Runtime:
    engine = create_db_engine(settings.database_url)
    initialize_database(engine)
    repository = JobRepository(session_factory(engine))
    active_provider = provider or FakeProvider()
    processing = ProcessingService(settings, policy, repository, active_provider)
    return Runtime(settings, repository, active_provider, processing,
                   ScanService(processing, settings.dirty_dir))


def test_init_is_non_destructive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    first = runner.invoke(commands.app, ["init"])
    assert first.exit_code == 0
    env = tmp_path / ".env"
    assert env.exists() and (tmp_path / "config/default-policy.yaml").exists()
    env.write_text("PRESERVE=true\n")
    second = runner.invoke(commands.app, ["init"])
    assert second.exit_code == 0 and env.read_text() == "PRESERVE=true\n"


def test_doctor_success_and_failed_ollama(settings, policy, monkeypatch) -> None:
    runtime = _runtime(settings, policy)
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    success = runner.invoke(commands.app, ["doctor"])
    assert success.exit_code == 0 and "Cleanroom is ready" in success.stdout

    class Unavailable(FakeProvider):
        async def health(self):
            return {"reachable": False, "model_installed": False}

    failed_runtime = _runtime(settings, policy, Unavailable())
    monkeypatch.setattr(commands, "_runtime", lambda: failed_runtime)
    failed = runner.invoke(commands.app, ["doctor"])
    assert failed.exit_code == 1 and "Ollama unreachable" in failed.stdout


def test_review_command_binds_to_configured_loopback(settings, policy, monkeypatch) -> None:
    runtime = _runtime(settings, policy)
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    called = {}

    def run(app, **options):
        called.update(options)

    monkeypatch.setattr(commands.uvicorn, "run", run)
    result = runner.invoke(commands.app, ["review", "--port", "8765"])
    assert result.exit_code == 0
    assert called["host"] == "127.0.0.1" and called["port"] == 8765
    assert "approval actions are not enabled" in result.stdout


def test_scan_status_show_config_and_demo(settings, policy, monkeypatch) -> None:
    runtime = _runtime(settings, policy)
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    source = settings.dirty_dir / "safe.txt"
    source.write_text("Entirely safe synthetic note.")
    scan = runner.invoke(commands.app, ["scan"])
    assert scan.exit_code == 0 and "Completed: 1" in scan.stdout
    job = runtime.repository.recent()[0]
    status = runner.invoke(commands.app, ["status", "--status", "completed", "--limit", "1"])
    assert status.exit_code == 0 and "safe.txt" in status.stdout
    shown = runner.invoke(commands.app, ["show", job.id[:8]])
    assert shown.exit_code == 0 and job.id in shown.stdout

    monkeypatch.setattr(commands, "Settings", lambda: settings)
    configured = runner.invoke(commands.app, ["config"])
    assert configured.exit_code == 0 and "Private Network" in configured.stdout
    assert "100.64.0.1" in configured.stdout

    demo = runner.invoke(commands.app, ["demo", "--run"])
    assert demo.exit_code == 0
    assert "All values are fake demonstration data." in " ".join(demo.stdout.split())
    assert list(settings.spotless_dir.glob("cleanroom-demo*-clean.txt"))


def test_policies_list_show_and_validate() -> None:
    listed = runner.invoke(commands.app, ["policies"])
    assert listed.exit_code == 0 and "ai-safe" in listed.stdout and "strict" in listed.stdout
    shown = runner.invoke(commands.app, ["policies", "show", "default"])
    assert shown.exit_code == 0 and '"name": "default"' in shown.stdout
    validated = runner.invoke(commands.app, ["policies", "validate", "config/default-policy.yaml"])
    assert validated.exit_code == 0 and "is valid" in validated.stdout


def test_evaluate_regex_command(settings, policy, monkeypatch) -> None:
    policy.placeholders["PERSON_NAME"] = "PERSON"
    runtime = _runtime(settings, policy)
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    result = runner.invoke(commands.app, ["evaluate", "--detector", "regex"])
    assert result.exit_code == 0, result.stdout
    assert "Evaluation thresholds passed" in result.stdout
    assert "PDF cases: 3" in result.stdout


def test_evaluate_provider_failure_is_safe_and_has_no_traceback(settings, policy,
                                                                monkeypatch) -> None:
    runtime = _runtime(settings, policy, FakeProvider(fail=True))
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    result = runner.invoke(commands.app, ["evaluate", "--detector", "combined"])
    assert result.exit_code == 1
    assert "Evaluation failed safely" in result.stdout
    assert "Traceback" not in result.stdout
    assert "do-not-store" not in result.stdout


def test_pdf_demo_inspect_process_status_and_show(settings, policy, monkeypatch) -> None:
    runtime = _runtime(settings, policy)
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    inspect_source = settings.dirty_dir / "inspect-only.pdf"
    create_synthetic_pdf(inspect_source)
    inspected = runner.invoke(commands.app, ["inspect", str(inspect_source)])
    assert inspected.exit_code == 0
    assert '"page_count": 1' in inspected.stdout
    assert '"supported": true' in inspected.stdout
    assert "jane@example.test" not in inspected.stdout

    demo = runner.invoke(commands.app, ["demo", "--type", "pdf", "--run"])
    assert demo.exit_code == 0 and "Demo result: completed" in demo.stdout
    job = runtime.repository.recent()[0]
    shown = runner.invoke(commands.app, ["show", job.id[:8]])
    assert shown.exit_code == 0
    assert '"document_type": "pdf"' in shown.stdout
    assert '"redaction_rectangle_count": 3' in shown.stdout
    status = runner.invoke(commands.app, ["status", "--status", "completed"])
    assert status.exit_code == 0 and "pdf" in status.stdout


def test_inspect_rejects_likely_scanned_pdf(settings, policy, monkeypatch) -> None:
    import pymupdf as fitz

    runtime = _runtime(settings, policy)
    monkeypatch.setattr(commands, "_runtime", lambda: runtime)
    source = settings.dirty_dir / "scan.pdf"
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        page = document.new_page()
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pixmap.clear_with(255)
        page.insert_image(fitz.Rect(72, 72, 200, 200), pixmap=pixmap)  # type: ignore[no-untyped-call]
        document.save(source)  # type: ignore[no-untyped-call]
    finally:
        document.close()  # type: ignore[no-untyped-call]
    result = runner.invoke(commands.app, ["inspect", str(source)])
    assert result.exit_code == 1
    assert "LIKELY_SCANNED_PDF" in result.stdout
    assert "appears_scanned" in result.stdout
