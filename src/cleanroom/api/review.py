import html
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import HTMLResponse

from cleanroom.database.models import JobRecord
from cleanroom.models.job import JobStatus
from cleanroom.runtime import Runtime


def build_review_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/review", include_in_schema=False)

    @router.get("", response_class=HTMLResponse)
    async def dashboard() -> str:
        jobs = runtime.repository.list_by_status({JobStatus.QUARANTINED}, 100)
        rows = "".join(_job_row(job) for job in jobs)
        if not rows:
            rows = '<tr><td colspan="5" class="empty">No quarantined jobs.</td></tr>'
        body = (
            "<h1>Review queue</h1>"
            "<p class=lede>Privacy-safe metadata only. Original and matched values are never shown.</p>"
            "<table><thead><tr><th>Job</th><th>File</th><th>Status</th>"
            f"<th>Findings</th><th>Created</th></tr></thead><tbody>{rows}</tbody></table>"
        )
        return _page("Review queue", body)

    @router.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def detail(job_id: str) -> str:
        job = runtime.repository.get(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        report = _safe_report(job)
        fields = (
            ("Job", job.id), ("File", job.source_filename), ("Status", job.status),
            ("Findings", str(job.findings_count)), ("Model", job.model),
            ("Policy", f"{job.policy_name} v{job.policy_version}"),
            ("Created", job.created_at.isoformat()),
            ("Verification", str(job.verification_result)),
            ("Error code", job.error_code or "—"),
        )
        items = "".join(
            f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>"
            for label, value in fields
        )
        safe_json = html.escape(json.dumps(report, indent=2, sort_keys=True, default=str))
        body = (
            '<p><a href="/review">← Review queue</a></p>'
            f"<h1>Job {html.escape(job.id[:8])}</h1><dl>{items}</dl>"
            "<h2>Safe report details</h2>"
            f"<pre>{safe_json}</pre>"
            '<p class="notice">Approval actions are intentionally unavailable in this foundation. '
            "Use the CLI and inspect the privacy-safe report before changing policy.</p>"
        )
        return _page(f"Job {job.id[:8]}", body)

    return router


def _job_row(job: JobRecord) -> str:
    return (
        f'<tr><td><a href="/review/jobs/{html.escape(job.id)}">{html.escape(job.id[:8])}</a></td>'
        f"<td>{html.escape(job.source_filename)}</td><td>{html.escape(job.status)}</td>"
        f"<td>{job.findings_count}</td><td>{html.escape(job.created_at.isoformat())}</td></tr>"
    )


def _safe_report(job: JobRecord) -> dict[str, object]:
    if not job.report_path:
        return {}
    path = Path(job.report_path)
    if not path.is_file():
        return {}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"report_status": "unavailable"}
    keys = (
        "document_type", "page_count", "findings_count", "findings_by_category",
        "findings_by_source", "verification", "structural_verification",
        "pdf_security", "quarantine_reason", "error",
    )
    return {key: report[key] for key in keys if key in report}


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Cleanroom</title>
<style>
:root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
body {{ max-width: 72rem; margin: 0 auto; padding: 2rem; background: #0f172a; color: #e2e8f0; }}
a {{ color: #7dd3fc; }} table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; }}
th,td {{ padding: .75rem; border-bottom: 1px solid #334155; text-align: left; }}
th {{ color: #93c5fd; }} .lede,.empty {{ color: #94a3b8; }}
dl {{ display: grid; grid-template-columns: 10rem 1fr; gap: .6rem; }} dt {{ color: #93c5fd; }}
dd {{ margin: 0; overflow-wrap: anywhere; }} pre {{ padding: 1rem; overflow: auto; background: #020617; }}
.notice {{ padding: 1rem; border: 1px solid #475569; border-radius: .5rem; color: #cbd5e1; }}
</style></head><body>{body}</body></html>"""
