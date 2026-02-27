from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "STREAMLIT_IA_V0.md"


def _read_doc() -> str:
    assert DOC_PATH.exists(), f"Expected IA doc to exist: {DOC_PATH}"
    return DOC_PATH.read_text(encoding="utf-8")


def test_streamlit_ia_doc_exists() -> None:
    assert DOC_PATH.exists()
    assert DOC_PATH.is_file()


def test_streamlit_ia_doc_has_required_sections() -> None:
    text = _read_doc()
    required_sections = [
        "## Goals / Non-goals",
        "## Personas & primary tasks",
        "## IA map",
        "## Screen specs (4 зоны)",
        "## Data contracts & field mapping",
        "## Error/empty/loading states",
        "## Operator flows (happy + failure)",
        "## Safe actions guardrails",
        "## M8.1 handoff checklist",
    ]
    for section in required_sections:
        assert section in text, f"Missing required section: {section}"


def test_streamlit_ia_doc_lists_required_ui_zones() -> None:
    text = _read_doc()
    required_zones = [
        "Stack Health",
        "Run Explorer",
        "Latest Metrics",
        "Safe Actions",
    ]
    for zone in required_zones:
        assert zone in text, f"Missing required UI zone: {zone}"


def test_streamlit_ia_doc_lists_canonical_sources() -> None:
    text = _read_doc()
    required_sources = [
        "runs/ci-smoke-phase-a/smoke_summary.json",
        "runs/ci-smoke-retrieve/smoke_summary.json",
        "runs/ci-smoke-eval/smoke_summary.json",
        "runs/ci-smoke-gateway-core/gateway_smoke_summary.json",
        "runs/ci-smoke-gateway-automation/gateway_smoke_summary.json",
        "runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json",
        "runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json",
    ]
    for source in required_sources:
        assert source in text, f"Missing required canonical source: {source}"


def test_streamlit_ia_doc_mentions_gateway_dependencies() -> None:
    text = _read_doc()
    assert "GET /healthz" in text
    assert "POST /v1/gateway" in text
