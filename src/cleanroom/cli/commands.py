import asyncio
import json
import os
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from cleanroom import __version__
from cleanroom.config.ollama_endpoint import (
    ConnectionMode,
    EndpointValidationError,
    format_safe_endpoint,
    validate_ollama_endpoint,
)
from cleanroom.config.policies import PolicyError, load_policy
from cleanroom.config.settings import Settings
from cleanroom.database.models import JobRecord
from cleanroom.database.session import create_db_engine, initialize_database
from cleanroom.files.discovery import discover_files
from cleanroom.files.lifecycle import collision_safe, move_original
from cleanroom.files.pdf_handler import PdfDocumentHandler, PdfError, create_synthetic_pdf
from cleanroom.files.text_handler import validate_input
from cleanroom.models.job import JobStatus
from cleanroom.runtime import Runtime, build_runtime
from cleanroom.services.evaluation_service import (
    EvaluationService,
    EvaluationThresholds,
    bundled_evaluation_paths,
    threshold_failures,
)
from cleanroom.services.verification_service import VerificationService
from cleanroom.watchers.folder_watcher import watch_folder

console = Console()
app = typer.Typer(no_args_is_help=True, help="Local-first AI Privacy Gateway")
policies_app = typer.Typer(invoke_without_command=True, help="List and validate policies")
configure_app = typer.Typer(help="Guided configuration")
app.add_typer(policies_app, name="policies")
app.add_typer(configure_app, name="configure")


def _runtime() -> Runtime:
    try:
        return build_runtime()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/] {_safe_configuration_error(exc)}")
        raise typer.Exit(2) from exc


@app.command()
def version() -> None:
    """Print the installed Cleanroom version."""
    console.print(f"Cleanroom v{__version__}")


@app.command()
def init() -> None:
    """Initialize a Cleanroom workspace without overwriting configuration."""
    settings = Settings(_env_file=None)
    created: list[Path] = []
    for directory in (*settings.required_dirs, settings.temp_dir):
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(directory)
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text(files("cleanroom.resources").joinpath("env.example").read_text())
        created.append(env_path)
    settings.policy_path.parent.mkdir(parents=True, exist_ok=True)
    if not settings.policy_path.exists():
        settings.policy_path.write_text(
            files("cleanroom.resources").joinpath("default-policy.yaml").read_text())
        created.append(settings.policy_path)
    engine = create_db_engine(settings.database_url)
    initialize_database(engine)
    console.print("[bold green]Cleanroom workspace initialized.[/]")
    console.print(f"Created {len(created)} item(s). Existing configuration was preserved.")
    console.print("\nCleanroom is configured to use a local Ollama instance.\n")
    console.print("Endpoint:\nhttp://127.0.0.1:11434\n")
    console.print("Next steps:\n\n1. Start Ollama\n2. Install your preferred model\n3. Run:\n")
    console.print("[bold]cleanroom doctor[/]\n")
    console.print("Remote Ollama servers can be configured later with "
                  "[bold]cleanroom configure ollama[/].")


@app.command()
def doctor() -> None:
    """Validate storage, policy, database, private Ollama, and structured output."""
    console.print("[bold]Cleanroom Doctor[/]\n")
    runtime = _runtime()
    failures: list[str] = []

    def check(ok: bool, success: str, failure: str) -> None:
        console.print(f"[green]✓[/] {success}" if ok else f"[red]✗[/] {failure}")
        if not ok:
            failures.append(failure)

    check(True, "Configuration loaded", "Configuration failed; edit .env")
    for directory in runtime.settings.required_dirs:
        check(directory.is_dir() and os.access(directory, os.W_OK),
              f"{directory} directory writable",
              f"{directory} is missing or not writable; run cleanroom init")
    try:
        load_policy(runtime.settings.policy_path)
        check(True, "Policy valid", "")
    except PolicyError:
        check(False, "", f"Policy invalid; edit {runtime.settings.policy_path}")
    try:
        with create_db_engine(runtime.settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        check(True, "SQLite available", "")
    except Exception:
        check(False, "", "SQLite unavailable; check CLEANROOM_DATABASE_URL")
    endpoint = runtime.settings.validated_ollama_endpoint
    console.print("\n[bold]Ollama[/]\n")
    check(True, f"Connection mode: {endpoint.mode.display_name}", "")
    check(True, f"Endpoint: {endpoint.safe_url}", "")
    check(True, f"Endpoint classification: {endpoint.kind.display_name}", "")
    if endpoint.mode is not ConnectionMode.LOCAL:
        check(True, "Host validated", "")
    health, structured_error = asyncio.run(_doctor_ollama(runtime))
    check(bool(health.get("reachable")), "Ollama reachable",
          "Ollama unreachable; check OLLAMA_BASE_URL, Tailscale, and Windows Firewall")
    installed = bool(health.get("model_installed"))
    check(installed, f"Model installed: {runtime.settings.ollama_model}",
          f"Model missing; run: ollama pull {runtime.settings.ollama_model}")
    if installed:
        if structured_error is None:
            check(True, "Structured output supported", "")
        else:
            check(False, "", "Structured output failed; verify model capability and Ollama logs")
    if failures:
        console.print(f"\n[red]Cleanroom is not ready ({len(failures)} failed check(s)).[/]")
        raise typer.Exit(1)
    console.print("\n[bold green]Cleanroom is ready.[/]")


@app.command()
def scan() -> None:
    """Process all supported files in dirty and print a safe summary."""
    runtime = _runtime()
    console.print(f"[bold]Scanning {runtime.settings.dirty_dir}/[/]\n")
    result = asyncio.run(runtime.scanning.scan())
    console.print(f"{result.discovered} supported files found")
    console.print(f"{result.duplicates_skipped} duplicate skipped")
    console.print(f"{len(result.jobs)} files processed\n")
    for job in result.jobs:
        marker = "✓" if job.status == "completed" else "!"
        console.print(f"{marker} {job.source_filename:<28} {job.status:<14} {job.findings_count} findings")
    counts = {status: sum(job.status == status for job in result.jobs)
              for status in ("completed", "quarantined", "failed")}
    console.print("\n[bold]Summary[/]")
    for status, count in counts.items():
        console.print(f"{status.title()}: {count}")
    console.print(f"Skipped: {result.duplicates_skipped}")
    if counts["failed"]:
        raise typer.Exit(1)


@app.command("process")
def process_file(path: Path) -> None:
    """Process one file within dirty."""
    runtime = _runtime()
    with console.status("Reading") as progress:
        job = asyncio.run(runtime.processing.process(path, stage_callback=progress.update))
    console.print(f"[bold]{job.status.title()}[/] {job.id[:8]} — {job.findings_count} findings")
    if job.status != JobStatus.COMPLETED.value:
        raise typer.Exit(1)


@app.command()
def status(status_filter: Annotated[JobStatus | None, typer.Option("--status")] = None,
           limit: Annotated[int, typer.Option(min=1, max=500)] = 20) -> None:
    """Show safe recent job metadata with optional status filtering."""
    runtime = _runtime()
    statuses = {status_filter} if status_filter else None
    rows = runtime.repository.list_by_status(statuses, limit)
    table = Table(title="Cleanroom Jobs")
    table.add_column("Job", no_wrap=True)
    table.add_column("Filename", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Pages", no_wrap=True)
    for heading in ("Status", "Findings", "Model", "Started", "Duration", "Output"):
        table.add_column(heading, overflow="fold")
    for row in rows:
        duration = _duration(row)
        report_meta = _report_metadata(row)
        table.add_row(row.id[:8], row.source_filename,
                      str(report_meta.get("document_type", Path(row.source_filename).suffix.lstrip(".") or "text")),
                      str(report_meta.get("page_count") or "—"),
                      row.status, str(row.findings_count), row.model,
                      row.started_at.isoformat(timespec="seconds") if row.started_at else "—",
                      duration, row.output_path or "—")
    console.print(table)
    console.print(f"Pending supported files: {len(discover_files(
        runtime.settings.dirty_dir, runtime.settings.extension_set))}")


@app.command()
def show(job_id: str) -> None:
    """Show one job and its privacy-safe report metadata."""
    runtime = _runtime()
    matches = [row for row in runtime.repository.recent(500) if row.id == job_id or row.id.startswith(job_id)]
    if len(matches) != 1:
        console.print("[red]Job not found or ID prefix is ambiguous.[/]")
        raise typer.Exit(1)
    row = matches[0]
    payload = _job_dict(row)
    if row.report_path and Path(row.report_path).exists():
        report = json.loads(Path(row.report_path).read_text(encoding="utf-8"))
        payload["verification"] = report.get("verification", {})
        payload["findings_by_category"] = report.get("findings_by_category", {})
        for key in ("document_type", "page_count", "mapped_findings_count",
                    "redaction_rectangle_count", "pdf_security",
                    "structural_verification", "quarantine_reason"):
            payload[key] = report.get(key)
    console.print_json(json.dumps(payload, default=str))


@app.command("config")
def config_command() -> None:
    """Display resolved Ollama configuration without exposing credentials."""
    try:
        settings = Settings()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/] {_safe_configuration_error(exc)}")
        raise typer.Exit(2) from None
    endpoint = settings.validated_ollama_endpoint
    console.print(f"Connection Mode: {endpoint.mode.display_name}")
    console.print(f"Endpoint: {endpoint.safe_url}")
    console.print(f"Model: {settings.ollama_model}")
    console.print(f"Endpoint Type: {endpoint.kind.display_name}")


@configure_app.command("ollama")
def configure_ollama() -> None:
    """Interactively configure and validate an Ollama deployment."""
    console.print("[bold]Ollama connection setup[/]\n")
    console.print("1. Local Ollama (recommended)\n")
    console.print("2. Private-network Ollama\n   (LAN / VPN / Tailscale)\n")
    console.print("3. Custom endpoint\n")
    choice = typer.prompt("Select a deployment mode", type=int)
    modes = {1: ConnectionMode.LOCAL, 2: ConnectionMode.PRIVATE_NETWORK,
             3: ConnectionMode.CUSTOM}
    if choice not in modes:
        console.print("[red]Choose 1, 2, or 3.[/]")
        raise typer.Exit(2)
    mode = modes[choice]
    existing = _read_env(Path(".env"))
    default_url = existing.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    if mode is ConnectionMode.LOCAL:
        url = typer.prompt("Ollama endpoint", default="http://127.0.0.1:11434")
    else:
        if urlsplit(default_url).username is not None:
            console.print(f"Current endpoint: {format_safe_endpoint(default_url)}")
            url = typer.prompt("Ollama endpoint")
        else:
            url = typer.prompt("Ollama endpoint", default=default_url)
        console.print("[yellow]Remote Ollama has no built-in authentication by default. "
                      "Use a trusted network or a secured reverse proxy.[/]")

    allow_public = existing.get("CLEANROOM_ALLOW_PUBLIC_OLLAMA", "false").lower() == "true"
    allow_insecure = existing.get(
        "CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA", "false").lower() == "true"
    if mode is not ConnectionMode.LOCAL and url.lower().startswith("http://") and not allow_insecure:
        if not typer.confirm("Allow unencrypted HTTP to this remote endpoint?", default=False):
            console.print("[yellow]Configuration was not changed.[/]")
            raise typer.Exit(1)
        allow_insecure = True
    try:
        endpoint = validate_ollama_endpoint(
            url, mode, allow_public=allow_public, allow_insecure_remote=allow_insecure
        )
    except EndpointValidationError as exc:
        console.print(f"[red]Invalid Ollama endpoint:[/] {exc}")
        console.print("Configuration was not changed.")
        raise typer.Exit(2) from None

    updates = {
        "OLLAMA_CONNECTION_MODE": mode.value,
        "OLLAMA_BASE_URL": endpoint.url,
    }
    if allow_insecure:
        updates["CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA"] = "true"
    _update_env(Path(".env"), updates)
    console.print(f"[green]✓[/] Saved {mode.display_name} Ollama configuration")
    console.print(f"Endpoint: {endpoint.safe_url}")
    console.print("Run [bold]cleanroom doctor[/] to test the connection.")


@policies_app.callback(invoke_without_command=True)
def policies(ctx: typer.Context) -> None:
    """List bundled policies."""
    if ctx.invoked_subcommand is None:
        for path in sorted(Path("config").glob("*-policy.yaml")):
            policy = load_policy(path)
            console.print(f"[bold]{policy.name}[/] v{policy.version} — {policy.description}")


@policies_app.command("show")
def policy_show(name: str) -> None:
    path = _policy_path(name)
    policy = load_policy(path)
    console.print_json(data=policy.model_dump(mode="json"))


@policies_app.command("validate")
def policy_validate(path: Path) -> None:
    try:
        policy = load_policy(path)
    except PolicyError as exc:
        console.print(f"[red]Invalid policy:[/] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/] {policy.name} v{policy.version} is valid")


@app.command()
def demo(run: Annotated[bool, typer.Option("--run")] = False,
         demo_type: Annotated[str, typer.Option("--type")] = "text") -> None:
    """Create an entirely synthetic demonstration file, optionally processing it."""
    runtime = _runtime()
    if demo_type not in {"text", "pdf"}:
        console.print("[red]--type must be text or pdf[/]")
        raise typer.Exit(2)
    suffix = ".pdf" if demo_type == "pdf" else ".txt"
    destination = collision_safe(runtime.settings.dirty_dir, f"cleanroom-demo{suffix}")
    if demo_type == "pdf":
        create_synthetic_pdf(destination)
    else:
        destination.write_text(
            "This file contains synthetic demonstration data only.\n"
            "Name: Jane Example\nEmail: jane@example.test\nPhone: 312-555-0199\n",
            encoding="utf-8",
        )
    console.print(f"Created {destination}. All values are fake demonstration data.")
    if run:
        job = asyncio.run(runtime.processing.process(destination, check_stability=False))
        console.print(f"Demo result: {job.status}; job {job.id[:8]}")
        if job.status == "failed":
            raise typer.Exit(1)


@app.command()
def evaluate(
    detector: Annotated[str, typer.Option(help="regex, ollama, or combined")] = "combined",
    model: Annotated[str | None, typer.Option(help="Override the configured Ollama model")] = None,
) -> None:
    """Evaluate detectors against the bundled synthetic local dataset."""
    if detector not in {"regex", "ollama", "combined"}:
        console.print("[red]--detector must be regex, ollama, or combined[/]")
        raise typer.Exit(2)
    try:
        runtime = build_runtime(Settings(OLLAMA_MODEL=model)) if model else _runtime()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/] {exc}")
        raise typer.Exit(2) from exc
    pdf_handler = runtime.processing.handlers.for_path(Path("synthetic.pdf"))
    service = EvaluationService(runtime.processing.regex, runtime.processing.chunker,
        runtime.processing.policy,
        pdf_handler if isinstance(pdf_handler, PdfDocumentHandler) else None)
    cases_dir, expected_dir = bundled_evaluation_paths()
    try:
        summary = asyncio.run(service.evaluate(cases_dir, expected_dir,
                                               Path("evaluation-results"), detector))
    except Exception as exc:
        console.print(f"[red]Evaluation failed safely ({type(exc).__name__}).[/]")
        console.print("Check the synthetic dataset, private Ollama connection, model output, and chunk settings.")
        raise typer.Exit(1) from None
    console.print(f"Precision: {summary.precision:.3f}\nRecall: {summary.recall:.3f}\n"
                  f"F1: {summary.f1:.3f}\nRequired recall: {summary.required_finding_recall:.3f}\n"
                  f"Exact-span accuracy: {summary.exact_span_accuracy:.3f}\n"
                  f"Verification pass rate: {summary.verification_pass_rate:.3f}\n"
                  f"Invalid model responses/findings: {summary.invalid_model_findings}\n"
                  f"PDF cases: {summary.pdf_case_count}\n"
                  f"PDF mapping rate: {summary.pdf_exact_mapping_rate:.3f}\n"
                  f"PDF redaction rate: {summary.pdf_successful_redaction_rate:.3f}")
    failures = threshold_failures(summary, EvaluationThresholds(
        min_precision=runtime.settings.eval_min_precision,
        min_required_recall=runtime.settings.eval_min_required_recall,
        min_exact_span_accuracy=runtime.settings.eval_min_exact_span_accuracy,
        min_verification_pass_rate=runtime.settings.eval_min_verification_pass_rate,
        max_invalid_findings=runtime.settings.eval_max_invalid_findings,
        min_pdf_mapping_rate=runtime.settings.eval_min_pdf_mapping_rate,
        min_pdf_redaction_rate=runtime.settings.eval_min_pdf_redaction_rate,
        min_pdf_verification_rate=runtime.settings.eval_min_pdf_verification_rate,
    ))
    if failures:
        console.print("[red]Evaluation thresholds failed.[/]")
        console.print("Failed gates: " + ", ".join(failures))
        console.print("See evaluation-results/ for privacy-safe counts and metrics.")
        raise typer.Exit(1)
    console.print("[green]Evaluation thresholds passed.[/]")


@app.command()
def verify(path: Path) -> None:
    """Reopen and verify a sanitized text or PDF file."""
    runtime = _runtime()
    resolved = path.resolve()
    if not resolved.is_relative_to(runtime.settings.spotless_dir.resolve()) or resolved.is_symlink():
        console.print("[red]Output must be a regular file inside spotless.[/]")
        raise typer.Exit(2)
    handler = runtime.processing.handlers.for_path(resolved)
    structural: dict[str, object] = {}
    if isinstance(handler, PdfDocumentHandler):
        structural = handler.verify_output(resolved)
        extracted_text = handler.extract_output(resolved).text
    else:
        extracted_text = handler.extract(resolved).text
    result = asyncio.run(VerificationService(runtime.processing.regex, runtime.provider,
        runtime.processing.chunker).verify(extracted_text, set(),
                                            runtime.processing.policy, runtime.settings.ollama_verify))
    console.print_json(json.dumps({"verification": result.model_dump(mode="json"),
                                   "structural": structural}))
    if not result.passed or (structural and not structural.get("passed")):
        raise typer.Exit(1)


@app.command()
def inspect(path: Path) -> None:
    """Inspect PDF structure and support status without printing extracted text."""
    runtime = _runtime()
    try:
        resolved = validate_input(path, runtime.settings.dirty_dir,
            runtime.settings.max_file_size_mb * 1024 * 1024, {".pdf"})
        handler = runtime.processing.handlers.for_path(resolved)
        if not isinstance(handler, PdfDocumentHandler):
            raise ValueError("inspect currently supports PDF files only")
        inspection = handler.inspect(resolved)
    except (PdfError, ValueError) as exc:
        console.print_json(data={"filename": path.name, "supported": False,
                                 "error_code": type(exc).__name__})
        raise typer.Exit(1) from None
    payload = inspection.model_dump(mode="json")
    payload.update({"filename": resolved.name, "size_bytes": resolved.stat().st_size})
    console.print_json(data=payload)
    if not inspection.supported:
        raise typer.Exit(1)


@app.command()
def retry() -> None:
    """Retry eligible failed or interrupted files."""
    runtime = _runtime()
    jobs: list[JobRecord] = []
    for prior in runtime.repository.eligible_retries():
        source = Path(prior.source_path)
        if not source.exists():
            continue
        if source.resolve().is_relative_to(runtime.settings.failed_dir.resolve()):
            source = move_original(source, runtime.settings.dirty_dir)
        if source.resolve().is_relative_to(runtime.settings.dirty_dir.resolve()):
            jobs.append(asyncio.run(runtime.processing.process(source, check_stability=False)))
    console.print(f"Retried {len(jobs)} job(s)")
    if any(job.status == JobStatus.FAILED.value for job in jobs):
        raise typer.Exit(1)


@app.command()
def watch() -> None:
    """Watch dirty and process stable files until Ctrl+C."""
    runtime = _runtime()
    console.print(f"Watching {runtime.settings.dirty_dir}; press Ctrl+C to stop")
    try:
        asyncio.run(watch_folder(runtime.settings.dirty_dir, runtime.processing))
    except KeyboardInterrupt:
        console.print("Stopped cleanly")


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _safe_configuration_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        messages = [str(item.get("msg", "Invalid configuration")) for item in exc.errors()]
        return "; ".join(messages)
    return type(exc).__name__


def _update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)
    if output and remaining:
        output.append("")
    output.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


async def _doctor_ollama(runtime: Runtime) -> tuple[dict[str, object], str | None]:
    """Keep health and structured-output checks on one HTTP client's event loop."""
    health = await runtime.provider.health()
    if not health.get("model_installed"):
        return health, None
    try:
        await runtime.provider.detect("Synthetic clean test.", runtime.processing.policy)
    except Exception as exc:
        return health, type(exc).__name__
    return health, None


def _duration(row: JobRecord) -> str:
    if not row.started_at:
        return "—"
    end = row.completed_at or datetime.now(row.started_at.tzinfo)
    return f"{(end - row.started_at).total_seconds():.2f}s"


def _job_dict(job: JobRecord) -> dict[str, object]:
    return {key: getattr(job, key) for key in ("id", "source_filename", "status",
            "findings_count", "model", "output_path", "report_path", "verification_result",
            "error_code", "error_message", "created_at", "started_at", "completed_at")}


def _report_metadata(job: JobRecord) -> dict[str, object]:
    if not job.report_path or not Path(job.report_path).is_file():
        return {}
    try:
        value = json.loads(Path(job.report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _policy_path(name: str) -> Path:
    matches = [path for path in Path("config").glob("*-policy.yaml")
               if load_policy(path).name == name]
    if len(matches) != 1:
        console.print(f"[red]Unknown policy:[/] {name}")
        raise typer.Exit(1)
    return matches[0]
