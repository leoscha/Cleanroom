# Security model

Cleanroom is a local-first AI Privacy Gateway that sanitizes sensitive information
before documents are shared with AI systems.

Cleanroom defaults to Ollama on `127.0.0.1`. Remote inference requires an explicit
`private-network` or `custom` connection mode. It resolves and validates every host
address, rejects mixed public/private DNS answers, and rejects public endpoints unless
`CLEANROOM_ALLOW_PUBLIC_OLLAMA=true` is explicitly set. That override is unsafe for
normal use. Remote plain HTTP separately requires
`CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true`. Redirects are followed only after the
destination passes the same endpoint policy.

Cleanroom never changes firewall rules, starts Ollama, or configures Ollama to listen
on `0.0.0.0`. Ollama has no built-in authentication by default; protect any remote
instance with network controls or an authenticated TLS reverse proxy.

Inputs must be regular supported `.txt` or `.pdf` files beneath `dirty/`; links,
traversal, devices, unsupported types, unstable copies, and oversized files are
rejected. Text must be UTF-8. PDFs must be unencrypted, structurally readable, and
contain meaningful extractable text.
Atomic writes, collision-safe names, a workspace lock, manifests, and interrupted-job
recovery protect lifecycle integrity.

Cleanroom never logs document content, prompts, responses, or finding plaintext.
SQLite stores job metadata only. JSON and Markdown reports use hashes. Private review
diffs are disabled by default and may contain the full original sensitive content.

Cleanroom reduces the risk of sensitive-data exposure but does not guarantee that
every sensitive item will be detected. Review quarantined files and use strict
policies for high-risk documents.

## What Cleanroom does not guarantee

- AI detection is probabilistic; false negatives and false positives remain possible.
- Human review may still be required for ambiguous or high-impact material.
- OCR and image-only PDFs are not supported.
- Unsupported formats are rejected rather than silently or partially processed.
- Supported PDF checks do not establish forensic irrecoverability against every parser.
- Cleanroom cannot protect data on a compromised host or malicious Ollama server.
- Enabling private-review diffs, public inference, or insecure remote HTTP expands the
  threat surface and shifts responsibility to the operator.

PDF redaction uses PyMuPDF redaction annotations followed by `apply_redactions`, a
full non-incremental save with garbage collection, and a disk reopen. Cleanroom never
executes JavaScript, launches actions, follows PDF links, or extracts attachments.
Forms, embedded files, active content, optional-content layers, uncertain finding
maps, malformed files, encrypted files, and likely scans fail closed. Metadata and
configured annotations are removed before release.

Cleanroom checks ordinary extraction, raw text dictionaries, metadata, page count,
encryption, annotations, attachments, forms, and active content. These controls do
not establish forensic irrecoverability against every PDF parser or recovery method.

Report vulnerabilities through the repository's [private security
process](.github/SECURITY.md). Do not attach real documents, prompts, model responses,
secrets, or databases to an issue.
