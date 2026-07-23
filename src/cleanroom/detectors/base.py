from typing import Protocol

from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy


class Detector(Protocol):
    async def detect(self, text: str, policy: SanitizationPolicy) -> list[Finding]: ...
