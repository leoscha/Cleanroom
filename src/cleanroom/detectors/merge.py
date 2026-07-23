from dataclasses import dataclass

from cleanroom.models.finding import Category, Finding

RISK = {Category.SECRET: 100, Category.PASSWORD: 100, Category.API_KEY: 100,
        Category.SSN: 95, Category.CREDIT_CARD: 95, Category.BANK_ACCOUNT: 95,
        Category.PASSPORT: 90, Category.DRIVERS_LICENSE: 90}


@dataclass
class MergeResult:
    findings: list[Finding]
    ambiguous: list[dict[str, str | int | float]]


def merge_findings(text: str, findings: list[Finding]) -> MergeResult:
    invalid = [item for item in findings if not item.matches(text)]
    valid = [item for item in findings if item.matches(text)]
    unique: dict[tuple[int, int, Category], Finding] = {}
    for item in valid:
        key = (item.start, item.end, item.category)
        if key in unique:
            prior = unique[key]
            prior.confidence = max(prior.confidence, item.confidence)
            prior.sources.update(item.sources)
        else:
            unique[key] = item.model_copy(deep=True)
    ranked = sorted(unique.values(), key=lambda f: (
        -RISK.get(f.category, 0), "regex" not in f.sources, -(f.end - f.start),
        f.start, -f.confidence, f.category.value))
    accepted: list[Finding] = []
    ambiguous: list[dict[str, str | int | float]] = [
        {"category": item.category.value, "start": item.start, "end": item.end,
         "confidence": item.confidence, "issue": "offset_mismatch"}
        for item in invalid
    ]
    for candidate in ranked:
        conflict = next((item for item in accepted if candidate.start < item.end and item.start < candidate.end), None)
        if conflict:
            ambiguous.append({"category": candidate.category.value, "start": candidate.start,
                              "end": candidate.end, "confidence": candidate.confidence,
                              "conflicts_with": conflict.category.value})
        else:
            accepted.append(candidate)
    return MergeResult(sorted(accepted, key=lambda f: f.start), ambiguous)
