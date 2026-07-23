# Evaluation

The bundled evaluation cases contain synthetic data only.

```bash
cleanroom evaluate --detector regex
cleanroom evaluate --detector combined
cleanroom evaluate --detector ollama --model gemma3:4b
```

Expected output fields:

```text
Precision: 0.714
Recall: 0.833
F1: 0.769
Required recall: 1.000
Invalid model responses/findings: 0
Evaluation thresholds passed.
```

This excerpt is the published v0.2.0 `gemma3:4b` combined baseline. Exact results vary
by detector, model build, hardware, and dataset revision. The
command writes privacy-safe aggregate and per-case metadata under
`evaluation-results/`.
