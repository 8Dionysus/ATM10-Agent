# DECISIONS

## 2026-02-19

* Phase A smoke использует `DeterministicStubVLM` через интерфейс `VLMClient`, чтобы держать loop engine-agnostic и не блокироваться на модели.
* Скриншот в smoke-runner сохраняется как валидный placeholder PNG без внешних зависимостей; реальный capture будет подменен позже без изменения artifact contract.
* Для Phase B зафиксирован JSONL doc contract: `id`, `source`, `title`, `text`, `tags`, `created_at`; добавлен tiny fixture dataset для тестов.
* В ingest `ftbquests` стартовая итерация поддерживала только JSON-файлы; это решение позже superseded SNBT fallback-веткой (см. решения от 2026-02-20).

## 2026-02-20

* Для completion M2 выбран `in-memory retrieval` как first step без Docker/Qdrant: это закрывает `top-k + citations` и оставляет API-границу для последующей интеграции Qdrant.
* `scripts/retrieve_demo.py` пишет artifacts в `runs/<timestamp>/` (`run.json`, `retrieval_results.json`) для воспроизводимости и отладки.
* Qdrant интеграция добавлена как optional backend через REST API (без новых Python dependencies): `scripts/ingest_qdrant.py` + `scripts/retrieve_demo.py --backend qdrant`.
* В нормализации квестов добавлен lightweight fallback для `.snbt`: индексируем файл как документ без полного SNBT-парсера, чтобы обеспечить рабочий retrieval baseline на реальных ATM10 данных.
* Ingest в Qdrant сделан идемпотентным для сценария "collection already exists" (HTTP 409): pipeline продолжает upsert и не падает.
* Для снижения retrieval-noise в baseline ingestion по умолчанию исключает `lang/**` и `reward_tables/**` из индекса; основной фокус индекса — квестовые главы/структуры, а не локализации и reward tables.
* Phase B baseline validated e2e на локальном ATM10 + Qdrant (`normalize -> ingest -> retrieve`) с рабочими top-k + citations.
* Для hardware-accelerated inference baseline добавлен OpenVINO (`openvino==2025.4.1`) и зафиксирован диагностический workflow в `docs/RUNBOOK.md` с artifact-отчетом в `runs/<timestamp>-openvino/`.
* Для повышения retrieval relevance принят двухэтапный поиск: first-stage candidate retrieval + second-stage rerank; в CLI добавлены `--candidate-k` и `--reranker` (`none|qwen3`) с baseline по умолчанию `none`.
* Специализированный rerank выбран через семейство `Qwen3-Reranker`; стартовая целевая модель для rollout — `Qwen/Qwen3-Reranker-0.6B` (опционально, без обязательного добавления heavy deps в baseline).
* Зафиксирована EOL-политика через `.gitattributes`: source/docs/config по LF, Windows scripts (`*.ps1`, `*.bat`, `*.cmd`) по CRLF для стабильных diff и меньшего шума.
* Для настройки retrieval defaults добавлен reproducible benchmark `scripts/eval_retrieval.py` (Recall@k, MRR@k, hit-rate) с артефактами в `runs/<timestamp>/`; подбор `topk/candidate_k/reranker` теперь делается по метрикам, а не по ручным примерам.
* Интеграция `Qwen3-Reranker` выровнена с официальным scoring-flow (yes/no logits через CausalLM prompt), чтобы избежать некорректного режима `SequenceClassification` и получать валидный rerank score.
* В first-stage tokenization добавлен split по `_` (с сохранением исходного токена), чтобы запросы вида `metallurgic infuser` корректно матчились с `metallurgic_infuser`.
* По grid-eval на реальном ATM10 `chapters/*` (`runs/20260220_m2_calibration_none/`) зафиксированы production defaults:
  `topk=5`, `candidate_k=50`, `reranker=none`; для `topk>=3` метрики совпали, `topk=1` хуже по Recall/hit-rate.
* Для `qwen3` добавлен runtime-переключатель `torch|openvino` и device-параметр (`AUTO|CPU|GPU|NPU`) в retrieval/eval CLI, чтобы ускорять rerank на Intel GPU/NPU через `torch.compile(..., backend="openvino")` без изменения baseline `reranker=none`.
* SNBT signal extraction для Phase B улучшен: в ingestion учитываются не только quoted, но и unquoted значения ключей (`id/type/dimension/structure/filename/...`), что повышает recall по квестам в `chapters/*`.
* Для first-stage retrieval в `chapters/*` принят field-weighted scoring (`title/text/tags`) + stopword filtering: это снижает ложные совпадения по служебным словам (`and/the/...`) и поднимает релевантную главу при запросах по модам (например, `ars nouveau`).
* Phase A VLM provider теперь переключаемый (`auto|stub|openai`) через CLI/env: baseline остается стабильным (stub fallback), а real provider подключается через `VLMClient` interface без изменения artifact contract.
* Зафиксирован основной модельный стек проекта на `Qwen3` (text/vl/retrieval/voice) с политикой `OpenVINO-first`: используем готовые `OpenVINO/*Qwen3*` репозитории там, где они есть, и делаем self-conversion для остальных моделей (без замены на `Qwen2.5*`).
* Для self-conversion Qwen3 в OpenVINO зафиксирован единый entrypoint `scripts/export_qwen3_openvino.py` с preset-профилями (`qwen3-vl-4b`, `qwen3-asr-0.6b`) и dry-run-first режимом с артефактами в `runs/<timestamp>-qwen3-export/`.
* По фактическому запуску `--execute` (2026-02-20) зафиксированы upstream-ограничения: `qwen3_vl` пока не поддерживается `optimum-intel` нативно, а `qwen3_asr` не проходит через текущий `transformers/optimum` export path. Политика сохраняется: остаемся на Qwen3, используем готовые OV-репозитории где доступны и держим self-conversion path до появления поддержки.
* Для `qwen3-vl-4b` добавлен отдельный custom-export entrypoint `scripts/export_qwen3_custom_openvino.py` (через `custom_export_configs + fn_get_submodels`) и поддержка `--model-source` (HF repo id или локальный путь). Этот путь успешно собрал OpenVINO IR в `models/qwen3-vl-4b-instruct-ov-custom` (run: `runs/20260220_150028-qwen3-custom-export/`).
* После успешного `qwen3-vl` custom export выполнена очистка локальных HF-кэшей (`models/hf_cache`, `models/hf_raw/qwen3-vl-4b`, `C:\Users\Admin\.cache\huggingface`) для освобождения диска; решение принято с пониманием, что при повторных экспорт/инференс сценариях потребуется повторная загрузка весов.
* Для `qwen3-asr-0.6b` в `scripts/export_qwen3_custom_openvino.py` включен отдельный execute-path через `main_export` (вместо заглушки "not implemented"), а при ошибках экспорта теперь сохраняется `diagnostic` в `run.json`, чтобы явно отделять upstream-блокер `qwen3_asr` от общих runtime ошибок.
* Для `Qwen3-TTS-12Hz-0.6B-CustomVoice` добавлен отдельный scaffold entrypoint `scripts/export_qwen3_tts_openvino.py`: dry-run фиксирует план и probe-результаты (model/tokenizer), а `--execute` пока сознательно завершаетcя с диагностикой до появления полного custom export path.
* Для устойчивости к upstream API-changes в `optimum` добавлен compatibility-resolver Qwen VL export classes (`Qwen3VLOpenVINOConfig|Qwen2VLOpenVINOConfig|QwenVLOpenVINOConfig` + behavior enum variants), а в TTS scaffold probe сделан lazy-import `transformers.AutoConfig`, чтобы при version mismatch получать диагностируемый `run.json`, а не import-time crash.
* Результат изолированного nightly-эксперимента (`runs/20260220_190319-qwen3-exp-venv-probe/`): даже с `optimum/optimum-intel` из `main` и проверками в отдельном `.venv-exp` `AutoConfig` по-прежнему не распознает `qwen3_asr`/`qwen3_tts`, поэтому держим стратегию `upstream-first` и ждем нативной поддержки архитектур.
* Для voice-конверсии добавлен единый probe-слой `scripts/probe_qwen3_voice_support.py` с machine-readable статусами `supported|blocked_upstream|import_error|runtime_error`; этот контракт используется в ASR/TTS exporters и фиксируется в `export_plan.json`.
* Для повторяемых nightly-проверок upstream добавлен matrix runner `scripts/qwen3_voice_probe_matrix.py` (dry-run/execute, опциональный `--with-setup` для `.venv-exp`), чтобы сравнивать комбинации `transformers/optimum` без ручного переписывания команд.
* Matrix setup-профили для voice-probe ограничены совместимыми `transformers`-вариантами (`main` и `4.57.6`) без принудительной установки `optimum/optimum-intel`, чтобы избежать частых pip resolver-конфликтов и держать nightly-check воспроизводимым.
* Для voice exporters зафиксирован unlock-gate контракт: если probe-status не `supported`, `--execute` завершается со статусом `blocked` и `error_code=unlock_gate_blocked`; только при `unlock_ready=true` выполняется попытка экспорта.
* Для operational Phase C добавлен native runtime path (без ожидания OpenVINO-export unlock): `scripts/asr_demo.py` и `scripts/tts_demo.py`, с общей runtime-обвязкой в `src/agent_core/io_voice.py`.
* Для voice runtime зафиксирован практический install-path: базовые deps в `requirements.txt` + отдельная установка `qwen-asr==0.0.6`, `qwen-tts==0.1.1 --no-deps` и доп.пакетов `onnxruntime/einops/torchaudio`; причина — конфликтующие `transformers` pin'ы в upstream пакетах (состояние на 2026-02-20).
* Для production-path Phase C выбран long-lived runtime: `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py`; это устраняет повторный model load на каждый запрос и минимизирует latency в steady-state для голосового цикла проекта.
* По benchmark-замерам (`runs/20260220_211505-voice-latency-bench/`, `runs/20260220_211708-voice-latency-oneshot-bench/`) подтверждено, что текущий CPU runtime укладывает ASR в sub-second warm path, но не укладывает `Qwen3-TTS` в in-game SLA `<=2s`; для production game-loop нужен отдельный fast-TTS fallback path, а `Qwen3-TTS` сохраняется как optional HQ mode.
* Для `scripts/export_qwen3_tts_openvino.py` добавлен `--backend notebook_helper` (experimental): путь использует `qwen_3_tts_helper` из `openvino_notebooks`, не зависит от `AutoConfig` support для `qwen3_tts*` и сохраняет стандартный artifact contract (`run.json`, `export_plan.json`, `export_stdout.log`, `export_stderr.log`).
* Для `scripts/export_qwen3_tts_openvino.py` добавлен `--weights-quantization` (`none|int8|int8_asym|int8_sym`) в `notebook_helper` backend; на целевом хосте `int8_asym` дал ускорение CPU warm-path TTS (~`10.4-11.4s` -> ~`9.5-9.6s`) при неизменном NPU compile blocker по dynamic-graph компонентам.
* Эксперимент `int4_asym` добавлен в `--weights-quantization` (`int4_asym|int4_sym`): на текущем хосте CPU warm-path ускорился дополнительно до ~`8.7-9.5s` (artifact: `runs/20260220_222426-qwen3-tts-ov-speed-bench-int4-cpu/`), GPU warm-path остаётся вариативным (~`8.8-12.3s`), а NPU compile для TTS pipeline по-прежнему `0/10` (artifact: `runs/20260220_222650-qwen3-tts-npu-compile-diag-int4/`).
* Для снижения perceived latency в voice runtime добавлен streaming-контракт `POST /tts_stream` (NDJSON events) и режим клиента `tts-stream`; в артефактах теперь фиксируются `first_chunk_latency_sec`, `total_synthesis_sec`, `rtf` и `streaming_mode` для воспроизводимого latency-профилирования.
* Принято решение деактивировать `Qwen3-TTS` в active stack (2026-02-20): production path для voice ограничен ASR (`qwen-asr`), TTS-эксперименты сохранены только как historical artifacts; `qwen-tts` удален из рабочего `.venv`, `.venv-exp` удалено как cleanup-хвост.

## 2026-02-21

* Принято разделение зависимостей на runtime/dev: `requirements.txt` содержит только runtime-пакеты, `requirements-dev.txt` включает runtime + `pytest` для локального тестирования и CI.
* Для закрытия voice SLA-gap принят отдельный native Python TTS runtime как independent service/container: Router=`FastAPI`, main engine=`XTTS v2`, fallback engines=`Piper` + `Silero` (для русской служебной озвучки), с operational техниками prewarm/queue/chunking/phrase cache.

## 2026-02-22

* Зафиксирован operational-path для custom exporter: `scripts/export_qwen3_custom_openvino.py` должен быть runnable и как module (`python -m scripts.export_qwen3_custom_openvino`), и как script (`python scripts/export_qwen3_custom_openvino.py`); добавлен fallback import и smoke-test на `--help`.
* В рабочем runtime-only окружении поддерживаем probe-first политику для ASR export: если `support_probe.status=import_error` (например, отсутствует `transformers`), считаем `unlock_gate.ready=false` и не делаем ложных выводов о natively-supported `qwen3_asr` до отдельного export-toolchain прогона.
* После отдельного прогона в `.venv` с установленным `transformers/optimum/optimum-intel` зафиксирован `blocked_upstream` для `qwen3_asr` (run artifacts: `runs/20260222_142450-qwen3-voice-probe/`, `runs/20260222_142518-qwen3-custom-export/`): текущий unlock-gate блокируется upstream-support, а не локальной нехваткой пакетов.
* Для быстрого NPU-ASR пути принят дополнительный runtime-branch на `OpenVINO GenAI + Whisper v3 Turbo` (`scripts/asr_demo_whisper_genai.py`) без замены основного `qwen-asr` branch: это снижает зависимость от upstream-support `qwen3_asr` в `transformers/optimum`.
* Long-lived voice runtime расширен переключаемым ASR backend (`qwen_asr|whisper_genai`) в `scripts/voice_runtime_service.py`; для `whisper_genai` добавлены параметры `--asr-device` и `--asr-task`, при этом контракт `/asr` и `voice_runtime_client` сохранён без breaking changes.
* Для сравнения operational ASR-веток добавлен reproducible benchmark `scripts/benchmark_asr_backends.py` с artifacts (`summary.json`, `summary.md`, `per_sample_results.jsonl`) в `runs/<timestamp>-asr-backend-bench/`; baseline run `runs/20260222_152347-asr-backend-bench/` показал сопоставимый avg latency (`qwen_asr` ~1.377s vs `whisper_genai` NPU ~1.364s) на одинаковом локальном наборе WAV.
* Для снижения cold-start impact в игровом цикле добавлен startup warmup request в `scripts/voice_runtime_service.py` (`--asr-warmup-request`, опционально `--asr-warmup-audio`/`--asr-warmup-language`) и helper launcher `scripts/start_voice_whisper_npu.ps1` для low-latency профиля `whisper_genai + NPU + warmup`.
* Принято решение архивировать `Qwen3-ASR-0.6B` как recoverable path: активный ASR backend в runtime сменен на `whisper_genai`, а `qwen_asr` сохраняется в коде только за explicit opt-in флагами.
* Для reversible-архивации `qwen_asr` добавлены guard-флаги без удаления кода:
  `scripts/voice_runtime_service.py --allow-archived-qwen-asr`,
  `scripts/asr_demo.py --allow-archived-qwen-asr`,
  `scripts/benchmark_asr_backends.py --include-archived-qwen-asr`.
* Operational policy: baseline/документация/дефолты используют только `whisper_genai`; archived path держим для точечного rollback и future restore после upstream unlock.
* Для M3.1 добавлен lightweight runnable path text-core на OpenVINO GenAI: `scripts/text_core_openvino_demo.py` с artifact contract (`run.json`, `response.json`) и graceful dependency error (`runtime_missing_dependency`) без изменения baseline dependencies.
* Для M3.1 retrieval зафиксирован profile-layer `baseline|ov_production` (`src/rag/retrieval_profiles.py`): OV profile включает `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov` + `reranker_runtime=openvino`, а baseline остается совместимым с текущим CI/dev loop.
* Для HUD assistance выбран dependency-light OCR baseline через системный `tesseract` CLI (`scripts/hud_ocr_baseline.py`) вместо добавления новых Python OCR библиотек: это сохраняет reproducibility и не меняет `requirements.txt`.
* Для HUD mod-hook baseline выбран file-based ingest контракт (`scripts/hud_mod_hook_baseline.py`) с нормализацией в machine-readable артефакт (`hook_normalized.json`): это позволяет интегрировать разные mod hooks без жёсткой привязки к конкретному транспорту.
* Для Graph/KAG принят file-based baseline без инфраструктурных зависимостей (`src/kag/baseline.py`, `scripts/kag_build_baseline.py`, `scripts/kag_query_demo.py`) с artifact contract `kag_graph.json` и `kag_query_results.json`.
* Переход Graph/KAG на Neo4j подтвержден как целевой этап; добавлены runnable entrypoints `scripts/kag_sync_neo4j.py` и `scripts/kag_query_neo4j.py` (HTTP Cypher path без новых Python dependencies).
* Neo4j path подтвержден e2e-прогоном на локальном контейнере (`runs/20260222_164928-kag-build/` -> `runs/20260222_164942-kag-sync-neo4j/` -> `runs/20260222_165026-kag-query-neo4j/`) с latency snapshot в `runs/20260222_165100-kag-neo4j-e2e/e2e_latency_snapshot.json`.
* Для Neo4j KAG зафиксирован reproducible benchmark entrypoint `scripts/eval_kag_neo4j.py` с метриками `Recall@k/MRR@k/hit-rate` и latency (`mean/p95/max`) на фиксированном JSONL eval-наборе.
* Для KAG Neo4j принят двухнаборный benchmark-подход: `sample` (стабильный regression-check) + `hard` (gap-finding по relevance), чтобы развивать качество без потери latency контроля.
* Для закрытия hard-cases relevance gap в `query_kag_neo4j` добавлен lexical fallback по `Doc.title/doc_id` (дополнительный score поверх graph-сигналов), что подняло `hit-rate@5` до `1.0` на run `runs/20260222_170453-kag-neo4j-eval/`; latency trade-off зафиксирован отдельно.
* Для снижения tail latency после relevance uplift принят hybrid-query режим в `query_kag_neo4j`: сначала fulltext lexical lookup, затем ограниченный scan fallback только при пустом fulltext-результате; lexical path выполняется только при `direct_rows < topk`, а expansion отключается для single-token queries.
* Для single-token hard-case запросов в `query_kag_neo4j` добавлен post-merge lexical alignment bonus по `doc_id/title` (+canonical boost для `:chapters/chapter_`), чтобы уменьшить влияние "шумных" graph-only матчей и поднять целевую главу в топ (`star.first_hit_rank`: `4 -> 1` в `runs/20260222_213235-kag-neo4j-eval/`).
* Для снижения latency без потери relevance в `query_kag_neo4j` введен scan-fallback gating: при `fulltext=empty` fallback `MATCH (d:Doc)` выполняется для multi-token только если `direct_rows=0`, а для single-token — только если в direct hits нет lexical alignment по `title/doc_id` (после удаления namespace `ftbquests:` из `doc_id`-matching). Это сохранило `star.first_hit_rank=1` и снизило hard `latency_p95_ms` до `83.68` (`runs/20260222_214352-kag-neo4j-eval/`).
* Для стабильных latency-метрик в `scripts/eval_kag_neo4j.py` добавлен опциональный benchmark-warmup (`--warmup-runs`): перед измеряемым циклом выполняются прогревочные проходы по тем же queries, но они не попадают в `eval_results.json` метрики. С warmup (`--warmup-runs 1`) получен более устойчивый benchmark snapshot: sample `latency_p95_ms=72.10` (`runs/20260222_215053-kag-neo4j-eval/`), hard `latency_p95_ms=92.41` (`runs/20260222_215058-kag-neo4j-eval/`).
* Для регулярной проверки эффекта warmup добавлен отдельный мини-benchmark entrypoint `scripts/compare_kag_neo4j_warmup.py`: он запускает baseline/candidate профили сериями (`repeats`) и пишет агрегированные `p95` дельты в `summary.json`/`summary.md` (пример run: `runs/20260222_215707-kag-neo4j-warmup-compare/`).
* Для направления automation введен безопасный baseline `scripts/automation_dry_run.py`: entrypoint принимает JSON action-plan, нормализует его и пишет execution plan artifacts, но намеренно не отправляет keyboard/mouse события в ОС; любые реальные automation actions остаются out-of-scope без отдельного explicit approval.
* Документационная структура приведена к единому source of truth: `TODO.md` используется только как execution-план (Now/Next/Blocked + WIP=3), `PLANS.md` — только как цели/milestones/DoD, подробная хронология и run-детали перенесены в `docs/SESSION_*.md`.
* Archived/recoverable направления вынесены в отдельный реестр `docs/ARCHIVED_TRACKS.md`, чтобы roadmap не смешивался с recovery-треками.
* Счетчики вида `N passed` не дублируются по всем статус-докам: оперативная истина фиксируется в CI и в последнем `docs/SESSION_*.md` snapshot.

## 2026-02-23

* Для `automation_dry_run` зафиксирован явный action-plan контракт `automation_plan_v1`: валидируем `schema_version`, добавляем нормализацию `intent` (`goal/priority/tags/constraints`) и сохраняем его в `actions_normalized.json` для интеграции с planning-слоем.
* В контракте введено правило уникальности `action.id`, чтобы предотвратить неоднозначность в downstream execution traces и regression-тестах.
* Для reproducible demo-path добавлены canonical сценарии `tests/fixtures/automation_plan_quest_book.json` и `tests/fixtures/automation_plan_inventory_check.json`; runbook обновлен командами прямого запуска этих fixtures.
* Для `M6.3` добавлен lightweight adapter `scripts/intent_to_automation_plan.py` (`automation_intent_v1` -> `automation_plan_v1`) с детерминированными template-intent сценариями (`open_quest_book`, `check_inventory_tool`) и artifact contract `runs/<timestamp>-intent-to-automation-plan/{run.json,automation_plan.json}`.
* Для `M6.4` добавлен единый smoke entrypoint `scripts/automation_intent_chain_smoke.py`, который оркестрирует dry-run цепочку `intent -> automation_plan_v1 -> automation_dry_run` и пишет chain artifacts (`run.json`, `chain_summary.json`, `automation_plan.json`) с ссылками на child runs.
* Для `M6.5` CI smoke расширен двумя lightweight automation-сценариями на фиксированных fixtures: `scripts/automation_dry_run.py --plan-json tests/fixtures/automation_plan_quest_book.json` и `scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json`.
* Для снижения flaky-риска в CI выбран fixture-only подход без внешних сервисов/девайсов: новые smoke-steps не требуют Docker, аудио-устройств или модельных runtime-загрузок.
* Для `KAG quality guardrail` зафиксированы canonical threshold-профили `sample|hard` и отдельный checker `scripts/check_kag_neo4j_guardrail.py` для явного pass/fail по `recall/mrr/hit-rate/latency_p95`.
* Для `M6.6` зафиксирован CI contract-check layer для automation smoke: `scripts/check_automation_smoke_contract.py` проверяет artifact contract и минимальные thresholds; шаги валидации добавлены в `.github/workflows/pytest.yml`.
* Для `M5.3` guardrail-path переведен в отдельный nightly workflow `.github/workflows/kag-neo4j-guardrail-nightly.yml` (`build -> sync -> eval sample/hard -> guardrail-check`) с upload artifacts и step summary.
* Для `M6.7` в `scripts/check_automation_smoke_contract.py` добавлен machine-readable output (`--summary-json`), а в CI smoke job добавлены summary/report шаг и artifact upload для контрактных проверок.
* Для `M5.4` добавлен lightweight trend-snapshot script `scripts/kag_guardrail_trend_snapshot.py`, который сравнивает latest метрики `sample/hard` из nightly run artifacts и пишет `trend_snapshot.json` + `summary.md`.
* Для `M6.8` troubleshooting playbook по automation smoke contract failures зафиксирован в `docs/RUNBOOK.md` как canonical оперативная процедура диагностики.
* Для `M5.5` nightly workflow дополнен trend-report шагом: `kag_guardrail_trend_snapshot.py` выполняется в CI, а результаты добавляются в `GITHUB_STEP_SUMMARY` и в upload artifacts (`runs/nightly-kag-trend`).
* Для `M6.9` в CI smoke summary добавлен прямой quick-link на runbook section `M6.8`, чтобы сократить time-to-diagnosis при контрактных падениях.
* Для `M5.6` trend snapshot расширен rolling-baseline сравнением (`latest` vs mean previous N runs) с отдельными baseline-дельтами в `trend_snapshot.json`, `summary.md` и nightly step summary.
* Для `M6.10` quick-link на runbook troubleshooting (`M6.8`) продублирован в nightly guardrail summary, чтобы CI/nightly отчеты имели единый path к диагностике.
* Для `M5.7` в `kag_guardrail_trend_snapshot` добавлен regression-статус слой для rolling-baseline (`mrr` и `latency_p95`: `improved|stable|regressed|insufficient_history`) и агрегированный флаг `has_any_regression`.
* Для doc-hygiene на закрытии сессии `README.md` и `MANIFEST.md` переведены в lightweight snapshot-формат с ссылками на `TODO/PLANS/RUNBOOK/SESSION`, чтобы исключить расхождение длинных статус-блоков.
* Для weekly ретроспектив зафиксирован единый one-screen шаблон `docs/SESSION_WEEKLY_TEMPLATE.md`; `docs/SOURCE_OF_TRUTH.md` обновлен с явной ролью шаблона.

## 2026-02-24

* В `scripts/voice_runtime_service.py` зафиксирован безопасный контракт `out_wav_path`: сервис принимает только имя файла и всегда пишет TTS output внутри `runs/<timestamp>-voice-service/tts_outputs`; абсолютные и вложенные пути из HTTP payload запрещены.
* Для совместимости с этим контрактом `scripts/voice_runtime_client.py` отправляет в `out_wav_path` только безопасное имя файла (basename), а не абсолютный локальный путь.
* В `voice_runtime_service` internal-error path санитизирован: traceback больше не отдается клиенту в `/tts` и `/tts_stream`; полный traceback теперь пишется только в локальный artifact `service_errors.jsonl`.
* `scripts/retrieve_demo.py` теперь всегда пишет `run.json`, включая backend failure path (`status=error`, `error_code=retrieval_backend_error`), чтобы не терять диагностический артефакт неуспешного запуска.
* `scripts/export_qwen3_tts_openvino.py` приведен к dual-run контракту (module + direct script execution через fallback import); добавлен regression test на `python scripts/export_qwen3_tts_openvino.py --help`.
* `scripts/discover_instance.py` унифицирован по политике run-dir creation: добавлен suffix-loop при timestamp-collision (`_01`, `_02`, ...), чтобы убрать флейки параллельных/повторных запусков в ту же секунду.
* Для `scripts/tts_runtime_service.py` зафиксирован supply-chain hardening для Silero: remote `torch.hub` источник заблокирован по умолчанию, разрешается только через `SILERO_ALLOW_REMOTE_HUB=true` и pinned revision (`SILERO_REPO_REF` или `owner/repo:ref`); local path остается разрешенным без opt-in.
* Для `M5.8` в `scripts/kag_guardrail_trend_snapshot.py` приняты калибруемые severity thresholds для rolling-baseline регрессий: `mrr` (`warn=0.005`, `critical=0.02`) и `latency_p95_ms` (`warn=2.0`, `critical=8.0`).
* Для обратной совместимости guardrail-анализа сохранен текущий boolean сигнал `has_any_regression` (любой факт регрессии), а severity добавлен отдельными полями (`mrr_regression_severity`, `latency_p95_regression_severity`, `max_regression_severity`).
* Для интеграции `M6.1` с верхним planning-слоем в `automation_plan_v1` принят optional metadata envelope `planning`; adapter `intent_to_automation_plan` теперь пишет туда `intent_type`, `intent_schema_version`, `adapter_name/version` и пробрасывает `intent_id/trace_id` при наличии во входном intent payload.
* Для сквозной корреляции automation CI artifacts в `scripts/check_automation_smoke_contract.py` `summary_json.observed` расширен optional полями `trace_id/intent_id` (из `planning`; для `trace_id` добавлен fallback через `chain_summary/run.json` в intent-chain режиме).
* Для ускорения triage в CI summary `.github/workflows/pytest.yml` таблица `Automation Smoke Contracts` расширена колонками `trace_id` и `intent_id`; canonical automation fixtures получили стабильные correlation ids.
* Для canonical intent-chain smoke в CI включен strict-check `--require-trace-id` в `check_automation_smoke_contract`: отсутствие `trace_id` теперь трактуется как contract violation и завершает шаг с non-zero exit code.
* Для canonical intent-chain smoke в CI дополнительно включен strict-check `--require-intent-id`; отсутствие `intent_id` также трактуется как contract violation и завершает шаг с non-zero exit code.
* Для стандартизации onboarding новых `intent_type` policy formalized в `docs/RUNBOOK.md` (`M6.19`): обязательны fixture, smoke run, strict contract-check (`--require-trace-id`, `--require-intent-id`), summary/artifact wiring и минимум один e2e regression test.
* Для `G3` стандартизирован machine-readable summary слой и для non-automation smoke в `pytest` workflow: добавлен `scripts/collect_smoke_run_summary.py` (`phase_a_smoke|retrieve_demo|eval_retrieval`) с единым `smoke_summary.json` контрактом и upload в общий smoke summaries artifact.
* Для `G2` policy по `critical` trend severity формализован в `scripts/kag_guardrail_trend_snapshot.py`: baseline режим `critical_policy=signal_only` (nightly не фейлится по trend severity), при этом добавлен explicit opt-in режим `critical_policy=fail_nightly` для ужесточенного guardrail.
* По локальной warmup=1 истории `kag-neo4j-eval` выполнена калибровка latency severity thresholds в `kag_guardrail_trend_snapshot`: `warn 2.0 -> 5.0 ms`, `critical 8.0 -> 15.0 ms` (наблюдаемый noise-floor по rolling-baseline latency regression доходил до ~`13.9 ms` без quality-regression по MRR).
* Стратегический production baseline зафиксирован как `Combo A`: unified local backend (`FastAPI gateway + workers + Qdrant + Neo4j + runs artifacts`) и frontend path `Streamlit` operator panel с CLI fallback.
* Model/runtime policy уточнена как pragmatic hybrid: `Qwen3` остается core для text/retrieval, active ASR path — `Whisper GenAI`; drift к `Qwen2.5*` в core stack не допускается.
* Планирование (`PLANS/TODO`) отвязано от стабильности конкретного audit-файла: текущая стратегия фиксируется напрямую в source-of-truth документах без hard reference на перемещаемые артефакты.

## 2026-02-27

* Для `M7.0` зафиксирован contract-first локальный gateway path без новых dependencies: `scripts/gateway_v1_local.py` принимает `gateway_request_v1` и всегда пишет `request.json/run.json/response.json` с `gateway_response_v1` контрактом.
* В gateway v1 принят operation set `health|retrieval_query|kag_query|automation_dry_run`; `kag_query` по умолчанию работает в `file` backend и держит `neo4j` как optional backend, чтобы smoke path оставался стабильным без внешних сервисов.
* Для CI smoke добавлены два lightweight сценария `scripts/gateway_v1_smoke.py` (`core`, `automation`) с machine-readable summary (`gateway_smoke_summary.json`) и fail-fast при любом `status=error`.
* Для `M7.1` зафиксирован canonical HTTP transport `POST /v1/gateway` как thin-wrapper над `run_gateway_request`, чтобы исключить drift между CLI и HTTP body-контрактом (`gateway_request_v1`/`gateway_response_v1`).
* В `gateway_v1_http_service` зафиксирован явный HTTP status mapping: `ok -> 200`, `invalid_request -> 400`, `operation_failed|gateway_dispatch_failed -> 500`, при этом body всегда остается `gateway_response_v1`.
* Для проверки transport-пути добавлен отдельный runnable smoke `scripts/gateway_v1_http_smoke.py` (`core`, `automation`) с machine-readable summary (`gateway_http_smoke_summary.json`) и CI fail-fast policy.
* Для `M7.2` принят hardening profile `Balanced` для `POST /v1/gateway`: `max_request_body_bytes=262144`, `max_json_depth=8`, `max_string_length=8192`, `max_array_items=256`, `max_object_keys=256`, `operation_timeout_sec=15.0`.
* Для timeout policy зафиксирован transport-level контракт: `operation_timeout` возвращается как sanitized `gateway_response_v1` и маппится в HTTP `504`.
* Для internal-error policy клиент получает только sanitized envelope (`internal_error_sanitized`), а подробности исключений (`traceback` + request context) пишутся локально в `runs/.../gateway_http_errors.jsonl`.
* Для `M8.0` IA Streamlit panel v0 зафиксирована как отдельный single source document `docs/STREAMLIT_IA_V0.md`; реализация `M8.1` должна следовать этому документу без дополнительных продуктовых решений.
* Для сохранения IA contract добавлен regression test `tests/test_streamlit_ia_doc.py` (обязательные секции, canonical data sources, gateway dependency `GET /healthz` + `POST /v1/gateway`).
* Для `M8.1` `streamlit` добавлен в runtime dependencies (`requirements.txt`), чтобы panel entrypoint и smoke path были reproducible локально и в CI.
* Для `M8.1` no-crash smoke реализован через реальный subprocess `python -m streamlit run ...` с timeout/terminate policy и machine-readable summary `streamlit_smoke_summary_v1`.
* В CI для Streamlit smoke принят strict policy `missing_sources => error`, чтобы panel не маскировала отсутствие canonical summaries в runs tree.
* Для `M7.post` принят `signal-first` SLA режим для gateway: default policy `signal_only` не валит CI на breach, но всегда публикует machine-readable `gateway_sla_summary_v1` с метриками и breaches.
* Для SLA baseline выбран профиль `conservative` (`latency_p95<=1500ms`, `error_rate<=0.05`, `timeout_rate<=0.01`) как стартовый operating point до последующего tightening.
* Gateway smoke summaries (`local` + `http`) расширены observability-полями (`started/finished`, `duration_ms`, per-request `latency_ms`, `latency_p50/p95/max`, `error_buckets`) без изменения существующих response body-контрактов.
