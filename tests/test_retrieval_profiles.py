from __future__ import annotations

import pytest

from src.rag.retrieval_profiles import list_profile_names, resolve_profile


def test_resolve_profile_returns_ov_production_defaults() -> None:
    profile = resolve_profile("ov_production")
    assert profile.name == "ov_production"
    assert profile.topk == 5
    assert profile.candidate_k == 50
    assert profile.reranker == "qwen3"
    assert profile.reranker_model == "OpenVINO/Qwen3-Reranker-0.6B-fp16-ov"
    assert profile.reranker_runtime == "openvino"
    assert profile.reranker_device == "AUTO"
    assert profile.embedding_model == "OpenVINO/Qwen3-Embedding-0.6B-int8-ov"


def test_resolve_profile_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError):
        resolve_profile("unknown_profile")


def test_list_profile_names_contains_baseline_and_ov_production() -> None:
    names = set(list_profile_names())
    assert "baseline" in names
    assert "ov_production" in names
