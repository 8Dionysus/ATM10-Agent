# ATM10-Agent local stats port

This directory exposes statistical questions whose meaning belongs to the
local companion and its operator-facing service evidence. It uses the shared
`aoa-stats` grammar without moving service SLA or product authority into the
central organ.

## Measurement

| Measurement | Question | Reference value |
| --- | --- | --- |
| `ATM10-Agent/cross-service-sla-pass-ratio` | What fraction of the expected service lanes passed their own SLA in one completed cross-service benchmark suite? | `4 / 4` for the public `baseline_first` fixture run at source revision `5044451c1c0690acaa2d73dd0e7f6a41f7c157d5` |

The population is an exact profile-specific census. `baseline_first` expects
voice ASR, voice TTS, retrieval, and file KAG; `combo_a` expects voice ASR,
voice TTS, retrieval, and Neo4j KAG. A missing or extra lane, failed suite,
unsupported profile, malformed child summary, or inconsistent overall status
makes the statistic unknown. Four complete breaches remain an observed zero.

## Evidence posture

`scripts/cross_service_benchmark_suite.py` produces live-capable suite
artifacts, and `src/agent_core/service_sla.py` derives the ratio without
combining heterogeneous child metrics. The committed packet is a public
reference observation over sanitized fixtures; live run artifacts remain
outside Git and are not copied into the packet.

## Authority

The ratio reports only how many expected lanes carried `status=ok` and
`sla_status=pass` in one internally consistent completed suite. It does not
certify operator readiness, gameplay success, current host health, product
support, causal service quality, or an `aoa-evals` verdict.

## Surfaces

- `port.manifest.json` declares the owner-local question and measurement.
- `packets/cross-service-sla-pass-ratio.reference.json` records the public
  fixture observation.
- `scripts/cross_service_benchmark_suite.py` remains the live evidence owner.
- `aoa-stats` owns shared validation and cross-owner composition.
