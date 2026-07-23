# Cleanroom

Cleanroom is a local-first Python 3.12 application that removes sensitive data from
UTF-8 text and digitally generated, text-based PDFs using deterministic rules plus a
privately hosted Ollama model. It writes a verified copy, preserves the original,
tracks metadata in SQLite, and produces safe JSON and Markdown reports.

> **Warning:** Cleanroom reduces the risk of sensitive-data exposure but does not
> guarantee that every sensitive item will be detected. Review quarantined files and
> use strict policies for high-risk documents.

Cleanroom does not support scanned/image-only PDFs, OCR, DOCX, spreadsheets, cloud
inference, a browser UI, or multiple users. PDFs with encryption, forms, attachments,
JavaScript, launch actions, or uncertain text mapping fail closed.

> **PDF limitation:** Cleanroom verifies that redacted values are absent from
> supported extraction paths, but this MVP does not claim forensic sanitization
> against every possible PDF recovery technique.

## Five-minute setup

macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cleanroom init
# Edit .env with a real private OLLAMA_BASE_URL and installed OLLAMA_MODEL
cleanroom doctor
cleanroom demo --run
cleanroom demo --type pdf --run
cleanroom status
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cleanroom init
# Edit .env
cleanroom doctor
cleanroom demo --run
cleanroom status
```

On Fedora, install Python with `sudo dnf install python3.12 python3.12-devel`, then use
the Linux commands. `cleanroom init` creates directories, `.env`, the default policy,
and SQLite without overwriting existing configuration.

## Everyday commands

```bash
cleanroom scan
cleanroom watch
cleanroom process dirty/example.txt
cleanroom process dirty/example.pdf
cleanroom inspect dirty/example.pdf
cleanroom status --status quarantined --limit 20
cleanroom show JOB_ID
cleanroom verify spotless/example-clean.txt
cleanroom verify spotless/example-clean.pdf
cleanroom retry
cleanroom config
cleanroom policies
cleanroom policies show strict
cleanroom policies validate config/custom-policy.yaml
cleanroom evaluate --detector regex
```

`doctor` prints an actionable readiness checklist. `scan` reports completed,
quarantined, failed, and duplicate counts. `show` displays safe job/report metadata.
Reports explain categories, detector sources, replacements, verification, quarantine,
and safe next actions without matched plaintext.

For PDFs, Cleanroom extracts positioned glyphs with PyMuPDF, normalizes text while
retaining a per-character source map, maps accepted findings to precise page
rectangles, applies and flattens real PDF redactions, removes metadata and supported
annotations, saves a fresh PDF, then reopens it for structural and text verification.
`label`, `black_box`, and `blank` replacement modes are available; `label` is the
default. `cleanroom inspect` reports structure and support status without printing
document text. See [PDF support](docs/pdf-support.md).

Verification has five stages: original-value absence, policy-aware placeholder
parsing, deterministic rescanning outside placeholders, a dedicated Ollama verifier
prompt, and strict model-finding validation. A file is quarantined when real content
remains, placeholders are malformed, verification errors, or the policy requires
review. Generated placeholders are safe and ignored.

## Ollama over Tailscale

On Windows PowerShell, an Ollama host can listen on network interfaces with:

```powershell
$env:OLLAMA_HOST="0.0.0.0:11434"; ollama serve
```

Restrict Windows Firewall and Tailscale ACLs to the Cleanroom client. **Never expose
Ollama publicly.** Public endpoints are rejected unless the explicit unsafe override
is enabled. See [Ollama setup](docs/ollama-setup.md).

## API and development

```bash
uvicorn cleanroom.api.app:app --host 127.0.0.1 --port 8000
pytest -q
ruff check .
mypy src
```

Metadata-only routes: `GET /health`, `/ready`, `/config`, `/jobs`, `/jobs/{id}`,
`/policies`; `POST /scan`, `/process`, and `/retry/{id}`. Job listing supports
pagination and status filters. Responses include request IDs. Never bind publicly.

Normal tests mock Ollama. Optional live tests require
`CLEANROOM_RUN_LIVE_OLLAMA=1` and are marked `live_ollama`.

## Privacy and optional review diffs

Documents go only to the configured Ollama endpoint. Logs, SQLite, and ordinary
reports exclude document and finding plaintext. `CLEANROOM_WRITE_REVIEW_DIFF=true`
creates local files under `reports/private-review/` that may contain the entire
original sensitive document; it is disabled by default and ignored by Git.

Further reading: [architecture](ARCHITECTURE.md), [security](SECURITY.md),
[privacy](PRIVACY.md), [troubleshooting](TROUBLESHOOTING.md),
[policies](docs/policies.md), [evaluation](docs/evaluation.md), and
[file lifecycle](docs/file-lifecycle.md), and [PDF support](docs/pdf-support.md).
