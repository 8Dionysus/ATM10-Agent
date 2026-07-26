from __future__ import annotations

from pathlib import Path


NESTED_AGENTS = [
    Path("src/AGENTS.md"),
    Path("src/atm10_agent/agent_core/AGENTS.md"),
    Path("src/atm10_agent/rag/AGENTS.md"),
    Path("src/atm10_agent/kag/AGENTS.md"),
    Path("src/atm10_agent/hybrid/AGENTS.md"),
    Path("tests/AGENTS.md"),
    Path("scripts/AGENTS.md"),
    Path("docs/decisions/AGENTS.md"),
]

DISALLOWED_LITERALS = [
    "".join(["neo4j", "pass"]),
    f"D:{chr(92)}atm10-agent",
    f"C:{chr(92)}Users{chr(92)}Admin",
    f"C:{chr(92)}path{chr(92)}to",
    '--service-token "' + "change" + '-me"',
]

REQUIRED_MARKERS = {
    Path("src/AGENTS.md"): [
        "src/atm10_agent/agent_core/AGENTS.md",
        "src/atm10_agent/rag/AGENTS.md",
        "src/atm10_agent/kag/AGENTS.md",
        "src/atm10_agent/hybrid/AGENTS.md",
    ],
    Path("src/atm10_agent/agent_core/AGENTS.md"): [
        "service_sla.py",
        "combo_a_profile.py",
    ],
    Path("src/atm10_agent/rag/AGENTS.md"): [
        "doc_contract.py",
        "ftbquests_ingest.py",
        "retrieval_profiles.py",
    ],
    Path("src/atm10_agent/kag/AGENTS.md"): [
        "baseline.py",
        "neo4j_backend.py",
        "NEO4J_PASSWORD",
    ],
    Path("src/atm10_agent/hybrid/AGENTS.md"): [
        "planner.py",
        "baseline_first",
        "combo_a",
    ],
    Path("tests/AGENTS.md"): [
        "tests/fixtures/",
        "python -m pytest",
        "test_nested_agents_docs.py",
    ],
    Path("scripts/AGENTS.md"): [
        "phase_a_smoke.py",
        "retrieve_demo.py",
        "maintainer-tool shell",
    ],
    Path("docs/decisions/AGENTS.md"): [
        "ATM10-D-####",
        "Companion layers",
        "Operator surfaces",
        "python -m scripts.generate_decision_indexes --check",
    ],
}


def test_nested_agents_docs_exist() -> None:
    for path in NESTED_AGENTS:
        assert path.is_file(), f"missing expected nested AGENTS file: {path}"


def test_nested_agents_docs_remain_public_safe() -> None:
    for path in NESTED_AGENTS:
        text = path.read_text(encoding="utf-8")
        assert "Read the root `AGENTS.md` first." in text
        assert "<repo-root>" in text
        for literal in DISALLOWED_LITERALS:
            assert literal not in text, f"disallowed public literal {literal!r} found in {path}"


def test_nested_agents_docs_are_grounded_in_local_surface() -> None:
    for path, markers in REQUIRED_MARKERS.items():
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker in text, f"expected marker {marker!r} missing from {path}"
