from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(rel_path: str) -> ModuleType:
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bringup_contract_cli_fails_when_readiness_has_blocker(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script(".agents/skills/aoa-local-stack-bringup/scripts/bringup_contract.py")
    payload = dict(script.TEMPLATE)
    payload["readiness_items"] = [{"severity": "fail", "label": "db unavailable"}]
    monkeypatch.setattr(sys, "argv", ["bringup_contract.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert script.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "hold"
    assert result["blocker_count"] == 1


def test_infra_change_contract_cli_fails_on_confirm_or_hold(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script(".agents/skills/aoa-safe-infra-change/scripts/infra_change_contract.py")
    payload = dict(script.TEMPLATE)
    payload["authority_state"] = "planned"
    payload["touched_surfaces"] = ["secrets/oauth.tfvars"]
    monkeypatch.setattr(sys, "argv", ["infra_change_contract.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert script.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["report_state"] == "confirm-or-hold"


def test_preview_gap_check_reports_non_object_preview_steps() -> None:
    script = _load_script(".agents/skills/aoa-dry-run-first/scripts/preview_gap_check.py")

    result = script.check_gaps(
        {
            "preview_steps": ["terraform plan"],
            "apply_step": {"command": "terraform apply"},
            "limitations": ["manual approval required"],
        }
    )

    assert result["status"] == "fail"
    assert "preview-step-not-object" in result["gaps"]


def test_aoa_summon_skill_uses_canonical_transport_and_lane_ids() -> None:
    text = (REPO_ROOT / ".agents/skills/aoa-summon/SKILL.md").read_text(encoding="utf-8")

    assert "default `transport_preference` to `codex_local`" in text
    assert "`codex_local_leaf`" in text
    assert "`codex_local_reviewed`" in text
    assert "optional `codex_local_target`" in text
