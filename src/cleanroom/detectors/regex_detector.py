import ipaddress
import re

from cleanroom.models.finding import Category, Finding
from cleanroom.models.policy import SanitizationPolicy


def luhn_valid(value: str) -> bool:
    digits = [int(char) for char in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class RegexDetector:
    patterns: tuple[tuple[Category, re.Pattern[str], str], ...] = (
        (Category.EMAIL, re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w-])"), "email-address pattern"),
        (Category.PHONE, re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}(?!\d)"), "US phone pattern"),
        (Category.SSN, re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)"), "US SSN pattern"),
        (Category.URL, re.compile(r"https?://[^\s<>\]\[\"']+"), "URL pattern"),
        (Category.CREDIT_CARD, re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), "Luhn-valid card number"),
        (Category.API_KEY, re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b"), "common API key pattern"),
        (Category.SECRET, re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.I), "bearer token"),
        (Category.SECRET, re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "JWT token"),
        (Category.SECRET, re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private-key header"),
    )
    assignments: tuple[tuple[Category, re.Pattern[str], str], ...] = (
        (Category.PASSWORD, re.compile(
            r"(?im)\bpassword\s*[:=]\s*(?:\"(?P<dq>[^\"\r\n]+)\"|'(?P<sq>[^'\r\n]+)'|(?P<raw>[^\s,;]+))"),
         "password assignment value"),
        (Category.API_KEY, re.compile(
            r"(?im)\b(?:api[_ -]?key|api\s+token|token)\s*[:=]\s*(?:\"(?P<dq>[^\"\r\n]+)\"|'(?P<sq>[^'\r\n]+)'|(?P<raw>[^\s,;]+))"),
         "API token assignment value"),
        (Category.SECRET, re.compile(
            r"(?im)\bsecret\s*[:=]\s*(?:\"(?P<dq>[^\"\r\n]+)\"|'(?P<sq>[^'\r\n]+)'|(?P<raw>[^\s,;]+))"),
         "secret assignment value"),
    )
    # Accept normal sentence punctuation after an address without accepting a
    # fifth dotted component such as 1.2.3.4.5.
    ipv4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?=$|[^\d.]|\.(?=\s|$))")

    async def detect(self, text: str, policy: SanitizationPolicy) -> list[Finding]:
        findings: list[Finding] = []
        for category, pattern, reason in self.patterns:
            for match in pattern.finditer(text):
                if category == Category.CREDIT_CARD and not luhn_valid(match.group()):
                    continue
                value, end = match.group(), match.end()
                if category == Category.URL:
                    value = value.rstrip(".,;:!?)]}")
                    end = match.start() + len(value)
                findings.append(self._finding(value, category, match.start(), end, reason))
        for match in self.ipv4.finditer(text):
            try:
                ipaddress.IPv4Address(match.group())
            except ipaddress.AddressValueError:
                continue
            findings.append(self._finding(match.group(), Category.IP_ADDRESS, match.start(), match.end(), "valid IPv4 address"))
        for category, pattern, reason in self.assignments:
            for match in pattern.finditer(text):
                group = next(name for name in ("dq", "sq", "raw") if match.group(name) is not None)
                findings.append(self._finding(match.group(group), category,
                                               match.start(group), match.end(group), reason))
        return findings

    @staticmethod
    def _finding(text: str, category: Category, start: int, end: int, reason: str) -> Finding:
        return Finding(text=text, category=category, confidence=1, source="regex", start=start,
                       end=end, reason=f"Matched {reason}")
