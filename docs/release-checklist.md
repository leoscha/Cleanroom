# Release checklist

Use this checklist for every public release. Do not check an item until the linked
evidence exists.

- [x] Tests passing locally
- [x] CI passing on the release commit
- [x] Documentation complete and links checked
- [x] `CHANGELOG.md` updated
- [x] Version bumped in package metadata and CLI
- [x] Synthetic demo validated
- [x] Wheel and Quick Start validated in an isolated environment
- [x] Release notes written
- [x] Version tag created and pushed
- [x] GitHub Release published

After publication, verify the release title, attached notes, source archives, badges,
and Quick Start from a clean clone. Record any exception in the release notes.

## v0.2.0 record

- Release: [Text Foundation](https://github.com/leoscha/Cleanroom/releases/tag/v0.2.0)
- Release CI: [passed](https://github.com/leoscha/Cleanroom/actions/runs/29971665426)
- Release workflow: [passed](https://github.com/leoscha/Cleanroom/actions/runs/29971675974)
- Label synchronization: [passed](https://github.com/leoscha/Cleanroom/actions/runs/29971775428)

## v0.2.1 record

- Release: [Text Foundation Stabilization](https://github.com/leoscha/Cleanroom/releases/tag/v0.2.1)
- Cross-platform release CI: [passed](https://github.com/leoscha/Cleanroom/actions/runs/30479767415)
- Release workflow: [passed](https://github.com/leoscha/Cleanroom/actions/runs/30479955513)
- Local validation: 100 passed, 1 opt-in live-Ollama test skipped; Ruff and mypy passed
- Deterministic gate: precision 1.000, required recall 1.000, exact-span accuracy 0.952,
  verification 1.000, and generated-PDF mapping/redaction/verification 1.000

## v0.3.0 record

- Release: [Native PDF](https://github.com/leoscha/Cleanroom/releases/tag/v0.3.0)
- Cross-platform release CI: [passed](https://github.com/leoscha/Cleanroom/actions/runs/30480480998)
- Release workflow: [passed](https://github.com/leoscha/Cleanroom/actions/runs/30480614058)
- Local validation: 105 passed, 1 opt-in live-Ollama test skipped; Ruff and mypy passed
- PDF gate: three generated layouts with mapping, redaction, structural verification,
  metadata sanitization, and original-absence checks passing
