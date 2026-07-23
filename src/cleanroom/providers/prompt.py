from cleanroom.models.finding import Category
from cleanroom.models.policy import SanitizationPolicy

PROMPT_VERSION = "detection-v1"
VERIFICATION_PROMPT_VERSION = "verification-v1"
SYSTEM_PROMPT = """You are a sensitive-data detection component.

Your task is to identify exact text spans that may reveal private, confidential,
identifying, security-sensitive, or organization-sensitive information.
Return only valid JSON matching the provided schema.
Copy finding text exactly from the supplied source.
Do not rewrite the source. Do not invent information.
Do not return findings that are not present verbatim in the source.
Prefer false positives over missing highly sensitive information, but assign lower
confidence to uncertain findings. Do not include commentary."""


def user_prompt(text: str, policy: SanitizationPolicy) -> str:
    actions = ", ".join(f"{key.value}={value.value}" for key, value in policy.actions.items())
    categories = ", ".join(item.value for item in Category)
    hints = "; ".join(policy.ollama_prompt_hints) or "none"
    return (f"Prompt version: {PROMPT_VERSION}\nSupported categories: {categories}\n"
            f"Policy: {policy.name} v{policy.version}; {actions}\n"
            f"Policy hints: {hints}\n"
            "Find exact sensitive spans in SOURCE below.\n<SOURCE>\n" + text + "\n</SOURCE>")


VERIFICATION_SYSTEM_PROMPT = """You are verifying an already sanitized document.

Cleanroom placeholders are safe generated tokens.
Do not report Cleanroom placeholders, placeholder category names, redaction labels,
or bracketed replacement tokens. Report only real sensitive information remaining
outside placeholders. Every finding must exist verbatim in the supplied sanitized
text. Return only valid JSON matching the schema. Do not rewrite or comment."""


def verification_user_prompt(text: str, policy: SanitizationPolicy) -> str:
    examples: list[str] = []
    for category, action in policy.actions.items():
        label = policy.placeholders[category]
        if action.value == "replace":
            examples.append(f"[{label}_1]")
        elif action.value == "redact":
            examples.append(f"[REDACTED_{label}]")
    return (f"Prompt version: {VERIFICATION_PROMPT_VERSION}\n"
            f"Safe placeholder examples: {', '.join(sorted(set(examples)))}\n"
            "Inspect SANITIZED_SOURCE only for real remaining sensitive values.\n"
            "<SANITIZED_SOURCE>\n" + text + "\n</SANITIZED_SOURCE>")


RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"text": {"type": "string", "minLength": 1},
                       "category": {"type": "string", "enum": [c.value for c in Category]},
                       "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                       "reason": {"type": "string", "minLength": 1}},
        "required": ["text", "category", "confidence", "reason"]}}},
    "required": ["findings"], "additionalProperties": False,
}
