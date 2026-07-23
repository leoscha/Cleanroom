# Contributing to Cleanroom

Thank you for helping build a safer local-first AI workflow. Please open an issue
before a large change so scope and privacy implications can be discussed early.

## Development setup

```bash
git clone https://github.com/leoscha/Cleanroom.git
cd Cleanroom
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cleanroom init
make check
```

Windows users can activate with `.venv\Scripts\Activate.ps1`.

## Pull requests

1. Create a focused branch and keep unrelated changes out.
2. Add tests for behavior changes. Use synthetic data only.
3. Run `pytest -q`, `ruff check .`, and `mypy src`.
4. Update relevant documentation and `CHANGELOG.md`.
5. Complete the pull request checklist.

Never commit real personal data, prompts, model responses, `.env` files, databases,
or private-review reports. Do not weaken fail-closed behavior without an explicit
security discussion. By contributing, you agree that your contribution is licensed
under Apache-2.0.

See the [architecture](../ARCHITECTURE.md), [philosophy](../docs/philosophy.md), and
[security policy](SECURITY.md) before changing trust boundaries.

