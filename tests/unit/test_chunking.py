import asyncio

import pytest

from cleanroom.models.finding import Category, Finding
from cleanroom.services.chunking import ChunkedDetector, ChunkLimitError, split_text


def test_paragraph_boundaries_and_overlap() -> None:
    text = "First paragraph.\n\nSecond paragraph is longer.\n\nThird paragraph."
    chunks = split_text(text, 35, 5, 10)
    assert chunks[0].text.endswith("\n\n")
    assert chunks[1].overlap_before == 5
    assert chunks[0].global_end - chunks[1].global_start == 5


def test_long_paragraph_falls_back_and_offsets() -> None:
    text = "x" * 250
    chunks = split_text(text, 100, 10, 10)
    assert len(chunks) == 3
    assert all(chunk.text == text[chunk.global_start:chunk.global_end] for chunk in chunks)


def test_protected_finding_is_not_split() -> None:
    text = "a" * 90 + "John Smith" + "b" * 90
    protected = [Finding(text="John Smith", category=Category.PERSON_NAME, confidence=1,
                         source="regex", start=90, end=100, reason="test")]
    chunks = split_text(text, 95, 10, 10, protected)
    assert chunks[0].global_end == 100


def test_maximum_chunks_enforced() -> None:
    with pytest.raises(ChunkLimitError):
        split_text("x" * 1000, 101, 10, 2)


class RepeatedProvider:
    async def detect(self, text, policy):
        findings = []
        start = 0
        while (position := text.find("Jane", start)) >= 0:
            findings.append(Finding(text="Jane", category=Category.PERSON_NAME, confidence=.9,
                                    source="ollama", start=position, end=position + 4, reason="name"))
            start = position + 4
        return findings

    async def verify(self, text, policy):
        return await self.detect(text, policy)


def test_global_offsets_repeated_names_and_overlap_dedup(policy) -> None:
    text = "a" * 90 + "Jane" + "b" * 15 + "Jane"
    result = asyncio.run(ChunkedDetector(RepeatedProvider(), 101, 20, 10).detect(text, policy))
    assert [(item.start, item.end) for item in result.findings] == [(90, 94), (109, 113)]
    assert result.telemetry.chunk_count == 2
