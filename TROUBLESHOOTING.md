# Troubleshooting

## Doctor fails

- Public endpoint: set `OLLAMA_BASE_URL` to a loopback, RFC1918, or Tailscale IP.
- Unreachable Ollama: verify Tailscale, Windows Firewall, port 11434, and Ollama's
  listen address.
- Missing model: run `ollama pull MODEL_TAG` on the Ollama host.
- Structured output failure: inspect Ollama locally and choose a compatible model.
- Storage failure: run `cleanroom init` and check workspace permissions.

## Quarantine

Run `cleanroom show JOB_ID` and open the Markdown report. Quarantine means a real
value remained, a placeholder was malformed, model verification failed, or a policy
marked a review finding for quarantine. Fix the source/policy and use
`cleanroom retry` when eligible.

For a PDF, run `cleanroom inspect dirty/example.pdf` before processing or inspect the
job report afterward. Common safe-stop codes include `LIKELY_SCANNED_PDF` (OCR is not
available), `ENCRYPTED_PDF`, `PDF_FORMS`, `EMBEDDED_FILES`, `PDF_JAVASCRIPT`,
`EXTERNAL_ACTIONS`, `OPTIONAL_CONTENT`, and `PdfMappingError`. Mapping errors mean
normalized findings could not be traced to page geometry with sufficient confidence;
lowering the confidence threshold can redact unrelated text and is not recommended.

If a label does not fit its redacted region, Cleanroom uses an opaque fallback and
records the count. This is expected and is not a failed redaction. Use
`CLEANROOM_PDF_REPLACEMENT_MODE=blank` or `black_box` when labels are undesirable.

## Duplicate or lock errors

A duplicate hash is intentionally skipped. “Another Cleanroom process” means a scan,
watcher, or API process owns the workspace lock; stop it cleanly before retrying.
