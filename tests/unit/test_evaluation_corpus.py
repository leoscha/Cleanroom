from scripts.generate_evaluation_corpus import build_corpus


def test_regression_corpus_has_120_valid_synthetic_cases() -> None:
    corpus = build_corpus()
    assert len(corpus) == 120
    assert len({case["name"] for case in corpus}) == 120
    for case in corpus:
        text = case["text"]
        assert isinstance(text, str)
        findings = case["findings"]
        assert isinstance(findings, list)
        for finding in findings:
            assert isinstance(finding, dict)
            assert text[finding["start"]:finding["end"]] == finding["text"]
