import os
from pathlib import Path

import pytest

from cleanroom.config.settings import Settings
from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy

# Keep test collection independent of a developer's workspace .env.
os.environ["OLLAMA_CONNECTION_MODE"] = "local"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"


@pytest.fixture
def policy() -> SanitizationPolicy:
    actions = {category.value: "replace" for category in __import__(
        "cleanroom.models.finding", fromlist=["Category"]).Category}
    actions.update({"SSN": "redact", "CREDIT_CARD": "redact", "API_KEY": "redact",
                    "PASSWORD": "redact", "SECRET": "redact", "OTHER": "ignore"})
    placeholders = {key: ("PROJECT" if key == "PROJECT_NAME" else key) for key in actions}
    return SanitizationPolicy.model_validate({"name": "test", "version": 1,
        "minimum_confidence": 0.7, "actions": actions, "placeholders": placeholders})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    directories = {name: tmp_path / name for name in ("dirty", "spotless", "processed",
                                                        "failed", "reports")}
    for directory in directories.values():
        directory.mkdir()
    quarantine = directories["spotless"] / "quarantine"
    quarantine.mkdir()
    return Settings(CLEANROOM_DIRTY_DIR=directories["dirty"],
        CLEANROOM_SPOTLESS_DIR=directories["spotless"],
        CLEANROOM_PROCESSED_DIR=directories["processed"],
        CLEANROOM_FAILED_DIR=directories["failed"],
        CLEANROOM_REPORTS_DIR=directories["reports"],
        CLEANROOM_QUARANTINE_DIR=quarantine,
        CLEANROOM_TEMP_DIR=tmp_path / ".cleanroom" / "tmp",
        CLEANROOM_DATABASE_URL=f"sqlite:///{tmp_path / 'jobs.db'}",
        CLEANROOM_POLICY_PATH=Path("config/default-policy.yaml"),
        OLLAMA_CONNECTION_MODE="private-network",
        OLLAMA_BASE_URL="http://100.64.0.1:11434", OLLAMA_MODEL="test:latest",
        CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA=True,
        CLEANROOM_FILE_STABILITY_SECONDS=0, CLEANROOM_OLLAMA_VERIFY=False)


class FakeProvider:
    def __init__(self, findings: list[Finding] | None = None, fail: bool = False) -> None:
        self.findings = findings or []
        self.fail = fail

    async def detect(self, text: str, policy: SanitizationPolicy) -> list[Finding]:
        if self.fail:
            raise RuntimeError("provider failed secret=do-not-store")
        return [item for item in self.findings if item.matches(text)]

    async def verify(self, text: str, policy: SanitizationPolicy) -> list[Finding]:
        return await self.detect(text, policy)

    async def health(self) -> dict[str, object]:
        return {"reachable": True, "model_installed": True}
