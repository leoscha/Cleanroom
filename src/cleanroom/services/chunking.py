import time
from dataclasses import dataclass

from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.providers.base import DetectionProvider


class ChunkLimitError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    index: int
    global_start: int
    global_end: int
    text: str
    overlap_before: int
    overlap_after: int


@dataclass(frozen=True)
class ChunkTelemetry:
    chunk_count: int
    average_chunk_duration: float
    total_inference_duration: float
    retry_count: int = 0
    invalid_finding_count: int = 0


@dataclass(frozen=True)
class ChunkDetectionResult:
    findings: list[Finding]
    telemetry: ChunkTelemetry


def split_text(
    text: str,
    max_chars: int,
    overlap_chars: int,
    max_chunks: int,
    protected: list[Finding] | None = None,
) -> list[TextChunk]:
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("chunk overlap must be non-negative and smaller than chunk size")
    protected_spans = [(item.start, item.end) for item in (protected or [])]
    raw: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        if len(raw) >= max_chunks:
            raise ChunkLimitError(f"document exceeds maximum of {max_chunks} chunks")
        target = min(start + max_chars, len(text))
        end = target if target == len(text) else _boundary(text, start, target)
        for protected_start, protected_end in protected_spans:
            if protected_start < end < protected_end:
                end = protected_end
        end = min(end, len(text))
        if end <= start:
            end = target
        raw.append((start, end))
        if end == len(text):
            break
        start = max(start + 1, end - overlap_chars)
    chunks: list[TextChunk] = []
    for index, (chunk_start, chunk_end) in enumerate(raw):
        previous_end = raw[index - 1][1] if index else chunk_start
        next_start = raw[index + 1][0] if index + 1 < len(raw) else chunk_end
        chunks.append(TextChunk(index, chunk_start, chunk_end, text[chunk_start:chunk_end],
                                max(0, previous_end - chunk_start),
                                max(0, chunk_end - next_start)))
    return chunks


def _boundary(text: str, start: int, target: int) -> int:
    minimum = start + max(1, (target - start) // 2)
    paragraph = text.rfind("\n\n", minimum, target + 1)
    if paragraph >= minimum:
        return paragraph + 2
    for marker in (". ", "! ", "? ", "\n"):
        position = text.rfind(marker, minimum, target + 1)
        if position >= minimum:
            return position + len(marker)
    return target


class ChunkedDetector:
    def __init__(self, provider: DetectionProvider, max_chars: int, overlap_chars: int,
                 max_chunks: int) -> None:
        self.provider = provider
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.max_chunks = max_chunks

    async def detect(self, text: str, policy: SanitizationPolicy,
                     protected: list[Finding] | None = None,
                     verification: bool = False) -> ChunkDetectionResult:
        chunks = split_text(text, self.max_chars, self.overlap_chars, self.max_chunks, protected)
        findings: list[Finding] = []
        invalid = 0
        durations: list[float] = []
        for chunk in chunks:
            started = time.monotonic()
            local = (await self.provider.verify(chunk.text, policy) if verification
                     else await self.provider.detect(chunk.text, policy))
            durations.append(time.monotonic() - started)
            for item in local:
                global_item = item.model_copy(update={
                    "start": item.start + chunk.global_start,
                    "end": item.end + chunk.global_start,
                })
                if global_item.matches(text):
                    findings.append(global_item)
                else:
                    invalid += 1
        unique: dict[tuple[int, int, str], Finding] = {}
        for item in findings:
            key = (item.start, item.end, item.category.value)
            if key not in unique or item.confidence > unique[key].confidence:
                unique[key] = item
            else:
                unique[key].sources.update(item.sources)
        total = sum(durations)
        telemetry = ChunkTelemetry(len(chunks), total / len(chunks) if chunks else 0,
                                   total, invalid_finding_count=invalid)
        return ChunkDetectionResult(sorted(unique.values(), key=lambda item: item.start), telemetry)
