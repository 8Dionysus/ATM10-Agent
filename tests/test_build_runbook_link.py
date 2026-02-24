from __future__ import annotations

import sys

import pytest

import scripts.build_runbook_link as helper


def test_build_runbook_url_uses_github_env_when_available() -> None:
    url = helper.build_runbook_url(
        anchor="m68-troubleshooting-automation-smoke-contract-failures-ci",
        env={
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_REF_NAME": "feature-branch",
        },
    )
    assert (
        url
        == "https://github.com/org/repo/blob/feature-branch/docs/RUNBOOK.md"
        "#m68-troubleshooting-automation-smoke-contract-failures-ci"
    )


def test_build_runbook_url_falls_back_without_repo_env() -> None:
    url = helper.build_runbook_url(
        anchor="#m68-troubleshooting-automation-smoke-contract-failures-ci",
        env={},
    )
    assert url == "docs/RUNBOOK.md#m68-troubleshooting-automation-smoke-contract-failures-ci"


def test_build_runbook_url_defaults_ref_name_to_main() -> None:
    url = helper.build_runbook_url(
        anchor="m68-troubleshooting-automation-smoke-contract-failures-ci",
        env={
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "org/repo",
        },
    )
    assert (
        url
        == "https://github.com/org/repo/blob/main/docs/RUNBOOK.md"
        "#m68-troubleshooting-automation-smoke-contract-failures-ci"
    )


def test_build_runbook_link_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["build_runbook_link.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        helper.parse_args()
    assert exc.value.code == 0
