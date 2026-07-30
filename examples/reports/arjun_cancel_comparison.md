# Pipeline comparison: arjun_cancel

Command:

```bash
voice-eval compare \
  --scenario arjun_cancel \
  --adapters cascade degraded
```

| Adapter | Overall | Avg latency (ms) | P95 latency (ms) | Tool recall |
|---|---:|---:|---:|---:|
| cascade | 100.00% | 640.0 | 640.0 | 100.00% |
| degraded | 55.27% | 1450.0 | 1450.0 | 33.33% |

The `degraded` adapter is an intentionally failing fixture. It demonstrates
how the scorecard exposes missed tools, missing required content, excessive
questions and sentences, and latency-budget violations. It does not represent
any real model or provider.
