# Changelog

All notable changes to Cleanroom are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A loopback-only, privacy-safe review queue foundation at `cleanroom review`.
- Server-rendered quarantined-job navigation with strict output escaping, no external
  assets, no-store responses, and a restrictive Content Security Policy.

Approval mutations remain intentionally disabled until decision persistence, fresh
verification, CSRF protection, and auditable state transitions are implemented.

## [0.3.0] — 2026-07-29 — Native PDF

### Added

- Multipage and repeated-value PDF evaluation fixtures with separate mapping,
  redaction, and verification gates.
- Default rejection of PDF images that cannot be inspected without OCR, with an
  explicit operator override for previously reviewed nonsensitive images.

### Fixed

- Windows workspace locks now consistently acquire and release byte zero even after
  the lock file has recorded a prior process identifier.

### Changed

- Text-based PDF support graduates from early capability to a supported format.
- PDFs containing images now fail closed by default because Cleanroom cannot inspect
  or sanitize their pixels without OCR. Reviewed images can be preserved only through
  the explicit `CLEANROOM_PDF_REJECT_IMAGES=false` override.

## [0.2.1] — 2026-07-29 — Text Foundation Stabilization

### Added

- A reproducible 120-case synthetic regression corpus covering deterministic
  identifiers, assignments, combined findings, boundary cases, and safe negatives.
- Release gates for exact spans, verification, invalid findings, and PDF mapping,
  redaction, and verification in addition to precision and required recall.
- Cross-platform CI tests on Linux, macOS, and Windows, plus deterministic evaluation
  and clean-wheel installation jobs.
- Privacy-safe per-case verification and quarantine results in evaluation reports.

### Fixed

- IPv4 addresses immediately followed by sentence punctuation are detected without
  accepting a fifth dotted component.

### Changed

- `cleanroom evaluate` prints every enforced quality metric and stable failure codes.
- The bundled evaluation suite now contains 128 cases: 120 generated regression
  cases, seven focused text fixtures, and one generated text-based PDF.

No configuration or database migration is required from v0.2.0.

## [0.2.0] — 2026-07-22 — Text Foundation

### Added

- Local-first TXT sanitization with deterministic and private Ollama detection.
- Chunked contextual analysis with global offsets and overlap-aware finding merges.
- Consistent placeholders, label preservation, verification, and fail-closed quarantine.
- SQLite job history, duplicate prevention, atomic lifecycle operations, and safe reports.
- Explicit `local`, `private-network`, and `custom` Ollama connection modes.
- Centralized IP, DNS, URL, redirect, and transport-security validation.
- Guided `cleanroom configure ollama` setup and expanded `doctor` diagnostics.
- Text-based PDF support as an early capability; broader native PDF support remains
  scheduled for v0.3 hardening.
- Open-source governance, CI, release automation, demos, examples, and release docs.

### Changed

- Local Ollama at `http://127.0.0.1:11434` is now the default.
- Product positioning is now “a local-first AI Privacy Gateway.”
- Public Ollama endpoints remain blocked by default; remote plain HTTP requires a
  separate explicit acknowledgement.

### Migration

Existing remote configurations are not changed automatically. Add
`OLLAMA_CONNECTION_MODE=private-network` for RFC1918, private IPv6, or Tailscale
deployments. Remote plain HTTP also requires
`CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=true`. See the
[migration notes](docs/migration-v0.2.0.md).

[0.2.0]: https://github.com/leoscha/Cleanroom/releases/tag/v0.2.0
[0.2.1]: https://github.com/leoscha/Cleanroom/releases/tag/v0.2.1
[0.3.0]: https://github.com/leoscha/Cleanroom/releases/tag/v0.3.0
