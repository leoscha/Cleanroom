# Synthetic evaluation dataset

All values are fabricated. Canonical fixtures are packaged under
`src/cleanroom/resources/evaluation/` so `cleanroom evaluate` runs the same suite from
a source checkout or an installed wheel. Its `cases/` directory contains focused text
fixtures plus a reproducible 120-case regression corpus. `expected/` contains exact
spans marked required or optional for the focused fixtures; JSONL corpus records carry
their own exact synthetic annotations. Regenerate the corpus with:

```bash
python scripts/generate_evaluation_corpus.py
```

CI verifies that the checked-in corpus matches the generator before enforcing exact
deterministic precision, required recall, span, verification, and PDF gates. Three PDF
compatibility cases are generated in a controlled temporary directory from synthetic
content and then removed. Text and PDF metrics are reported separately. Results are
written outside this directory to ignored `evaluation-results/`.
