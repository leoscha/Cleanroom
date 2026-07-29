import asyncio
import json

import httpx
import pytest

from cleanroom.config.ollama_endpoint import validate_ollama_endpoint
from cleanroom.detectors.merge import merge_findings
from cleanroom.detectors.regex_detector import RegexDetector, luhn_valid
from cleanroom.models.finding import Category, Finding
from cleanroom.providers.ollama import OllamaDetectionProvider, ProviderError
from cleanroom.sanitizers.text_sanitizer import sanitize_text
from cleanroom.services.verification_service import VerificationService


def finding(text: str, category: Category, start: int, source: str = "ollama",
            confidence: float = .9) -> Finding:
    return Finding(text=text, category=category, confidence=confidence, source=source,
                   start=start, end=start + len(text), reason="test")


def test_regex_categories_and_luhn(policy) -> None:
    text = ("a@b.com 312-555-0199 123-45-6789 10.0.0.1 https://x.test "
            "4111 1111 1111 1111 sk-abcdefghijklmnop Bearer abc.def password=hunter2 "
            "secret=value -----BEGIN PRIVATE KEY-----")
    values = asyncio.run(RegexDetector().detect(text, policy))
    categories = {item.category for item in values}
    assert {Category.EMAIL, Category.PHONE, Category.SSN, Category.IP_ADDRESS, Category.URL,
            Category.CREDIT_CARD, Category.API_KEY, Category.SECRET, Category.PASSWORD} <= categories
    assert luhn_valid("4111 1111 1111 1111")
    assert not luhn_valid("4111 1111 1111 1112")


def test_ipv4_accepts_sentence_punctuation_but_rejects_fifth_component(policy) -> None:
    text = "Internal 10.0.20.30. Invalid 1.2.3.4.5 remains."
    values = asyncio.run(RegexDetector().detect(text, policy))
    addresses = [item.text for item in values if item.category == Category.IP_ADDRESS]
    assert addresses == ["10.0.20.30"]


def test_merge_dedup_overlap_priority_and_invalid_offset() -> None:
    text = "secret@example.com"
    email = finding(text, Category.EMAIL, 0, "regex", 1)
    duplicate = finding(text, Category.EMAIL, 0, "ollama", .8)
    contained = finding("secret", Category.PERSON_NAME, 0)
    invalid = finding("missing", Category.OTHER, 0)
    result = merge_findings(text, [email, duplicate, contained, invalid])
    assert len(result.findings) == 1
    assert result.findings[0].sources == {"regex", "ollama"}
    assert result.findings[0].confidence == 1
    assert result.ambiguous and "text" not in result.ambiguous[0]


def test_placeholder_consistency_and_reverse_replacement(policy) -> None:
    text = "John Smith emailed j@example.com. John Smith replied."
    findings = [finding("John Smith", Category.PERSON_NAME, 0),
                finding("j@example.com", Category.EMAIL, 19),
                finding("John Smith", Category.PERSON_NAME, 34)]
    result = sanitize_text(text, findings, policy)
    assert result.text == "[PERSON_NAME_1] emailed [EMAIL_1]. [PERSON_NAME_1] replied."
    assert all("John Smith" not in item.model_dump_json() for item in result.replacements)


def _provider(response_content: str | None = None, timeout: bool = False) -> OllamaDetectionProvider:
    async def handler(request: httpx.Request) -> httpx.Response:
        if timeout:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"message": {"content": response_content}})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    endpoint = validate_ollama_endpoint("http://100.64.0.1:11434", "private-network",
                                       allow_insecure_remote=True)
    return OllamaDetectionProvider(endpoint, "test", retries=0, client=client)


def test_ollama_validates_repeated_and_missing_spans(policy) -> None:
    content = json.dumps({"findings": [
        {"text": "Jane", "category": "PERSON_NAME", "confidence": .9, "reason": "name"},
        {"text": "Jane", "category": "PERSON_NAME", "confidence": .8, "reason": "duplicate"},
        {"text": "Absent", "category": "LOCATION", "confidence": .7, "reason": "not present"}]})
    values = asyncio.run(_provider(content).detect("Jane met Jane.", policy))
    assert [(item.start, item.end) for item in values] == [(0, 4), (9, 13)]


@pytest.mark.parametrize("content", ["not json", "", json.dumps({"findings": [
    {"text": "x", "category": "INVALID", "confidence": 1, "reason": "x"}]})])
def test_ollama_rejects_invalid_responses(policy, content: str) -> None:
    with pytest.raises(ProviderError):
        asyncio.run(_provider(content).detect("x", policy))


def test_ollama_timeout(policy) -> None:
    with pytest.raises(ProviderError, match="unavailable"):
        asyncio.run(_provider(timeout=True).detect("x", policy))


def test_ollama_retries_truncated_json_then_accepts_valid_output(policy) -> None:
    responses = iter([
        '{"findings":[{"text":"Jane',
        json.dumps({"findings": [{"text": "Jane", "category": "PERSON_NAME",
                                  "confidence": .9, "reason": "name"}]})
    ])
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": {"content": next(responses)}})

    endpoint = validate_ollama_endpoint("http://100.64.0.1:11434", "private-network",
                                       allow_insecure_remote=True)
    provider = OllamaDetectionProvider(endpoint, "test", retries=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    findings = asyncio.run(provider.detect("Jane", policy))
    assert calls == 2
    assert len(findings) == 1 and findings[0].text == "Jane"


def test_verification_success_and_failure(policy) -> None:
    verifier = VerificationService(RegexDetector())
    good = asyncio.run(verifier.verify("[EMAIL_1]", {"a@b.com"}, policy, False))
    bad = asyncio.run(verifier.verify("a@b.com", {"a@b.com"}, policy, False))
    assert good.passed
    assert not bad.passed
