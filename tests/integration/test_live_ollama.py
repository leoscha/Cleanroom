import asyncio
import os
from pathlib import Path

import pytest

from cleanroom.config.policies import load_policy
from cleanroom.config.settings import Settings
from cleanroom.providers.ollama import OllamaDetectionProvider


@pytest.mark.live_ollama
def test_private_ollama_structured_output() -> None:
    if os.getenv("CLEANROOM_RUN_LIVE_OLLAMA") != "1":
        pytest.skip("set CLEANROOM_RUN_LIVE_OLLAMA=1 to enable private live testing")
    settings = Settings()
    provider = OllamaDetectionProvider(settings.ollama_base_url, settings.ollama_model,
                                       settings.ollama_timeout_seconds,
                                       settings.ollama_max_retries)
    findings = asyncio.run(provider.detect(
        "Synthetic person Jane Example.", load_policy(Path(settings.policy_path))))
    assert isinstance(findings, list)
