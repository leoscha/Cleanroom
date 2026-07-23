from typing import Protocol

from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy


class ProviderError(RuntimeError):
    pass


class DetectionProvider(Protocol):
    async def detect(self, text: str, policy: SanitizationPolicy) -> list[Finding]: ...

    async def verify(self, text: str, policy: SanitizationPolicy) -> list[Finding]: ...

    async def health(self) -> dict[str, object]: ...
