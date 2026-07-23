# Security model

Cleanroom is designed for local workspaces and a privately reachable Ollama server.
It rejects public Ollama IPs unless `CLEANROOM_ALLOW_PUBLIC_OLLAMA=true` is explicitly
set. That override is unsafe for normal use. HTTP redirects are disabled.

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

PDF redaction uses PyMuPDF redaction annotations followed by `apply_redactions`, a
full non-incremental save with garbage collection, and a disk reopen. Cleanroom never
executes JavaScript, launches actions, follows PDF links, or extracts attachments.
Forms, embedded files, active content, optional-content layers, uncertain finding
maps, malformed files, encrypted files, and likely scans fail closed. Metadata and
configured annotations are removed before release.

Cleanroom checks ordinary extraction, raw text dictionaries, metadata, page count,
encryption, annotations, attachments, forms, and active content. These controls do
not establish forensic irrecoverability against every PDF parser or recovery method.

Report vulnerabilities privately to the project owner. Do not attach real documents,
prompts, model responses, secrets, or databases to an issue.
