from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cleanroom.config.policies import load_policy
from cleanroom.config.settings import endpoint_network_kind
from cleanroom.files.lifecycle import move_original
from cleanroom.models.job import JobStatus
from cleanroom.runtime import Runtime


class ProcessRequest(BaseModel):
    path: str


def metadata(job: object) -> dict[str, object]:
    keys = (
        "id", "source_filename", "source_hash", "status", "output_path", "report_path",
        "model", "policy_name", "policy_version", "findings_count", "verification_result",
        "error_code", "error_message", "created_at", "started_at", "completed_at",
    )
    return {key: getattr(job, key) for key in keys}


def build_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "ollama": await runtime.provider.health()}

    @router.get("/ready", summary="Check whether local dependencies are ready")
    async def ready() -> dict[str, object]:
        health = await runtime.provider.health()
        storage = all(path.is_dir() for path in runtime.settings.required_dirs)
        ready_state = storage and bool(health.get("reachable")) and bool(health.get("model_installed"))
        return {"ready": ready_state, "storage": storage, "ollama": health}

    @router.get("/config", summary="Return privacy-safe resolved configuration")
    async def config() -> dict[str, object]:
        return {"dirty_dir": str(runtime.settings.dirty_dir),
                "spotless_dir": str(runtime.settings.spotless_dir),
                "policy": runtime.processing.policy.name,
                "model": runtime.settings.ollama_model,
                "ollama_network": endpoint_network_kind(runtime.settings.ollama_base_url),
                "verify_output": runtime.settings.verify_output,
                "ollama_verify": runtime.settings.ollama_verify}

    @router.get("/policies", summary="List bundled policy metadata")
    async def policies() -> list[dict[str, object]]:
        return [{"name": policy.name, "version": policy.version, "description": policy.description}
                for policy in (load_policy(path) for path in sorted(Path("config").glob("*-policy.yaml")))]

    @router.get("/jobs")
    async def jobs(limit: int = 20, offset: int = 0,
                   status: JobStatus | None = None) -> list[dict[str, object]]:
        limit = min(max(limit, 1), 500)
        return [metadata(job) for job in runtime.repository.list_by_status(
            {status} if status else None, limit, max(offset, 0))]

    @router.get("/jobs/{job_id}")
    async def job(job_id: str) -> dict[str, object]:
        row = runtime.repository.get(job_id)
        if row is None:
            raise HTTPException(404, "job not found")
        return metadata(row)

    @router.post("/scan")
    async def scan() -> dict[str, object]:
        result = await runtime.scanning.scan()
        return {"discovered": result.discovered, "duplicates_skipped": result.duplicates_skipped,
                "jobs": [metadata(row) for row in result.jobs]}

    @router.post("/process")
    async def process(request: ProcessRequest) -> dict[str, object]:
        return metadata(await runtime.processing.process(Path(request.path)))

    @router.post("/retry/{job_id}")
    async def retry(job_id: str) -> dict[str, object]:
        row = runtime.repository.get(job_id)
        if row is None or row.status != "failed":
            raise HTTPException(409, "job is not eligible for retry")
        source = Path(row.source_path)
        if not source.exists():
            raise HTTPException(409, "failed source is no longer available")
        restored = move_original(source, runtime.settings.dirty_dir)
        return metadata(await runtime.processing.process(restored, check_stability=False))

    return router
