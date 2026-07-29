#!/usr/bin/env python3
"""Generate Cleanroom's deterministic synthetic regression corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _finding(text: str, category: str, value: str) -> dict[str, object]:
    start = text.index(value)
    return {
        "category": category,
        "text": value,
        "start": start,
        "end": start + len(value),
        "required": True,
    }


def _case(name: str, text: str, values: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "name": f"{name}.txt",
        "text": text,
        "findings": [_finding(text, category, value) for category, value in values],
    }


def _luhn_number(prefix: str, length: int) -> str:
    body = prefix + "0" * (length - len(prefix) - 1)
    for digit in range(10):
        candidate = body + str(digit)
        total = 0
        for index, value in enumerate(reversed([int(char) for char in candidate])):
            if index % 2:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
        if total % 10 == 0:
            return candidate
    raise AssertionError("unable to generate Luhn value")


def build_corpus() -> list[dict[str, object]]:
    """Return 120 synthetic positive, combined, boundary, and negative cases."""
    cases: list[dict[str, object]] = []

    for index in range(10):
        value = f"person{index}+release@example{index}.test"
        text = f"Synthetic contact email is {value} for case {index}."
        cases.append(_case(f"email-{index:02}", text, [("EMAIL", value)]))

    phone_values = [
        "312-555-0100", "312.555.0101", "312 555 0102", "(312) 555-0103",
        "+1 312 555 0104", "+1-312-555-0105", "773-555-0106",
        "847.555.0107", "630 555 0108", "(708) 555-0109",
    ]
    for index, value in enumerate(phone_values):
        text = f"Synthetic callback: {value}."
        cases.append(_case(f"phone-{index:02}", text, [("PHONE", value)]))

    for index in range(10):
        value = f"123-45-{6700 + index:04}"
        text = f"Synthetic SSN field = {value}."
        cases.append(_case(f"ssn-{index:02}", text, [("SSN", value)]))

    for index in range(10):
        value = f"10.{index}.20.{30 + index}"
        text = f"Synthetic internal address: {value}."
        cases.append(_case(f"ipv4-{index:02}", text, [("IP_ADDRESS", value)]))

    for index in range(10):
        value = f"https://synthetic{index}.example.test/private/path-{index}?case={index}"
        text = f"Synthetic URL {value}"
        cases.append(_case(f"url-{index:02}", text, [("URL", value)]))

    for index in range(10):
        digits = _luhn_number(f"4{index + 1}", 16)
        value = " ".join(digits[position:position + 4] for position in range(0, 16, 4))
        text = f"Synthetic test card: {value}."
        cases.append(_case(f"card-{index:02}", text, [("CREDIT_CARD", value)]))

    api_values = [
        *(f"sk-synthetickey{index:04}abcd" for index in range(4)),
        *(f"AKIA{index:016d}" for index in range(3)),
        *(f"ghp_syntheticreleasekey{index:03}" for index in range(3)),
    ]
    for index, value in enumerate(api_values):
        text = f"Synthetic API credential {value}"
        cases.append(_case(f"api-key-{index:02}", text, [("API_KEY", value)]))

    for index in range(10):
        value = f"SyntheticOnly{index}!"
        label = ("password", "Password", "PASSWORD")[index % 3]
        separator = (" = ", ": ")[index % 2]
        quoted = f'"{value}"' if index % 2 else value
        text = f"{label}{separator}{quoted}"
        cases.append(_case(f"password-{index:02}", text, [("PASSWORD", value)]))

    secret_records = [
        ("Bearer synthetic-token-000", "Bearer synthetic-token-000"),
        ("Bearer synthetic.token.001", "Bearer synthetic.token.001"),
        ("Bearer synthetic_token_002", "Bearer synthetic_token_002"),
        ("eyJsynthetic0.eyJpayload0.signature0", "eyJsynthetic0.eyJpayload0.signature0"),
        ("eyJsynthetic1.eyJpayload1.signature1", "eyJsynthetic1.eyJpayload1.signature1"),
        ("eyJsynthetic2.eyJpayload2.signature2", "eyJsynthetic2.eyJpayload2.signature2"),
        ("Synthetic fixture\n-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----"),
        ("Synthetic fixture\n-----BEGIN OPENSSH PRIVATE KEY-----", "-----BEGIN OPENSSH PRIVATE KEY-----"),
        ("secret = SyntheticSecret8!", "SyntheticSecret8!"),
        ("SECRET: 'SyntheticSecret9!'", "SyntheticSecret9!"),
    ]
    for index, (text, value) in enumerate(secret_records):
        cases.append(_case(f"secret-{index:02}", text, [("SECRET", value)]))

    for index in range(10):
        email = f"combined{index}@example.test"
        password = f"CombinedOnly{index}!"
        text = f"Email={email}\npassword={password}"
        cases.append(_case(f"combined-{index:02}", text, [
            ("EMAIL", email), ("PASSWORD", password),
        ]))

    negatives = [
        "Generated placeholders [EMAIL_1] and [REDACTED_SSN] are safe.",
        "An invalid network-like value 256.300.1.1 must not match.",
        "An invalid SSN-like value 000-00-0000 must not match.",
        "A non-Luhn number 4111111111111112 must not match.",
        "An incomplete address user@example has no valid email suffix.",
        "An unseparated phone-like value 3125550199 is unsupported.",
        "The password policy requires twelve characters.",
        "The secret ingredient is synthetic cinnamon.",
        "The token budget is one thousand units.",
        "A private key concept is not a private-key header.",
        "Unicode fullwidth digits １２３４５ are ordinary text here.",
        "Version 1.2.3.4.5 contains too many dotted components.",
        "Release label EMAIL_1 is not itself an email.",
        "Call extension 555-0100 without an area code.",
        "Card suffix 4242 is safe on its own.",
        "The authentication scheme name is Bearer.",
        "A quoted word 'password' is documentation, not an assignment.",
        "A project may use sk- as a harmless textual prefix.",
        "Three dotted words alpha.beta.gamma are not a JWT.",
        "Clean synthetic prose with no identifiers at all.",
    ]
    for index, text in enumerate(negatives):
        cases.append(_case(f"negative-{index:02}", text, []))

    assert len(cases) == 120
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
        default=Path("src/cleanroom/resources/evaluation/cases/regression-corpus.jsonl"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(case, sort_keys=True) for case in build_corpus()) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(f"Wrote {len(build_corpus())} synthetic cases to {args.output}")


if __name__ == "__main__":
    main()
