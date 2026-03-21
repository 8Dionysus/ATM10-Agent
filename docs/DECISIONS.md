# DECISIONS

## 2026-02-19

* Phase A smoke uses `DeterministicStubVLM` through the `VLMClient` interface to keep the loop engine-agnostic and avoid getting blocked on a real model.
* The screenshot in the smoke runner is saved as a valid placeholder PNG without external dependencies; real capture will be swapped in later without changing the artifact contract.
* For Phase B, the JSONL doc contract is locked as: `id`, `source`, `title`, `text`, `tags`, `created_at`; a tiny fixture dataset was added for tests.
* In `ftbquests` ingest, the initial iteration supported JSON files only; this decision was later superseded by the SNBT fallback branch (see 2026-02-20).

## 2026-02-20

* For completion of M2, `in-memory retrieval` was chosen as the first step without Docker/Qdrant: it covers `top-k + citations` and preserves the API boundary for later Qdrant integration.
* `scripts/retrieve_demo.py` writes artifacts to `runs/<timestamp>/` (`run.json`, `retrieval_results.json`) for reproducibility and debugging.
* Qdrant integration was added as an optional backend through the REST API (without new Python dependencies): `scripts/ingest_qdrant.py` + `scripts/retrieve_demo.py --backend qdrant`.
* A lightweight fallback for `.snbt` was added to quest normalization: the file is indexed as a document without a full SNBT parser to provide a working retrieval baseline on real ATM10 data.
* Qdrant ingest was made idempotent for the `collection already exists` case (HTTP 409): the pipeline continues with upsert and does not fail.
* To reduce retrieval noise, baseline ingestion excludes `lang/**` and `reward_tables/**` from the index by default; the main index focus is quest chapters/structures rather than localizations and reward tables.
* Phase B baseline was validated end-to-end on local ATM10 + Qdrant (`normalize -> ingest -> retrieve`) with working top-k + citations.
* OpenVINO (`openvino==2025.4.1`) was added for hardware-accelerated inference, and the diagnostic workflow was locked in `docs/RUNBOOK.md` with artifact output in `runs/<timestamp>-openvino/`.
* A two-stage search was adopted to improve retrieval relevance: first-stage candidate retrieval + second-stage rerank; CLI options `--candidate-k` and `--reranker` (`none|qwen3`) were added, with default baseline `none`.
* Specialized reranking is based on the `Qwen3-Reranker` family; the initial rollout target model is `Qwen/Qwen3-Reranker-0.6B` (optional, without forcing heavy dependencies into the baseline).
* EOL policy was locked through `.gitattributes`: source/docs/config use LF, Windows scripts (`*.ps1`, `*.bat`, `*.cmd`) use CRLF for stable diffs and less noise.
* A reproducible benchmark `scripts/eval_retrieval.py` was added for tuning retrieval defaults (Recall@k, MRR@k, hit-rate) with artifacts in `runs/<timestamp>/`; `topk/candidate_k/reranker` are now chosen by metrics instead of ad hoc examples.
* `Qwen3-Reranker` integration was aligned with the official scoring flow (yes/no logits through a CausalLM prompt) to avoid an incorrect `SequenceClassification` mode and produce valid rerank scores.
* `_` splitting was added to first-stage tokenization (while keeping the original token) so queries like `metallurgic infuser` correctly match `metallurgic_infuser`.
* Grid-eval on real ATM10 `chapters/*` (`runs/20260220_m2_calibration_none/`) locked production defaults as `topk=5`, `candidate_k=50`, `reranker=none`; metrics matched for `topk>=3`, while `topk=1` was worse on Recall/hit-rate.
* For `qwen3`, a `torch|openvino` runtime switch and `AUTO|CPU|GPU|NPU` device parameter were added to retrieval/eval CLI, allowing rerank acceleration on Intel GPU/NPU through `torch.compile(..., backend="openvino")` without changing the default baseline `reranker=none`.
* SNBT signal extraction for Phase B was improved: ingestion now captures both quoted and unquoted key values (`id/type/dimension/structure/filename/...`), increasing quest recall in `chapters/*`.
* Field-weighted scoring (`title/text/tags`) + stopword filtering was adopted for first-stage retrieval in `chapters/*`, reducing false matches on service words (`and/the/...`) and lifting the relevant chapter for mod-based queries (for example `ars nouveau`).
* Phase A VLM provider is now switchable (`auto|stub|openai`) via CLI/env: the baseline remains stable through stub fallback, while the real provider plugs into the `VLMClient` interface without changing the artifact contract.
* The core project model stack was locked to `Qwen3` (text/vl/retrieval/voice) with an `OpenVINO-first` policy: use ready-made `OpenVINO/*Qwen3*` repositories where available and self-convert the rest (without falling back to `Qwen2.5*`).
* A single entrypoint for self-converting Qwen3 to OpenVINO was locked as `scripts/export_qwen3_openvino.py` with preset profiles (`qwen3-vl-4b`, `qwen3-asr-0.6b`) and a dry-run-first mode with artifacts in `runs/<timestamp>-qwen3-export/`.
* Based on the actual `--execute` run (2026-02-20), upstream limits were recorded: `qwen3_vl` is not yet natively supported by `optimum-intel`, and `qwen3_asr` does not pass through the current `transformers/optimum` export path. Policy remains: stay on Qwen3, use ready OV repos where available, and keep the self-conversion path until support arrives.
* For `qwen3-vl-4b`, a dedicated custom-export entrypoint `scripts/export_qwen3_custom_openvino.py` was added (through `custom_export_configs + fn_get_submodels`) with `--model-source` support (HF repo id or local path). This path successfully built OpenVINO IR in `models/qwen3-vl-4b-instruct-ov-custom` (`runs/20260220_150028-qwen3-custom-export/`).
* After the successful `qwen3-vl` custom export, local HF caches were cleaned (`models/hf_cache`, `models/hf_raw/qwen3-vl-4b`, and the user-level Hugging Face cache directory) to free disk space, with the explicit understanding that future export/inference scenarios would require re-downloading weights.
* For `qwen3-asr-0.6b`, `scripts/export_qwen3_custom_openvino.py` gained a dedicated execute path through `main_export` (instead of a `not implemented` stub), and export failures now persist `diagnostic` in `run.json`, clearly separating the upstream `qwen3_asr` blocker from general runtime errors.
* For `Qwen3-TTS-12Hz-0.6B-CustomVoice`, a separate scaffold entrypoint `scripts/export_qwen3_tts_openvino.py` was added: dry-run records the plan and probe results (model/tokenizer), while `--execute` intentionally exits with diagnostics until a full custom export path exists.
* To stay resilient to upstream API changes in `optimum`, a compatibility resolver for Qwen VL export classes was added (`Qwen3VLOpenVINOConfig|Qwen2VLOpenVINOConfig|QwenVLOpenVINOConfig` + behavior enum variants), and the TTS scaffold probe now uses lazy import of `transformers.AutoConfig` to produce a diagnosable `run.json` instead of an import-time crash on version mismatch.
* The isolated nightly experiment (`runs/20260220_190319-qwen3-exp-venv-probe/`) showed that even with `optimum/optimum-intel` from `main` in a separate `.venv-exp`, `AutoConfig` still does not recognize `qwen3_asr` / `qwen3_tts`; strategy remains `upstream-first` until architecture support appears.
* A unified probe layer `scripts/probe_qwen3_voice_support.py` was added for voice conversion with machine-readable statuses `supported|blocked_upstream|import_error|runtime_error`; this contract is used by ASR/TTS exporters and persisted in `export_plan.json`.
* A matrix runner `scripts/qwen3_voice_probe_matrix.py` was added for reproducible nightly upstream checks (dry-run/execute, optional `--with-setup` for `.venv-exp`) so different `transformers/optimum` combinations can be compared without hand-editing commands.
* Voice-probe matrix setup profiles were limited to compatible `transformers` variants (`main` and `4.57.6`) without force-installing `optimum/optimum-intel`, avoiding frequent pip resolver conflicts and keeping nightly checks reproducible.
* Unlock-gate behavior was locked for voice exporters: if the probe status is not `supported`, `--execute` ends with `status=blocked` and `error_code=unlock_gate_blocked`; only `unlock_ready=true` allows an actual export attempt.
* For operational Phase C, a native runtime path was added without waiting for OpenVINO-export unlock: `scripts/asr_demo.py` and `scripts/tts_demo.py`, with shared runtime wiring in `src/agent_core/io_voice.py`.
* The practical install path for voice runtime was locked as base deps in `requirements.txt` + separate installation of `qwen-asr==0.0.6`, `qwen-tts==0.1.1 --no-deps`, and extra packages `onnxruntime/einops/torchaudio`; reason: upstream packages pin conflicting `transformers` versions (state as of 2026-02-20).
* For the production Phase C path, long-lived runtime was chosen: `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py`; this removes repeated model loading per request and minimizes steady-state latency for the voice loop.
* Benchmarks (`runs/20260220_211505-voice-latency-bench/`, `runs/20260220_211708-voice-latency-oneshot-bench/`) confirmed that current CPU runtime keeps ASR within sub-second warm latency, but does not bring `Qwen3-TTS` under the in-game SLA of `<=2s`; production game-loop therefore needs a separate fast-TTS fallback path, while `Qwen3-TTS` stays optional HQ mode.
* `scripts/export_qwen3_tts_openvino.py` gained an experimental `--backend notebook_helper`: this path uses `qwen_3_tts_helper` from `openvino_notebooks`, does not depend on `AutoConfig` support for `qwen3_tts*`, and preserves the standard artifact contract (`run.json`, `export_plan.json`, `export_stdout.log`, `export_stderr.log`).
* `scripts/export_qwen3_tts_openvino.py` also gained `--weights-quantization` (`none|int8|int8_asym|int8_sym`) for the `notebook_helper` backend; on the target host, `int8_asym` improved CPU warm-path TTS from about `10.4-11.4s` to about `9.5-9.6s`, while the NPU compile blocker for dynamic-graph components remained unchanged.
* `int4_asym` was added as an experiment to `--weights-quantization` (`int4_asym|int4_sym`): on the current host it pushed CPU warm-path further down to about `8.7-9.5s` (`runs/20260220_222426-qwen3-tts-ov-speed-bench-int4-cpu/`), while GPU warm-path stayed variable and NPU compile for the TTS pipeline remained `0/10` (`runs/20260220_222650-qwen3-tts-npu-compile-diag-int4/`).
* To reduce perceived latency in voice runtime, a streaming contract `POST /tts_stream` (NDJSON events) and client mode `tts-stream` were added; artifacts now capture `first_chunk_latency_sec`, `total_synthesis_sec`, `rtf`, and `streaming_mode` for reproducible latency profiling.
* `Qwen3-TTS` was formally deactivated in the active stack (2026-02-20): the production voice path is now ASR-only (`qwen-asr` at the time of this decision), while TTS experiments are retained only as historical artifacts; `qwen-tts` was removed from the working `.venv`, and `.venv-exp` was deleted as cleanup tail.

## 2026-02-21

* Dependencies were split into runtime/dev: `requirements.txt` now contains runtime packages only, while `requirements-dev.txt` includes runtime + `pytest` for local testing and CI.
* To close the voice SLA gap, a separate native Python TTS runtime was chosen as an independent service/container: Router=`FastAPI`, main engine=`XTTS v2`, fallback engines=`Piper` + `Silero` (for Russian service voice), with operational techniques such as prewarm/queue/chunking/phrase cache.

## 2026-02-22

* The operational path for the custom exporter was locked: `scripts/export_qwen3_custom_openvino.py` must run both as a module (`python -m scripts.export_qwen3_custom_openvino`) and as a script (`python scripts/export_qwen3_custom_openvino.py`); fallback import and `--help` smoke test were added.
* In the working runtime-only environment, probe-first policy remains in force for ASR export: if `support_probe.status=import_error` (for example, missing `transformers`), treat `unlock_gate.ready=false` and avoid false conclusions about native `qwen3_asr` support until a separate export-toolchain run is performed.
* After a dedicated run in `.venv` with `transformers/optimum/optimum-intel` installed, `qwen3_asr` was locked as `blocked_upstream` (artifacts: `runs/20260222_142450-qwen3-voice-probe/`, `runs/20260222_142518-qwen3-custom-export/`): the current unlock-gate is blocked by upstream support, not by missing local packages.
* For a faster NPU ASR path, an additional runtime branch `OpenVINO GenAI + Whisper v3 Turbo` (`scripts/asr_demo_whisper_genai.py`) was adopted without replacing the main `qwen-asr` branch at that time; this reduces dependence on `qwen3_asr` upstream support in `transformers/optimum`.
* Long-lived voice runtime was extended with a switchable ASR backend (`qwen_asr|whisper_genai`) in `scripts/voice_runtime_service.py`; for `whisper_genai`, parameters `--asr-device` and `--asr-task` were added, while preserving the `/asr` and `voice_runtime_client` contract.
* A reproducible benchmark `scripts/benchmark_asr_backends.py` was added to compare operational ASR branches, with artifacts (`summary.json`, `summary.md`, `per_sample_results.jsonl`) in `runs/<timestamp>-asr-backend-bench/`; baseline run `runs/20260222_152347-asr-backend-bench/` showed similar average latency (`qwen_asr` ~1.377s vs `whisper_genai` NPU ~1.364s) on the same local WAV set.
* To reduce cold-start impact in the game loop, a startup warmup request was added to `scripts/voice_runtime_service.py` (`--asr-warmup-request`, optional `--asr-warmup-audio`/`--asr-warmup-language`) together with helper launcher `scripts/start_voice_whisper_npu.ps1` for a low-latency `whisper_genai + NPU + warmup` profile.
* `Qwen3-ASR-0.6B` was moved to archived/recoverable status: active ASR backend in runtime was switched to `whisper_genai`, while `qwen_asr` remains in the codebase behind explicit opt-in flags.
* Guard flags for reversible `qwen_asr` archiving were added without deleting code:
  `scripts/voice_runtime_service.py --allow-archived-qwen-asr`,
  `scripts/asr_demo.py --allow-archived-qwen-asr`,
  `scripts/benchmark_asr_backends.py --include-archived-qwen-asr`.
* Operational policy from this point on: baseline/docs/defaults use only `whisper_genai`; the archived path is kept for point rollback and future restore after upstream unlock.
* For M3.1, a lightweight runnable text-core path on OpenVINO GenAI was added: `scripts/text_core_openvino_demo.py` with artifact contract (`run.json`, `response.json`) and graceful dependency error (`runtime_missing_dependency`) without changing baseline dependencies.
* For M3.1 retrieval, a `baseline|ov_production` profile layer was locked in `src/rag/retrieval_profiles.py`: the OV profile uses `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov` + `reranker_runtime=openvino`, while the baseline stays compatible with the current CI/dev loop.
* For HUD assistance, a dependency-light OCR baseline through the system `tesseract` CLI (`scripts/hud_ocr_baseline.py`) was chosen instead of adding new Python OCR libraries; this preserves reproducibility and does not change `requirements.txt`.
* For the HUD mod-hook baseline, a file-based ingest contract (`scripts/hud_mod_hook_baseline.py`) with machine-readable normalization (`hook_normalized.json`) was chosen; this enables multiple mod-hook integrations without tying the system to a single transport.
* For Graph/KAG, a file-based baseline without infrastructure dependencies was adopted (`src/kag/baseline.py`, `scripts/kag_build_baseline.py`, `scripts/kag_query_demo.py`) with artifact contracts `kag_graph.json` and `kag_query_results.json`.
* Migration of Graph/KAG to Neo4j was confirmed as the target phase; runnable entrypoints `scripts/kag_sync_neo4j.py` and `scripts/kag_query_neo4j.py` were added using the HTTP Cypher path without new Python dependencies.
* The Neo4j path was validated end-to-end on a local container (`runs/20260222_164928-kag-build/` -> `runs/20260222_164942-kag-sync-neo4j/` -> `runs/20260222_165026-kag-query-neo4j/`) with a latency snapshot in `runs/20260222_165100-kag-neo4j-e2e/e2e_latency_snapshot.json`.
* A reproducible benchmark entrypoint `scripts/eval_kag_neo4j.py` was locked for Neo4j KAG, reporting `Recall@k/MRR@k/hit-rate` and latency (`mean/p95/max`) on a fixed JSONL evaluation set.
* For Neo4j KAG, a dual benchmark strategy was adopted: `sample` (stable regression check) + `hard` (relevance gap finding), allowing quality improvements without losing latency control.
* To close the hard-case relevance gap in `query_kag_neo4j`, a lexical fallback over `Doc.title/doc_id` was added (an extra score layer on top of graph signals), lifting `hit-rate@5` to `1.0` in `runs/20260222_170453-kag-neo4j-eval/`; the latency trade-off was recorded separately.
* To reduce tail latency after the relevance uplift, a hybrid query mode was adopted in `query_kag_neo4j`: first fulltext lexical lookup, then limited scan fallback only when fulltext is empty; lexical path runs only when `direct_rows < topk`, and expansion is disabled for single-token queries.
* For single-token hard-case queries in `query_kag_neo4j`, a post-merge lexical alignment bonus on `doc_id/title` (+canonical boost for `:chapters/chapter_`) was added, reducing noisy graph-only matches and lifting the target chapter to the top (`star.first_hit_rank: 4 -> 1` in `runs/20260222_213235-kag-neo4j-eval/`).
* To reduce latency without sacrificing relevance, scan-fallback gating was added to `query_kag_neo4j`: for `fulltext=empty`, fallback `MATCH (d:Doc)` runs for multi-token only when `direct_rows=0`, and for single-token only when direct hits have no lexical alignment by `title/doc_id` (after removing `ftbquests:` namespace from `doc_id` matching). This preserved `star.first_hit_rank=1` and reduced hard `latency_p95_ms` to `83.68` (`runs/20260222_214352-kag-neo4j-eval/`).
* `scripts/eval_kag_neo4j.py` gained optional benchmark warmup (`--warmup-runs`): warmup passes over the same queries are run before measured evaluation and do not enter `eval_results.json`; `run.json` records `params.warmup_runs` and `warmup.executed_calls`.
* A dedicated mini-benchmark `scripts/compare_kag_neo4j_warmup.py` was added to track warmup effect over time: it runs baseline/candidate profiles in repeat series and writes aggregate `p95` deltas to `summary.json` / `summary.md` (example: `runs/20260222_215707-kag-neo4j-warmup-compare/`).
* For automation, a safe baseline `scripts/automation_dry_run.py` was introduced: it accepts a JSON action plan, normalizes it, and writes execution-plan artifacts, but deliberately does not emit keyboard/mouse events into the OS; any real automation remains out-of-scope without explicit approval.
* Documentation structure was unified around a single source of truth: `TODO.md` is execution-only (Now/Next/Blocked + WIP=3), `PLANS.md` is goals/milestones/DoD only, and detailed chronology + run details live in `docs/SESSION_*.md`.
* Archived/recoverable directions were moved into a dedicated register `docs/ARCHIVED_TRACKS.md` so the roadmap does not mix with recovery tracks.
* Counters like `N passed` are no longer duplicated across all status docs: operational truth is recorded in CI and in the latest `docs/SESSION_*.md` snapshot.

## 2026-02-23

* For `automation_dry_run`, an explicit action-plan contract `automation_plan_v1` was locked: validate `schema_version`, normalize `intent` (`goal/priority/tags/constraints`), and persist it in `actions_normalized.json` for upper planning-layer integration.
* The contract now requires unique `action.id` values to avoid ambiguity in downstream execution traces and regression tests.
* Canonical demo scenarios `tests/fixtures/automation_plan_quest_book.json` and `tests/fixtures/automation_plan_inventory_check.json` were added for reproducible demo runs; the runbook was updated with direct launch commands.
* For `M6.3`, a lightweight adapter `scripts/intent_to_automation_plan.py` (`automation_intent_v1` -> `automation_plan_v1`) was added with deterministic template-intent scenarios (`open_quest_book`, `check_inventory_tool`) and artifact contract `runs/<timestamp>-intent-to-automation-plan/{run.json,automation_plan.json}`.
* For `M6.4`, a unified smoke entrypoint `scripts/automation_intent_chain_smoke.py` was added to orchestrate the dry-run chain `intent -> automation_plan_v1 -> automation_dry_run`, writing chain artifacts (`run.json`, `chain_summary.json`, `automation_plan.json`) with links to child runs.
* For `M6.5`, CI smoke was extended with two lightweight automation scenarios on fixed fixtures: `scripts/automation_dry_run.py --plan-json tests/fixtures/automation_plan_quest_book.json` and `scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json`.
* To reduce flaky risk in CI, a fixture-only approach was chosen: new smoke steps require no Docker, audio devices, or model runtime downloads.
* For `KAG quality guardrail`, canonical threshold profiles `sample|hard` were locked together with a dedicated checker `scripts/check_kag_neo4j_guardrail.py` for explicit pass/fail on `recall/mrr/hit-rate/latency_p95`.
* For `M6.6`, a CI contract-check layer was locked for automation smoke: `scripts/check_automation_smoke_contract.py` validates artifact contracts and minimum thresholds; validation steps were added to `.github/workflows/pytest.yml`.
* For `M5.3`, the guardrail path was moved into a dedicated nightly workflow `.github/workflows/kag-neo4j-guardrail-nightly.yml` (`build -> sync -> eval sample/hard -> guardrail-check`) with artifact upload and step summary.
* For `M6.7`, `scripts/check_automation_smoke_contract.py` gained machine-readable output (`--summary-json`); CI smoke job was extended with summary/report step and artifact upload for contract checks.
* For `M5.4`, a lightweight trend-snapshot script `scripts/kag_guardrail_trend_snapshot.py` was added to compare latest `sample/hard` metrics from nightly artifacts and write `trend_snapshot.json` + `summary.md`.
* For `M6.8`, a troubleshooting playbook for automation smoke contract failures was recorded in `docs/RUNBOOK.md` as the canonical operational diagnostic procedure.
* For `M5.5`, the nightly workflow was extended with a trend-report step: `kag_guardrail_trend_snapshot.py` runs in CI and publishes results into `GITHUB_STEP_SUMMARY` and uploaded artifacts (`runs/nightly-kag-trend`).
* For `M6.9`, the CI smoke summary now includes a direct quick-link to runbook section `M6.8` to reduce time-to-diagnosis on contract failures.
* For `M5.6`, the trend snapshot was extended with rolling-baseline comparison (`latest` vs mean of previous N runs), with baseline deltas exposed in `trend_snapshot.json`, `summary.md`, and nightly step summary.
* For `M6.10`, the quick-link to runbook troubleshooting (`M6.8`) was duplicated in the nightly guardrail summary so CI/nightly reports share the same diagnostic path.
* For `M5.7`, `kag_guardrail_trend_snapshot` gained a regression-status layer for rolling baseline (`mrr` and `latency_p95`: `improved|stable|regressed|insufficient_history`) plus aggregate flag `has_any_regression`.
* For doc hygiene at session close, `README.md` and `MANIFEST.md` were moved to a lightweight snapshot format with links to `TODO/PLANS/RUNBOOK/SESSION`, eliminating duplication of long status blocks.
* A single one-screen weekly retrospective template was locked in `docs/SESSION_WEEKLY_TEMPLATE.md`; `docs/SOURCE_OF_TRUTH.md` was updated with the template’s explicit role.

## 2026-02-24

* In `scripts/voice_runtime_service.py`, the `out_wav_path` contract was secured: the service accepts only a filename and always writes TTS output under `runs/<timestamp>-voice-service/tts_outputs`; absolute and nested paths from HTTP payload are forbidden.
* `scripts/voice_runtime_client.py` was updated for compatibility with that contract: it now sends only a safe basename in `out_wav_path`, never an absolute local path.
* Internal error handling in `voice_runtime_service` was sanitized: traceback is no longer returned to the client in `/tts` and `/tts_stream`; full traceback is written only to local artifact `service_errors.jsonl`.
* `scripts/retrieve_demo.py` now always writes `run.json`, including backend failure paths (`status=error`, `error_code=retrieval_backend_error`), so failed launches still leave diagnostic artifacts.
* `scripts/export_qwen3_tts_openvino.py` was normalized to a dual-run contract (module + direct script execution through fallback import); a regression test for `python scripts/export_qwen3_tts_openvino.py --help` was added.
* `scripts/discover_instance.py` was unified around safe run-dir creation: a suffix loop (`_01`, `_02`, ...) is used on timestamp collisions to eliminate flakes from parallel/repeated launches in the same second.
* Supply-chain hardening for Silero was locked in `scripts/tts_runtime_service.py`: remote `torch.hub` source is blocked by default and allowed only through `SILERO_ALLOW_REMOTE_HUB=true` with a pinned revision (`SILERO_REPO_REF` or `owner/repo:ref`); local path remains allowed without opt-in.
* For `M5.8`, calibratable severity thresholds were adopted in `scripts/kag_guardrail_trend_snapshot.py` for rolling-baseline regressions: `mrr` (`warn=0.005`, `critical=0.02`) and `latency_p95_ms` (`warn=2.0`, `critical=8.0`).
* To preserve backward compatibility in guardrail analysis, existing boolean signal `has_any_regression` was retained, while severity was added through separate fields (`mrr_regression_severity`, `latency_p95_regression_severity`, `max_regression_severity`).
* For upper planning-layer integration in `M6.1`, `automation_plan_v1` adopted an optional metadata envelope `planning`; `intent_to_automation_plan` now writes `intent_type`, `intent_schema_version`, `adapter_name/version`, and propagates `intent_id/trace_id` when present in the incoming intent payload.
* For end-to-end automation CI artifact correlation, `scripts/check_automation_smoke_contract.py` was extended so `summary_json.observed` includes optional `trace_id/intent_id` from `planning`; in intent-chain mode, `trace_id` also has a fallback path through `chain_summary/run.json`.
* To accelerate triage in CI summary, the `Automation Smoke Contracts` table in `.github/workflows/pytest.yml` was extended with `trace_id` and `intent_id` columns; canonical automation fixtures received stable correlation ids.
* Strict `--require-trace-id` was enabled for canonical intent-chain smoke in CI through `check_automation_smoke_contract`: missing `trace_id` is now treated as a contract violation and fails the step.
* Strict `--require-intent-id` was also enabled for canonical intent-chain smoke in CI: missing `intent_id` is likewise treated as a contract violation and fails the step.
* To standardize onboarding of new `intent_type`, policy was formalized in `docs/RUNBOOK.md` (`M6.19`): required elements are fixture, smoke run, strict contract-check (`--require-trace-id`, `--require-intent-id`), summary/artifact wiring, and at least one e2e regression test.
* For `G3`, machine-readable summary coverage was extended to non-automation smoke in the `pytest` workflow through `scripts/collect_smoke_run_summary.py` (`phase_a_smoke|retrieve_demo|eval_retrieval`) and uploaded into the shared smoke-summaries artifact.
* For `G2`, policy around `critical` trend severity was formalized in `scripts/kag_guardrail_trend_snapshot.py`: baseline mode is `critical_policy=signal_only` (nightly does not fail on trend severity), with an explicit opt-in `critical_policy=fail_nightly` for stricter guardrails.
* Based on the local warmup=1 history of `kag-neo4j-eval`, latency severity thresholds in `kag_guardrail_trend_snapshot` were recalibrated from `warn 2.0 / critical 8.0` to `warn 5.0 / critical 15.0` because rolling-baseline latency noise floor reached about `13.9 ms` without quality regression in MRR.
* The strategic production baseline was locked as `Combo A`: unified local backend (`FastAPI gateway + workers + Qdrant + Neo4j + runs artifacts`) and frontend path `Streamlit` operator panel with CLI fallback.
* Model/runtime policy was refined as pragmatic hybrid: `Qwen3` remains the core for text/retrieval, while active ASR path is `Whisper GenAI`; drift toward `Qwen2.5*` in the core stack is not allowed.
* Planning (`PLANS/TODO`) was decoupled from the stability of any single audit file: the current strategy is recorded directly in source-of-truth documents without hard references to movable artifacts.

## 2026-02-27

* For `M7.0`, a contract-first local gateway path without new dependencies was locked: `scripts/gateway_v1_local.py` accepts `gateway_request_v1` and always writes `request.json/run.json/response.json` under the `gateway_response_v1` contract.
* Gateway v1 operation set was fixed as `health|retrieval_query|kag_query|automation_dry_run`; `kag_query` defaults to the `file` backend and keeps `neo4j` as an optional backend so the smoke path remains stable without external services.
* Two lightweight CI smoke scenarios were added through `scripts/gateway_v1_smoke.py` (`core`, `automation`) with machine-readable summary (`gateway_smoke_summary.json`) and fail-fast on any `status=error`.
* For `M7.1`, canonical HTTP transport was locked as `POST /v1/gateway`, implemented as a thin wrapper over `run_gateway_request`, avoiding drift between CLI and HTTP body contracts (`gateway_request_v1` / `gateway_response_v1`).
* `gateway_v1_http_service` now has explicit HTTP status mapping: `ok -> 200`, `invalid_request -> 400`, `operation_failed|gateway_dispatch_failed -> 500`, while body always remains `gateway_response_v1`.
* To validate the transport path, a dedicated runnable smoke `scripts/gateway_v1_http_smoke.py` (`core`, `automation`) was added with machine-readable summary (`gateway_http_smoke_summary.json`) and CI fail-fast policy.
* For `M7.2`, hardening profile `Balanced` was adopted for `POST /v1/gateway`: `max_request_body_bytes=262144`, `max_json_depth=8`, `max_string_length=8192`, `max_array_items=256`, `max_object_keys=256`, `operation_timeout_sec=15.0`.
* Timeout behavior was locked at the transport level: `operation_timeout` returns a sanitized `gateway_response_v1` and maps to HTTP `504`.
* Internal-error policy was locked so the client receives only a sanitized envelope (`internal_error_sanitized`), while detailed exceptions (`traceback` + request context) are written locally to `runs/.../gateway_http_errors.jsonl`.
* For `M8.0`, Streamlit panel IA v0 was fixed as a dedicated single-source document `docs/STREAMLIT_IA_V0.md`; `M8.1` implementation must follow that document without additional product decisions.
* A regression test `tests/test_streamlit_ia_doc.py` was added to preserve the IA contract (required sections, canonical data sources, gateway dependency on `GET /healthz` + `POST /v1/gateway`).
* For `M8.1`, `streamlit` was added to runtime dependencies (`requirements.txt`) so the panel entrypoint and smoke path are reproducible both locally and in CI.
* The `M8.1` no-crash smoke was implemented through a real subprocess `python -m streamlit run ...` with timeout/terminate policy and machine-readable summary `streamlit_smoke_summary_v1`.
* CI Streamlit smoke uses a strict policy `missing_sources => error` so the panel does not silently mask absent canonical summaries in the runs tree.
* For `M7.post`, a signal-first SLA mode was adopted for the gateway: default policy `signal_only` never fails CI on breach, but always publishes machine-readable `gateway_sla_summary_v1` with metrics and breaches.
* Conservative SLA profile was selected as the initial operating point: `latency_p95<=1500ms`, `error_rate<=0.05`, `timeout_rate<=0.01`.
* Gateway smoke summaries (`local` + `http`) were extended with observability fields (`started/finished`, `duration_ms`, per-request `latency_ms`, `latency_p50/p95/max`, `error_buckets`) without changing existing response body contracts.

## 2026-02-28

* For `M8.post`, `scripts/streamlit_operator_panel.py` adopted an append-only audit trail for safe actions in `runs/.../ui-safe-actions/safe_actions_audit.jsonl` with contract `timestamp_utc/action_key/command/exit_code/status/summary_json/summary_status/error/ok`.
* The `Safe Actions` UI now contains required operator blocks `Last safe action` and `Recent safe actions` (latest 10, newest-first) to accelerate triage without opening external logs.
* To keep the panel robust, tolerant parsing of the audit JSONL was adopted: if the log is absent, show `not available yet`; if a line is broken, add `invalid audit entry`; the UI must not crash.
* For `M8.post`, the `Latest Metrics` tab adopted a file-based historical view without an external DB: history is built from timestamp run directories under canonical `runs/ci-smoke-*` roots.
* Historical view locks operator filters `source/status/limit` (defaults: all, `ok|error`, `10`) and a scan cap of `200` candidate run directories per source to control UI latency.
* Invalid historical run artifacts do not block the panel: contract/parse mismatches are skipped, the operator gets a warning summary, and the UI remains no-crash.

## 2026-03-01

* To close `M8.post`, `scripts/streamlit_operator_panel.py` adopted an explicit compact mobile layout policy with default `compact_breakpoint_px=768` and baseline viewport `390x844` (portrait), implemented as a CSS layer without changing tab IA/guardrails.
* `scripts/streamlit_operator_panel_smoke.py` gained a mobile regression-check contract: `streamlit_smoke_summary_v1` now includes `mobile_layout_contract_ok`, `mobile_layout_policy`, `viewport_baseline`; violating the baseline results in `status=error`, `exit_code=2`.
* To keep CI stable, a contract-first mobile smoke approach (policy + viewport invariants) was chosen instead of screenshot/DOM asserts, avoiding flaky UI dependencies while preserving a machine-readable regression signal.
* For `G1`, `scripts/check_gateway_sla.py --runs-dir` gained a history-friendly mode: the checker now writes timestamped `run.json` and history copy `gateway_sla_summary.json` without changing the base latest-summary contract.
* For `G1`, a new trend layer `scripts/gateway_sla_trend_snapshot.py` was added with contract `gateway_sla_trend_snapshot_v1` (rolling baseline over `error_rate/timeout_rate/latency_p95` + `breach_drift` + `critical_policy signal_only|fail_nightly`).
* In CI smoke (`.github/workflows/pytest.yml`), a signal-first model was adopted for SLA trend: snapshots are always published to artifacts/step summary, while failing on trend severity is enabled only through explicit `critical_policy=fail_nightly`.
* For `G1.1`, a hardening policy layer for gateway HTTP artifacts/errors was adopted without changing the public `gateway_request_v1/gateway_response_v1`: retention `14d`, error-log rotation `1 MB x 5 files`, redaction `gateway_error_redaction_v1`.
* In `scripts/gateway_v1_http_service.py`, startup cleanup is mandatory and limited to gateway scope (`gateway_http_errors*.jsonl`, `*-gateway-v1*` in `runs_dir`) so artifact growth is bounded without touching other subsystems.
* Internal error JSONL contract was extended with metadata fields `redaction` and `retention_policy`; the client HTTP response remains sanitized (`internal_error_sanitized`) with no traceback leakage.
* For `G2`, staged rollout for readiness toward `critical_policy=fail_nightly` was adopted: in the current iteration, only the report layer (`report_only`) is introduced, with no hard fail gate in CI.
* History source for readiness was formalized as nightly cache (`runs/nightly-gateway-sla-history`, `runs/nightly-gateway-sla-trend-history`) so the decision relies on accumulated daily snapshots rather than a one-off local run.
* The readiness baseline was fixed as a conservative bar: `readiness_window=14`, `required_baseline_count=5`, `critical_count=0`, `warn_ratio<=0.20`, `invalid_or_error_count=0`; the hard switch to `fail_nightly` is deferred to a follow-up after enough history is accumulated.
* For `G2.1`, a dedicated governance layer (`gateway_sla_fail_nightly_governance_v1`) was added for formal `go|hold` decisions about switching to `fail_nightly`.
* Promotion rule was fixed as `3` consecutive nightly `readiness_status=ready`; the relevant history slice must also have `invalid_or_mismatched_count=0`.
* Future rollout surface was fixed as `nightly_only`: `pytest.yml` stays `signal_only` until an explicit separate decision.

## 2026-03-02

* In `scripts/gateway_v1_http_service.py`, timeout path was moved to a lifecycle executor (startup/shutdown) instead of per-request `ThreadPoolExecutor(...)`, so `operation_timeout` returns immediately without waiting for a slow task to finish inside request scope.
* In `scripts/phase_a_smoke.py`, a fail-safe artifact contract was locked for strict VLM path: when provider fails (without fallback), `run.json` and `response.json` are always saved before re-raising the exception.
* For `scripts/voice_runtime_service.py`, an inbound payload hardening profile (`max_request_body_bytes/json_depth/string/array/object`) was adopted with explicit mapping `payload_too_large|payload_limit_exceeded -> HTTP 413`; this policy is exposed via `/health` and run artifacts.
* `/tts_stream` in both `scripts/voice_runtime_service.py` and `scripts/tts_runtime_service.py` was moved to true streaming (incremental NDJSON `started -> audio_chunk -> completed` without full pre-buffer), while `/tts` keeps the previous non-streaming contract.
* Lifecycle hooks in `scripts/gateway_v1_http_service.py` and `scripts/tts_runtime_service.py` were migrated from FastAPI `on_event(startup/shutdown)` to lifespan (`asynccontextmanager`) without changing HTTP/CLI contracts. The change is non-breaking and specifically removes deprecation warnings.
* Dependency management adopted a split-profile approach instead of `pyproject extras`: `requirements-voice.txt`, `requirements-llm.txt`, `requirements-export.txt`, and `requirements-audit.txt` were added, while `requirements.txt` remains the base runtime profile.
* A machine-readable dependency audit entrypoint `scripts/dependency_audit.py` was introduced with artifact contract (`dependency_inventory.json`, `dependency_findings.json`, `security_audit.json`, `summary.md`, `run.json`) under `runs/<timestamp>-dependency-audit/`.
* CI uses report-only policy for dependency/security audit: results are published as artifacts and summary signals but do not block the `pytest` pipeline on warn/error findings in this iteration.
* In `scripts/gateway_v1_local.py`, request artifacts were moved to secure-by-default mode: `request.json` is saved only after redaction, and `run.json` gets machine-readable `request_redaction` metadata (`applied`, `fields_redacted`, checklist version).
* For `retrieval_query` with `reranker=qwen3`, an allowlist policy for `payload.reranker_model` (`Qwen/Qwen3-Reranker-0.6B`, `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov`) was introduced, together with an explicit trusted override through `ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL=true`.
* For HTTP control-plane services (`gateway_v1_http_service`, `voice_runtime_service`, `tts_runtime_service`), an opt-in auth token layer was introduced: when `--service-token` / `ATM10_SERVICE_TOKEN` is present, all endpoints require `X-ATM10-Token`; without a token, behavior remains fully backward-compatible.
* `scripts/tts_runtime_service.py` received parity hardening with gateway/voice: inbound payload limits (`payload_too_large|payload_limit_exceeded -> 413`), sanitized internal `500` envelope, and local redacted error log `service_errors.jsonl` in run artifacts.
* For `G2.2`, a progress layer `scripts/check_gateway_sla_fail_nightly_progress.py` was added with contract `gateway_sla_fail_nightly_progress_v1`: it aggregates readiness+governance history, publishes `remaining_for_window/remaining_for_streak`, and forms a `go|hold` decision-progress signal without weakening baseline criteria (`window=14`, `streak=3`).
* The nightly workflow `.github/workflows/gateway-sla-readiness-nightly.yml` was extended with a progress step + summary section `Gateway SLA Fail-Nightly Progress`; cache/artifact wiring now preserves `runs/nightly-gateway-sla-governance` and `runs/nightly-gateway-sla-progress` in addition to history/trend/readiness.
* For `G2` operator UX, a `Latest Metrics` progress block was added to `scripts/streamlit_operator_panel.py` (optional sources: readiness/governance/progress); missing nightly progress artifacts are treated as `not available yet`, not as UI failure.
* `streamlit_smoke_summary_v1` was extended additively with `required_missing_sources` and `optional_missing_sources`, while legacy `missing_sources` remains as the required-only alias; strict smoke policy (`missing => error`) still applies only to required canonical CI sources.

## 2026-03-03

* On `master`, the G2.3 transition layer was restored in the nightly workflow after revert drift (`bb36672`): transition step, gate resolve, conditional strict trend step, transition summary, and cache/artifact wiring for `runs/nightly-gateway-sla-transition` were brought back.
* Runtime/test guardrail for the transition contract was restored: `scripts/check_gateway_sla_fail_nightly_transition.py`, `src/agent_core/ops_policy.py`, `tests/test_check_gateway_sla_fail_nightly_transition.py`, `tests/test_gateway_sla_readiness_nightly_workflow.py`.
* Recovery policy was clarified: if `transition_summary.json` is missing in a successful UTC run, one recovery rerun is allowed in the same UTC day, but without progression credit toward switch evidence.
* For G2 consistency, a dual-write pattern was locked for nightly checkers (`readiness/governance/progress/transition`): each run writes a top-level latest alias and a history copy into `run_dir/<summary>.json`.
* Anti-double-count rule was fixed for history collectors in governance/progress/transition: when history copies exist, the top-level latest alias is excluded from the history scan; legacy layout can still fall back to the top-level latest alias.
* No backfill is performed for old G2 summary runs: the valid accumulation window for `valid_count` starts with the first nightly run after this hotfix was merged.
* For `G3/M6.19`, a new automation intent template `open_world_map` (keyboard-only) was added without changing the public `automation_plan_v1` contract: rollout included canonical fixture, CI smoke + strict contract-check, summary/artifact wiring, and e2e regression tests.
* For `G2.manual`, an API-driven preflight helper `scripts/check_gateway_sla_manual_preflight.py` with contract `gateway_sla_manual_preflight_v1` was backported to `master`; `allow/block` before manual `workflow_dispatch` is now formalized as machine-readable summary without side effects.
* `scripts/check_gateway_sla_manual_cycle_summary.py` with contract `gateway_sla_manual_cycle_summary_v1` was added as an aggregating helper: one operator-loop snapshot combines preflight decision with current readiness/governance/progress/transition status without changing CI/workflow or runtime API contracts.
* A local solo+AI wrapper `scripts/run_gateway_sla_manual_nightly.py` with contract `gateway_sla_manual_nightly_runner_v1` was added: manual nightly chain now runs without `workflow_dispatch`, under local artifact UTC guardrail (`1 accounted run/day`), with recovery mode lacking progression credit and with fail-fast policy.
* A read-only daily operator helper `scripts/check_gateway_sla_manual_cadence_brief.py` with contract `gateway_sla_manual_cadence_brief_v1` was added: a single machine-readable brief `attention_state + forecast(UTC ETA)` formalizes `run now vs wait/recovery/repair` without changing runtime/API/CI and while preserving `no-backfill` policy.
* For execution window `2026-03-03 -> 2026-03-17`, `G2-only until go/no-go` was adopted: parallel execution tracks (`G3/G5`) are deferred until gate review is complete.
* `G2 Conservative Gate` was fixed as `conservative` policy: strict switch is allowed only if all of the following are true simultaneously: `window_observed>=14`, `critical_count=0`, `warn_ratio<=0.20`, `latest_ready_streak>=3`, `transition.allow_switch=true`.
* Surface policy was locked as `nightly_only`: if a future `GO` happens, only nightly strict path switches; `pytest.yml` stays `signal_only` until a separate explicit decision.
* Baseline lock on `2026-03-03`: `pytest -q = 383 passed`, `progress.remaining_for_window=12`, `progress.remaining_for_streak=3`, `transition.allow_switch=false`, `decision_status=hold`; no runtime API or summary schema changes are planned inside this window.
* By explicit operator request, a manual switch override was performed: in `.github/workflows/gateway-sla-readiness-nightly.yml`, strict step `gateway_sla_trend_snapshot --critical-policy fail_nightly` now runs on every nightly run without `allow_switch`.
* After the override, `transition.allow_switch` remains as a telemetry field for traceability and does not block nightly strict execution.
* Surface policy remains unchanged: enforcement exists only in nightly workflow; `pytest.yml` stays `signal_only`.
* The override was applied without changing runtime API (`gateway_request_v1`, `gateway_response_v1`, HTTP endpoints) and without changing the schema versions of G2 summary contracts.

## 2026-03-08

* For post-switch remediation, a read-only helper `scripts/check_gateway_sla_fail_nightly_remediation.py` with contract `gateway_sla_fail_nightly_remediation_v1` was added: it aggregates only the latest published summaries (`readiness/governance/progress/transition` + optional `manual_cadence`) and does not recompute history.
* Remediation backlog is normalized into fixed deterministic buckets (`telemetry_integrity`, `regression_investigation`, `window_accumulation`, `ready_streak_stabilization`, `manual_guardrail`) and capped at five candidate items so nightly triage stays reviewable.
* Exit policy for the remediation helper is locked as `report_only|fail_if_remediation_required`; fail mode returns `exit_code=2` on broken required sources or a non-empty remediation backlog, without changing runtime API, Streamlit surface, or nightly workflow.

## 2026-03-12

* `G2.5` integrates remediation snapshot into the primary nightly workflow as a diagnostic-only layer: `.github/workflows/gateway-sla-readiness-nightly.yml` runs `check_gateway_sla_fail_nightly_remediation.py --policy report_only`, but does not add a new hard-fail surface beyond strict `gateway_sla_trend_snapshot --critical-policy fail_nightly`.
* Workflow-level remediation source-of-truth is fixed as `runs/nightly-gateway-sla-remediation/remediation_summary.json`; cache/artifact wiring for that path is preserved alongside `readiness/governance/progress/transition`.
* To preserve triage context on red nightly, G2 summary sections are published with `always()` semantics and must remain missing-safe, so `GITHUB_STEP_SUMMARY` does not lose diagnostics after a strict fail.
* For `G2.post3`, a dedicated integrity layer `scripts/check_gateway_sla_fail_nightly_integrity.py` with contract `gateway_sla_fail_nightly_integrity_v1` was added: it collapses required source health, telemetry counters, dual-write/anti-double-count, and UTC guardrail into one machine-readable verdict `clean|attention`.
* The integrity layer remains strictly diagnostic: nightly workflow publishes `runs/nightly-gateway-sla-integrity/integrity_summary.json` and summary section `Gateway SLA Fail-Nightly Integrity`, but does not add a new hard-fail surface beyond the existing strict trend gate.
* In Streamlit `Latest Metrics`, the integrity snapshot is treated as an optional published source: missing artifact results in `not available yet`, while parse/contract drift shows a warning without crashing the UI and without tightening smoke policy for required sources.

## 2026-03-13

* For the local `G2` operator loop, a preferred single-cycle entrypoint `scripts/run_gateway_sla_operating_cycle.py` was added with contract `gateway_sla_operating_cycle_v1`: the helper reuses fresh same-UTC latest summaries and falls back to a fixed-order manual path only when required sources are missing, stale, or invalid.
* In Streamlit `Latest Metrics`, `operating_cycle_summary.json` is treated as the primary read-only triage snapshot for `G2`; supporting `progress/remediation/integrity` blocks stay below it, and `Safe Actions` intentionally remain smoke-only and do not run `scripts/run_gateway_sla_operating_cycle.py`.
* `scripts/streamlit_operator_panel_smoke.py` now performs an early dependency preflight for `streamlit`: missing dependency is classified as `runtime_missing_dependency` before subprocess launch, writes a repair hint to `streamlit_startup.log`, and returns a normal `streamlit_smoke_summary_v1` with `status=error`, `startup_ok=false`, `exit_code=2`.

## 2026-03-20

* `docs/ECOSYSTEM_CONTEXT.md` was locked as a context-only reference: the file is needed for high-level compatibility with the AoA/ToS ecosystem, but it is not treated as a governing doc for local development.
* In case of conflict, priority remains with public repo source-of-truth documents (`MANIFEST.md`, `ROADMAP.md`, `docs/DECISIONS.md`, `docs/RUNBOOK.md`); ecosystem context influences architectural direction only, not local operating rules.
* For public-repo prep, internal chronology, session templates, PR body/comment drafts, and release coordination notes were moved out of the public tree into ignored local-only surfaces (`docs/internal/**` by default, with existing local `docs/SESSION_*.md` allowed for continuity).
* Public current-state entrypoints were narrowed to stable tracked docs (`MANIFEST.md`, `ROADMAP.md`, `docs/DECISIONS.md`, `docs/RUNBOOK.md`, `docs/SOURCE_OF_TRUTH.md`); session docs and PR-coordination docs no longer belong to the public repo surface.
* Public repo surface is now split from maintainer-local workflow docs: `ROADMAP.md` is the public planning document, while `TODO.md` and `PLANS.md` are local-only ignored files and do not belong to the public contract.
* Public entrypoints should link to `MANIFEST.md`, `ROADMAP.md`, `docs/RUNBOOK.md`, `docs/DECISIONS.md`, and `docs/SOURCE_OF_TRUTH.md`; `TODO.md` and `PLANS.md` remain valid for local execution only.
* Public-repo hardening keeps FastAPI-generated `/docs` and `/openapi.json` disabled by default for `scripts/gateway_v1_http_service.py` and `scripts/tts_runtime_service.py`; local debugging may opt in explicitly with `--expose-openapi` while loopback binding remains the default.
* Public workflow and runbook examples should avoid reusable password literals and workstation-specific absolute paths: local-only placeholder credentials are acceptable for ephemeral CI/service containers, but examples should route through env vars/placeholders and generic local-path wording.
* Public doc examples were normalized accordingly: `README.md`, `AGENTS.md`, and `docs/RUNBOOK.md` now use `<repo-root>` / `<path-to-...>` placeholders and env-driven token setup instead of workstation-specific absolute paths or reusable demo token literals.
* `docs/RELEASE_WAVE6.md` remains tracked as a public engineering reference only after stripping PR choreography, reviewer assignments, checklist language, and local `runs/**` evidence paths; durable contract and rollout meaning stays, internal coordination does not.
* Public-readiness hardening now requires deliberate intent for non-loopback HTTP service binds: `gateway_v1_http_service`, `tts_runtime_service`, and `voice_runtime_service` stay backward-compatible on loopback without a token, but non-loopback startup requires `--service-token` / `ATM10_SERVICE_TOKEN` unless `--allow-insecure-no-token` is passed explicitly.
* `voice_runtime_service` error artifacts now follow the same public-safe default posture as gateway/TTS: `service_errors.jsonl` stores a sanitized envelope plus redaction metadata by default, while raw exception text/traceback is available only through explicit unsafe opt-in.
* Public GitHub workflow surfaces are intentionally coarse: step summaries should expose status/count-level health only, keep runner-local absolute paths out of `GITHUB_STEP_SUMMARY`, and upload allowlisted machine-readable summaries instead of broad run trees whenever practical.
