# File lifecycle

A successful job moves an unchanged original from `dirty/` to `processed/`, writes
the verified copy to `spotless/`, and creates JSON and Markdown reports. Failed
operations move the original to `failed/`. Verification or policy-review failures
move the unchanged original to `processed/` and sanitized output to quarantine.

Per-job manifests under `.cleanroom/tmp` track pending, reading, detecting,
sanitizing, verifying, and writing stages. Startup marks active database jobs as
interrupted and removes stale manifests while holding the workspace lock. Interrupted
and failed jobs are retry eligible. Atomic writes and collision suffixes prevent
partial files and overwrites. Set `CLEANROOM_ARCHIVE_PROCESSED=false` only when an
unchanged original must remain in `dirty/`; duplicate hashes prevent reprocessing.

PDF jobs add inspection, mapping, redaction, disk reopen, structural verification,
normal extraction verification, text-dictionary verification, and metadata checks.
An unsupported PDF is quarantined without a released output; its unchanged source is
moved to `processed/` and its safe reason is recorded. A PDF that was sanitized but
fails verification is written only to `spotless/quarantine/`.
