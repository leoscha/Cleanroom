# Cleanroom architecture decisions

## Boundaries

Cleanroom uses a `src` layout and a layered architecture. CLI and FastAPI adapters
construct and call the same application services. `ProcessingService` owns the job
state machine; file, detector, provider, sanitizer, verifier, report, and repository
components remain independently testable.

The model integration is behind `DetectionProvider`. Only the Ollama provider may
perform model HTTP calls, and it accepts only an explicitly configured private or
loopback HTTP(S) endpoint. Prompt construction is versioned and separate from the
transport. No prompt or raw response is logged or persisted.

## Data and failure flow

One process-wide async lock limits the proof of concept to one active document.
An OS-level workspace lock also prevents independent processes from sharing the same
input workspace. Privacy-safe manifests support interrupted-job recovery.
Input paths are resolved beneath `dirty`, rejected when they are links or non-regular
files, checked for type-specific validity and size, and hashed. Detection combines validated
regex spans and validated exact strings returned by Ollama. Accepted, non-overlapping
spans are sanitized from right to left with per-document placeholder state.

Verification is fail-closed: accepted plaintext must be absent, deterministic and
optional model rescans must be clear, placeholders must be well-formed, and output
must round-trip through the active document handler. Only then is output atomically
committed to `spotless`.
The verifier protects policy-derived placeholder spans and uses a dedicated model
prompt. Large inputs are divided at paragraph or sentence boundaries with overlap;
local model spans are validated and converted back to global offsets.
Verification failures commit output to quarantine. In either analyzed case the
unchanged source is moved to `processed`; operational failures move it to `failed`.
Destinations never overwrite and use numeric suffixes on collision.

SQLite stores job metadata only. Reports store hashes, categories, confidence,
sources, counts, and sanitized errors—never source text or finding plaintext.
JSON and Markdown are emitted together. An explicitly enabled private diff is the
only artifact allowed to contain original text and is isolated under an ignored path.

`DocumentHandler` separates extraction, sanitization, writing, and output verification.
`DocumentHandlerRegistry` selects `TextDocumentHandler` or `PdfDocumentHandler` only
after common input gates pass. Processing services remain format-independent except
for coordinating the PDF handler's structural verification result.

## Main risks and controls

- **Data exfiltration:** Ollama endpoints are restricted to loopback and private IP
  addresses (including Tailscale CGNAT); redirects are disabled. No cloud provider
  exists in the application.
- **Prompt/response leakage:** document-bearing payloads are neither logged nor
  persisted. Exception text passes through a conservative secret redactor.
- **Path traversal and links:** resolved containment, pre-resolution symlink checks,
  regular-file checks, and supported-extension checks gate every input.
- **Partial copies and partial output:** size/mtime stability checks precede work;
  fsync plus same-directory atomic replacement commits generated artifacts.
- **Model hallucination:** categories, confidence, exact source strings, and all
  occurrences are validated locally. Invalid output fails the job.
- **Residual sensitive data:** deterministic and optional model verification occur
  before completion; uncertain output is quarantined.
- **Duplicate processing:** SHA-256 job lookup prevents a successful or active hash
  from being processed twice.
- **Secret persistence:** keyed values become hashes in reports, and SQLite has no
  finding/content columns.

## Milestones

1. Configuration, policy, schemas, safe file handling, and SQLite job history.
2. Regex and Ollama detection, deterministic merge, placeholders, and verification.
3. End-to-end lifecycle with atomic outputs and privacy-safe reports.
4. CLI, local metadata-only API, watcher, doctor/status/retry workflows.
5. Unit/integration tests, static checks, scripts, and verified documentation.

Office files, OCR/scanned PDFs, parallel workers, and a UI are explicitly deferred.

## Text-based PDF design

The document-handler registry selects a concrete handler only after the common path,
size, extension, symlink, stability, and hash gates pass. `TextDocumentHandler` keeps
the existing UTF-8 behavior. `PdfDocumentHandler` owns all PyMuPDF operations:
inspection, extraction, normalized-to-source mapping, rectangle generation, applied
redactions, metadata/annotation cleanup, atomic PDF writing, reopening, structural
inspection, and extraction verification. The shared processing service continues to
own detection, policy decisions, job state, lifecycle, and privacy-safe reporting.

PDF normalization emits every normalized character together with its source span and
page rectangle. Unicode NFKC, ligatures, nonbreaking spaces, repeated whitespace,
line breaks, and dehyphenation are deterministic. A finding is releasable only when
every non-whitespace normalized character maps to source glyph geometry at or above
the configured confidence. Mapping ambiguity, cross-page findings, unsupported
active content, encryption, malformed structure, or scanned/image-only pages fail
closed.

Redaction uses PyMuPDF redaction annotations followed by `apply_redactions`; visual
rectangles alone are never treated as sanitization. Label mode inserts placeholders
only when the mapped region can safely fit them, otherwise using an opaque redaction
and recording a fallback. Blank mode still removes underlying content. Output is
saved to a controlled temporary path, reopened from disk, checked structurally, and
re-extracted before atomic release.

PDF verification covers supported extraction paths, text dictionaries, metadata,
attachments, annotations, forms, encryption, and page counts. It does not claim
forensic irrecoverability against every historical, incremental-update, parser, or
low-level object recovery technique; full garbage collection on save and reopening
reduce risk but do not establish that stronger guarantee.

### PDF threat controls

- JavaScript, launch/external actions, embedded files, forms, and optional-content
  configurations are never executed or extracted; configured rejection is the
  default.
- Source PDFs are opened read-only and never overwritten. Outputs use controlled
  temporary files, full garbage collection, deflation, and collision-safe renames.
- Untrusted metadata values and extracted text never enter logs, SQLite, or reports.
- Comments and annotations are detected during inspection and removed when configured;
  forms, attachments, active actions, JavaScript, and optional-content layers fail closed.
- Pages with too little meaningful text are classified as likely scanned; OCR is not
  attempted and the job cannot complete successfully.
