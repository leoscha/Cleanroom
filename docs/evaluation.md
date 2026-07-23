# Evaluation

The bundled dataset is synthetic. Run:

```bash
cleanroom evaluate --detector regex
cleanroom evaluate --detector combined
cleanroom evaluate --detector ollama --model gemma3:4b
```

Expected spans declare category, exact offsets, and whether a finding is required.
Cleanroom reports precision, recall, F1, required recall, exact-span/overlap/category
accuracy, false positives/negatives, invalid findings, latency percentiles,
verification pass rate, and quarantine rate. Results go to ignored
`evaluation-results/`; case reports use source hashes and counts.

The evaluator also generates a synthetic text-based PDF in a controlled temporary
directory. PDF metrics remain separate: exact mapping rate, successful redaction
rate, verification pass rate, quarantine and mapping-failure rates, metadata
sanitization success, and average processing duration per page. The temporary PDF is
deleted after evaluation, and case results contain hashes and counts rather than
finding plaintext.

`CLEANROOM_EVAL_MIN_REQUIRED_RECALL` and `CLEANROOM_EVAL_MIN_PRECISION` control
the nonzero threshold exit. Ollama modes send only the synthetic cases to the
configured private endpoint.
