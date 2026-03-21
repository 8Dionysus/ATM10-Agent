from __future__ import annotations

from pathlib import Path


_EXPECTED_PINS = {
    "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-python": "a309ff8b426b58ec0e2a45f0f869d46889d02405",
    "actions/cache/restore": "668228422ae6a00e4ad889ee87cd7109ec5666a7",
    "actions/cache/save": "668228422ae6a00e4ad889ee87cd7109ec5666a7",
    "actions/upload-artifact": "bbbca2ddaa5d8feaa63e36b76fdaad77386f024f",
}

_DEPRECATED_PINS = {
    "11bd71901bbe5b1630ceea73d27597364c9af683",
    "a26af69be951a213d495a4c3e4e4022e16d87065",
    "0400d5f644dc74513175e3cd8d07132dd4860809",
    "ea165f8d65b6e75b540449e92b4886f43607fa02",
}


def test_github_workflows_pin_node24_compatible_action_shas() -> None:
    workflow_paths = sorted(Path(".github/workflows").glob("*.yml"))
    assert workflow_paths, "expected workflow files under .github/workflows"

    texts = [path.read_text(encoding="utf-8") for path in workflow_paths]
    combined = "\n".join(texts)

    for action, sha in _EXPECTED_PINS.items():
        expected_line = f"uses: {action}@{sha}"
        if action.startswith("actions/cache/"):
            assert expected_line in combined
        else:
            assert expected_line in combined, f"missing updated pin for {action}"

    for sha in _DEPRECATED_PINS:
        assert sha not in combined, f"deprecated action pin still present: {sha}"
