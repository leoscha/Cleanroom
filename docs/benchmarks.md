# Benchmarks

These results describe one reproducible local run, not a universal performance or
quality guarantee. Model builds, Ollama versions, hardware, thermals, prompts, policy,
and dataset revisions can materially change the outcome.

## v0.2.0 TXT baseline

Run on 2026-07-22 with combined deterministic and contextual detection.

| Item | Value |
| --- | --- |
| Model | `gemma3:4b` |
| Ollama | 0.31.1, local loopback |
| Hardware | Apple M4, 10-core CPU, 16 GB RAM |
| OS | macOS 26.5.1 arm64 |
| Dataset | 7 synthetic TXT cases, 14,575 characters |
| Warm-up | 1 unmeasured request |
| Execution | Sequential, one workspace |

### Performance

| Metric | Result |
| --- | ---: |
| Average document latency | 4.837 s |
| Median document latency | 3.917 s |
| p95 document latency | 8.670 s |
| End-to-end wall time | 33.882 s |
| Throughput | 0.207 documents/s |
| Character throughput | 430.2 characters/s |

### Evaluation

| Metric | Result |
| --- | ---: |
| Precision | 0.714 |
| Recall | 0.833 |
| F1 | 0.769 |
| Required-finding recall | 1.000 |
| Exact-span accuracy | 0.833 |
| Invalid model findings | 0 |
| Verification pass rate | 1.000 |

Four findings beyond the exact expected annotations were counted as false positives.
The evaluation set is deliberately small and synthetic; it is a regression baseline,
not evidence that Cleanroom will find all sensitive information in real documents.

Raw results and privacy-safe per-case counts are published under
[`benchmarks/gemma3-4b-local/`](../benchmarks/gemma3-4b-local/). Reproduce them with:

```bash
python scripts/benchmark_text.py \
  --model gemma3:4b \
  --hardware "Describe the benchmark host"
```

