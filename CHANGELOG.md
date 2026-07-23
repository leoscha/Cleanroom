# Changelog

All notable changes to Cleanroom are documented here. This project follows
[Semantic Versioning](https://semver.org/).

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

