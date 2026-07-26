# Optional model and hardware providers

Current as of: 2026-07-25

This historical filename now records provider posture, not an application
topology or a claim that a particular model stack is required.

## Core rule

The default `atm10_agent` turn uses deterministic perception and the
file-backed world. Models and accelerators enrich that turn through replaceable
providers. They never own the composition root, trace, action fence, build,
test, or release contract.

## Current optional implementation anchors

- `agent_core/vlm_stub.py`: deterministic acceptance provider;
- `agent_core/vlm_openvino.py`: local OpenVINO vision provider;
- `agent_core/vlm_openai.py`: optional remote vision provider;
- `agent_core/grounded_reply_openvino.py`: local grounded-response provider;
- `agent_core/io_voice.py`: optional ASR/TTS implementation helpers;
- `agent_core/tts_runtime.py`: in-process TTS engine/router behavior;
- `rag/retrieval.py`: in-memory baseline plus optional Qdrant path;
- `kag/neo4j_backend.py`: optional Neo4j product-store adapter.

All optional dependencies must be loaded at the use site and return explicit
unavailable/degraded evidence when absent.

## OpenVINO posture

OpenVINO remains a validated provider family and is declared by the
`openvino` optional extra. Device placement is provider configuration, not
repository architecture. CPU/GPU/NPU measurements may guide a host-specific
choice, but no local model directory, compiled blob, or device is committed or
required by the core.

The model export, probe, and diagnostic scripts under `scripts/` are focused
maintainer tools. They do not form a launch gate or a second application.

## Voice posture

The package baseline is text-complete. `--voice` without a configured provider
returns explicit degradation. ASR/TTS libraries and model runtimes are
optional; separate HTTP voice/TTS services are retired.

## Host and evidence boundary

Windows 11 + PowerShell 7 remains the first product edge. Live hardware/model
evidence must name the provider, model revision or local artifact identity,
device, selected fallback, and trace. That evidence may prove one provider on
one host; it cannot promote the provider into core.

Large models, mutable caches, compile blobs, and benchmark output remain
outside Git. Follow the host storage policy before downloading or benchmarking
them.

## Archived tracks

Historical Qwen ASR/TTS conversion and rollback commands live in
`docs/ARCHIVED_TRACKS.md`. Their presence is recoverability evidence, not
current support.
