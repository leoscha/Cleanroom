# Upgrade guide

## Upgrade to v0.2.0

1. Back up `.env`, custom policies, and the workspace database.
2. Fetch the `v0.2.0` tag or pull the release branch.
3. Reinstall the package in the active virtual environment.
4. Apply the Ollama migration if the endpoint is remote.
5. Run the readiness and quality checks.

```bash
git fetch --tags
git checkout v0.2.0
source .venv/bin/activate
python -m pip install -e .
cleanroom version
cleanroom doctor
```

Expected version output:

```text
Cleanroom v0.2.0
```

`cleanroom init` remains non-destructive and can create newly required workspace
items without overwriting `.env` or an existing policy.

Contributors can install `.[dev]` and run `make check` after upgrading.

## Rollback

Stop watchers and API processes, check out the earlier revision, and reinstall it.
v0.2.0 does not require a destructive database migration. Preserve the workspace and
database until rollback validation is complete.
