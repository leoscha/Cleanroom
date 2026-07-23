import asyncio
import json

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cleanroom.models.finding import Category, Finding
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.providers.base import ProviderError
from cleanroom.providers.prompt import (
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    VERIFICATION_SYSTEM_PROMPT,
    user_prompt,
    verification_user_prompt,
)


class RawFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    category: Category
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class RawResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[RawFinding]


class OllamaDetectionProvider:
    def __init__(self, base_url: str, model: str, timeout: float = 180, retries: int = 2,
                 client: httpx.AsyncClient | None = None) -> None:
        self.base_url, self.model, self.retries = base_url.rstrip("/"), model, retries
        self.client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def health(self) -> dict[str, object]:
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            names = [item.get("name") for item in response.json().get("models", [])]
            return {"reachable": True, "model_installed": self.model in names, "models": names}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return {"reachable": False, "model_installed": False, "error": type(exc).__name__}

    async def detect(self, text: str, policy: SanitizationPolicy) -> list[Finding]:
        return await self._request(text, SYSTEM_PROMPT, user_prompt(text, policy))

    async def verify(self, text: str, policy: SanitizationPolicy) -> list[Finding]:
        return await self._request(
            text, VERIFICATION_SYSTEM_PROMPT, verification_user_prompt(text, policy)
        )

    async def _request(self, source: str, system: str, prompt: str) -> list[Finding]:
        payload = {"model": self.model, "stream": False, "format": RESPONSE_SCHEMA,
                   "options": {"temperature": 0},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": prompt}]}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                content = response.json().get("message", {}).get("content")
                if not isinstance(content, str) or not content.strip():
                    raise ProviderError("model returned an empty response")
                raw = RawResponse.model_validate(json.loads(content))
                return self._locate(source, raw)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last = exc
                if attempt < self.retries:
                    await asyncio.sleep(0.1 * (2**attempt))
            except httpx.HTTPStatusError as exc:
                raise ProviderError(
                    f"Ollama request failed with HTTP {exc.response.status_code}"
                ) from exc
            except (json.JSONDecodeError, ValidationError, ValueError, KeyError,
                    ProviderError) as exc:
                last = exc
                if attempt < self.retries:
                    await asyncio.sleep(0.1 * (2**attempt))
        if isinstance(last, (httpx.TimeoutException, httpx.NetworkError)):
            raise ProviderError(f"Ollama unavailable ({type(last).__name__})") from last
        raise ProviderError(
            f"Ollama returned invalid structured output after {self.retries + 1} attempt(s)"
        ) from last

    @staticmethod
    def _locate(text: str, raw: RawResponse) -> list[Finding]:
        found: list[Finding] = []
        seen: set[tuple[str, Category]] = set()
        for item in raw.findings:
            key = (item.text, item.category)
            if key in seen:
                continue
            seen.add(key)
            start = 0
            while (position := text.find(item.text, start)) >= 0:
                found.append(Finding(text=item.text, category=item.category,
                    confidence=item.confidence, source="ollama", start=position,
                    end=position + len(item.text), reason=item.reason))
                start = position + len(item.text)
        return found
