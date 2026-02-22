from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    topk: int
    candidate_k: int
    reranker: str
    reranker_model: str | None
    reranker_runtime: str | None
    reranker_device: str | None
    embedding_model: str | None


_PROFILES: dict[str, RetrievalProfile] = {
    "baseline": RetrievalProfile(
        name="baseline",
        topk=5,
        candidate_k=50,
        reranker="none",
        reranker_model=None,
        reranker_runtime=None,
        reranker_device=None,
        embedding_model=None,
    ),
    "ov_production": RetrievalProfile(
        name="ov_production",
        topk=5,
        candidate_k=50,
        reranker="qwen3",
        reranker_model="OpenVINO/Qwen3-Reranker-0.6B-fp16-ov",
        reranker_runtime="openvino",
        reranker_device="AUTO",
        embedding_model="OpenVINO/Qwen3-Embedding-0.6B-int8-ov",
    ),
}


def list_profile_names() -> tuple[str, ...]:
    return tuple(_PROFILES.keys())


def resolve_profile(name: str) -> RetrievalProfile:
    normalized = name.strip().lower()
    if normalized not in _PROFILES:
        supported = ", ".join(_PROFILES.keys())
        raise ValueError(f"Unsupported retrieval profile: {name!r}. Expected one of: {supported}.")
    return _PROFILES[normalized]
