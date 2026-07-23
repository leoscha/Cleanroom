from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.providers.base import DetectionProvider


class OllamaDetector:
    def __init__(self, provider: DetectionProvider) -> None:
        self.provider = provider

    async def detect(self, text: str, policy: SanitizationPolicy) -> list[Finding]:
        return await self.provider.detect(text, policy)
