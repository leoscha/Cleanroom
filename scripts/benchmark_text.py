"""Run the release TXT benchmark against a local Ollama model and record metadata."""

import argparse
import asyncio
import json
import platform
import subprocess
import time
from pathlib import Path

from cleanroom.config.ollama_endpoint import validate_ollama_endpoint
from cleanroom.config.policies import load_policy
from cleanroom.config.settings import Settings
from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.providers.ollama import OllamaDetectionProvider
from cleanroom.services.chunking import ChunkedDetector
from cleanroom.services.evaluation_service import EvaluationService


async def benchmark(model: str, output: Path, hardware: str) -> None:
    settings = Settings(_env_file=None, OLLAMA_MODEL=model)
    endpoint = validate_ollama_endpoint("http://127.0.0.1:11434", "local")
    provider = OllamaDetectionProvider(
        endpoint, model, settings.ollama_timeout_seconds, settings.ollama_max_retries
    )
    policy = load_policy(Path("config/default-policy.yaml"))
    chunker = ChunkedDetector(
        provider, settings.chunk_max_chars, settings.chunk_overlap_chars,
        settings.max_chunks_per_file,
    )
    service = EvaluationService(RegexDetector(), chunker, policy)
    cases = sorted(Path("evaluation/cases").glob("*.txt"))
    character_count = sum(len(path.read_text(encoding="utf-8")) for path in cases)
    await provider.detect("Synthetic warm-up sentence with no identifiers.", policy)
    started = time.monotonic()
    try:
        summary = await service.evaluate(
            Path("evaluation/cases"), Path("evaluation/expected"), output, "combined"
        )
    finally:
        await provider.client.aclose()
    elapsed = time.monotonic() - started
    try:
        ollama_version = subprocess.run(
            ["ollama", "--version"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        ollama_version = "unknown"
    data = {
        **summary.__dict__,
        "benchmark_scope": "TXT processing with combined regex and Ollama detection",
        "model": model,
        "endpoint": "local loopback",
        "hardware": hardware,
        "operating_system": platform.platform(),
        "ollama_version": ollama_version,
        "dataset": "evaluation/cases/*.txt",
        "dataset_revision": "v0.2.0",
        "total_characters": character_count,
        "wall_time_seconds": elapsed,
        "documents_per_second": len(cases) / elapsed,
        "characters_per_second": character_count / elapsed,
        "warmup_requests": 1,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "benchmark.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemma3:4b")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/gemma3-4b-local"))
    parser.add_argument("--hardware", required=True)
    arguments = parser.parse_args()
    asyncio.run(benchmark(arguments.model, arguments.output, arguments.hardware))


if __name__ == "__main__":
    main()
