from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.ops_policy import (
    GATEWAY_SLA_PROFILE,
    MAX_WARN_RATIO,
    READINESS_WINDOW,
    REQUIRED_BASELINE_COUNT,
    REQUIRED_READY_STREAK,
)

_POLICIES: tuple[str, ...] = ("report_only", "fail_on_step_error")
_STEP_NAMES: tuple[str, ...] = (
    "gateway_v1_http_smoke_core",
    "check_gateway_sla",
    "gateway_sla_trend_snapshot_signal_only",
    "check_gateway_sla_fail_nightly_readiness",
    "check_gateway_sla_fail_nightly_governance",
    "check_gateway_sla_fail_nightly_progress",
    "check_gateway_sla_fail_nightly_transition",
)


@dataclass(frozen=True)
class _Step:
    name: str
    command: list[str]
    summary_json: Path | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-bootstrap")
    run_dir = runs_dir / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_dir / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing file: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"failed to parse JSON {path}: {exc}"
    if not isinstance(payload, dict):
        return None, f"json root must be object: {path}"
    return payload, None


def _run_command(
    *,
    command: Sequence[str],
    cwd: Path,
    command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] | None,
) -> subprocess.CompletedProcess[str]:
    if command_runner is not None:
        return command_runner(list(command), cwd)
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _build_chain_steps(base_runs_dir: Path) -> list[_Step]:
    nightly_http_core = base_runs_dir / "nightly-gateway-http-core"
    nightly_sla_history = base_runs_dir / "nightly-gateway-sla-history"
    nightly_sla_trend_history = base_runs_dir / "nightly-gateway-sla-trend-history"
    nightly_readiness = base_runs_dir / "nightly-gateway-sla-readiness"
    nightly_governance = base_runs_dir / "nightly-gateway-sla-governance"
    nightly_progress = base_runs_dir / "nightly-gateway-sla-progress"
    nightly_transition = base_runs_dir / "nightly-gateway-sla-transition"

    http_summary = nightly_http_core / "gateway_http_smoke_summary.json"
    sla_summary = nightly_sla_history / "gateway_sla_summary.json"
    readiness_summary = nightly_readiness / "readiness_summary.json"
    governance_summary = nightly_governance / "governance_summary.json"
    progress_summary = nightly_progress / "progress_summary.json"
    transition_summary = nightly_transition / "transition_summary.json"

    return [
        _Step(
            name="gateway_v1_http_smoke_core",
            command=[
                sys.executable,
                "scripts/gateway_v1_http_smoke.py",
                "--scenario",
                "core",
                "--runs-dir",
                str(nightly_http_core),
                "--summary-json",
                str(http_summary),
            ],
            summary_json=http_summary,
        ),
        _Step(
            name="check_gateway_sla",
            command=[
                sys.executable,
                "scripts/check_gateway_sla.py",
                "--http-summary-json",
                str(http_summary),
                "--summary-json",
                str(sla_summary),
                "--profile",
                GATEWAY_SLA_PROFILE,
                "--policy",
                "signal_only",
                "--runs-dir",
                str(nightly_sla_history),
            ],
            summary_json=sla_summary,
        ),
        _Step(
            name="gateway_sla_trend_snapshot_signal_only",
            command=[
                sys.executable,
                "scripts/gateway_sla_trend_snapshot.py",
                "--sla-runs-dir",
                str(nightly_sla_history),
                "--history-limit",
                "30",
                "--baseline-window",
                "5",
                "--critical-policy",
                "signal_only",
                "--runs-dir",
                str(nightly_sla_trend_history),
            ],
            summary_json=None,
        ),
        _Step(
            name="check_gateway_sla_fail_nightly_readiness",
            command=[
                sys.executable,
                "scripts/check_gateway_sla_fail_nightly_readiness.py",
                "--trend-runs-dir",
                str(nightly_sla_trend_history),
                "--history-limit",
                "30",
                "--readiness-window",
                str(READINESS_WINDOW),
                "--required-baseline-count",
                str(REQUIRED_BASELINE_COUNT),
                "--max-warn-ratio",
                str(MAX_WARN_RATIO),
                "--policy",
                "report_only",
                "--runs-dir",
                str(nightly_readiness),
                "--summary-json",
                str(readiness_summary),
            ],
            summary_json=readiness_summary,
        ),
        _Step(
            name="check_gateway_sla_fail_nightly_governance",
            command=[
                sys.executable,
                "scripts/check_gateway_sla_fail_nightly_governance.py",
                "--readiness-runs-dir",
                str(nightly_readiness),
                "--history-limit",
                "60",
                "--required-ready-streak",
                str(REQUIRED_READY_STREAK),
                "--expected-readiness-window",
                str(READINESS_WINDOW),
                "--expected-required-baseline-count",
                str(REQUIRED_BASELINE_COUNT),
                "--expected-max-warn-ratio",
                str(MAX_WARN_RATIO),
                "--policy",
                "report_only",
                "--runs-dir",
                str(nightly_governance),
                "--summary-json",
                str(governance_summary),
            ],
            summary_json=governance_summary,
        ),
        _Step(
            name="check_gateway_sla_fail_nightly_progress",
            command=[
                sys.executable,
                "scripts/check_gateway_sla_fail_nightly_progress.py",
                "--readiness-runs-dir",
                str(nightly_readiness),
                "--governance-runs-dir",
                str(nightly_governance),
                "--readiness-history-limit",
                "60",
                "--governance-history-limit",
                "60",
                "--expected-readiness-window",
                str(READINESS_WINDOW),
                "--expected-required-baseline-count",
                str(REQUIRED_BASELINE_COUNT),
                "--expected-max-warn-ratio",
                str(MAX_WARN_RATIO),
                "--required-ready-streak",
                str(REQUIRED_READY_STREAK),
                "--policy",
                "report_only",
                "--runs-dir",
                str(nightly_progress),
                "--summary-json",
                str(progress_summary),
            ],
            summary_json=progress_summary,
        ),
        _Step(
            name="check_gateway_sla_fail_nightly_transition",
            command=[
                sys.executable,
                "scripts/check_gateway_sla_fail_nightly_transition.py",
                "--readiness-runs-dir",
                str(nightly_readiness),
                "--governance-runs-dir",
                str(nightly_governance),
                "--progress-runs-dir",
                str(nightly_progress),
                "--readiness-history-limit",
                "60",
                "--governance-history-limit",
                "60",
                "--progress-history-limit",
                "60",
                "--expected-readiness-window",
                str(READINESS_WINDOW),
                "--expected-required-baseline-count",
                str(REQUIRED_BASELINE_COUNT),
                "--expected-max-warn-ratio",
                str(MAX_WARN_RATIO),
                "--required-ready-streak",
                str(REQUIRED_READY_STREAK),
                "--policy",
                "report_only",
                "--runs-dir",
                str(nightly_transition),
                "--summary-json",
                str(transition_summary),
            ],
            summary_json=transition_summary,
        ),
    ]


def _build_latest_snapshot(base_runs_dir: Path) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    source_map = {
        "readiness": base_runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": base_runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": base_runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": base_runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
    }

    payloads: dict[str, dict[str, Any]] = {}
    for source, path in source_map.items():
        payload, error = _read_json_object(path)
        if payload is None:
            warnings.append(f"{source}: {error}")
            continue
        payloads[source] = payload

    latest = {
        "readiness": {
            "status": payloads.get("readiness", {}).get("status"),
            "readiness_status": payloads.get("readiness", {}).get("readiness_status"),
        },
        "governance": {
            "status": payloads.get("governance", {}).get("status"),
            "decision_status": payloads.get("governance", {}).get("decision_status"),
        },
        "progress": {
            "status": payloads.get("progress", {}).get("status"),
            "decision_status": payloads.get("progress", {}).get("decision_status"),
            "remaining_for_window": payloads.get("progress", {})
            .get("observed", {})
            .get("readiness", {})
            .get("remaining_for_window"),
            "remaining_for_streak": payloads.get("progress", {})
            .get("observed", {})
            .get("readiness", {})
            .get("remaining_for_streak"),
        },
        "transition": {
            "status": payloads.get("transition", {}).get("status"),
            "decision_status": payloads.get("transition", {}).get("decision_status"),
            "allow_switch": payloads.get("transition", {}).get("allow_switch"),
        },
        "paths": {key: str(path) for key, path in source_map.items()},
    }

    decision = {
        "allow_switch": payloads.get("transition", {}).get("allow_switch"),
        "target_critical_policy": payloads.get("transition", {})
        .get("recommendation", {})
        .get("target_critical_policy"),
        "reason_codes": payloads.get("transition", {}).get("recommendation", {}).get("reason_codes"),
    }
    return {"latest": latest, "decision": decision}, warnings


def _render_summary_markdown(summary_payload: Mapping[str, Any]) -> str:
    lines = [
        "# Gateway SLA Bootstrap Summary",
        "",
        f"- `status`: {summary_payload.get('status')}",
        f"- `iterations`: {summary_payload.get('iterations')}",
        f"- `started_at_utc`: {summary_payload.get('started_at_utc')}",
        f"- `finished_at_utc`: {summary_payload.get('finished_at_utc')}",
        f"- `exit_code`: {summary_payload.get('exit_code')}",
        "",
        "## Decision",
        "",
        f"- `allow_switch`: {summary_payload.get('decision', {}).get('allow_switch')}",
        f"- `target_critical_policy`: {summary_payload.get('decision', {}).get('target_critical_policy')}",
        f"- `reason_codes`: {summary_payload.get('decision', {}).get('reason_codes')}",
        "",
        "## Steps",
        "",
        "| iteration | step | exit_code | summary_json |",
        "|---|---|---:|---|",
    ]
    for step in summary_payload.get("steps", []):
        lines.append(
            f"| {step.get('iteration')} | {step.get('step')} | {step.get('exit_code')} | {step.get('summary_json')} |"
        )
    return "\n".join(lines) + "\n"


def run_bootstrap_gateway_sla_nightly_history(
    *,
    iterations: int = 3,
    runs_dir: Path = Path("runs"),
    policy: str = "report_only",
    strict_stop: bool = False,
    now: datetime | None = None,
    command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    if iterations <= 0:
        raise ValueError("iterations must be > 0.")
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")
    if now is None:
        now = datetime.now(timezone.utc)

    base_runs_dir = Path(runs_dir)
    bootstrap_runs_dir = base_runs_dir / "nightly-gateway-sla-bootstrap"
    run_dir = _create_run_dir(bootstrap_runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    summary_json_path = run_dir / "bootstrap_summary.json"
    summary_md_path = run_dir / "summary.md"
    started_at_utc = _utc_now()

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_sla_nightly_bootstrap",
        "status": "started",
        "params": {
            "iterations": iterations,
            "runs_dir": str(base_runs_dir),
            "policy": policy,
            "strict_stop": strict_stop,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    had_step_error = False
    stopped_early = False
    interrupted_iteration: int | None = None
    interrupted_step: str | None = None

    chain_steps = _build_chain_steps(base_runs_dir)
    assert tuple(step.name for step in chain_steps) == _STEP_NAMES

    for iteration in range(1, iterations + 1):
        for step in chain_steps:
            started_perf = time.perf_counter()
            completed = _run_command(command=step.command, cwd=REPO_ROOT, command_runner=command_runner)
            duration_ms = round((time.perf_counter() - started_perf) * 1000.0, 3)
            record = {
                "iteration": iteration,
                "step": step.name,
                "command": step.command,
                "exit_code": int(completed.returncode),
                "duration_ms": duration_ms,
                "ok": completed.returncode == 0,
                "summary_json": None if step.summary_json is None else str(step.summary_json),
                "summary_paths": {}
                if step.summary_json is None
                else {"summary_json": str(step.summary_json)},
            }
            steps.append(record)
            if completed.returncode != 0:
                had_step_error = True
                warnings.append(
                    f"iteration={iteration}, step={step.name}, exit_code={completed.returncode}"
                )
                if strict_stop:
                    stopped_early = True
                    interrupted_iteration = iteration
                    interrupted_step = step.name
                    break
        if stopped_early:
            break

    latest_bundle, snapshot_warnings = _build_latest_snapshot(base_runs_dir)
    warnings.extend(snapshot_warnings)

    status = "ok" if not had_step_error else "error"
    exit_code = 0
    if strict_stop and had_step_error:
        exit_code = 2
    elif had_step_error and policy == "fail_on_step_error":
        exit_code = 2

    summary_payload: dict[str, Any] = {
        "schema_version": "gateway_sla_bootstrap_summary_v1",
        "status": status,
        "iterations": iterations,
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "policy": policy,
        "strict_stop": strict_stop,
        "steps": steps,
        "latest": latest_bundle["latest"],
        "decision": latest_bundle["decision"],
        "warnings": warnings,
        "execution": {
            "had_step_error": had_step_error,
            "stopped_early": stopped_early,
            "interrupted_iteration": interrupted_iteration,
            "interrupted_step": interrupted_step,
        },
        "exit_code": exit_code,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
            "base_runs_dir": str(base_runs_dir),
        },
    }
    _write_json(summary_json_path, summary_payload)
    summary_md_path.write_text(_render_summary_markdown(summary_payload), encoding="utf-8")

    run_payload["status"] = summary_payload["status"]
    run_payload["result"] = {
        "exit_code": exit_code,
        "had_step_error": had_step_error,
        "stopped_early": stopped_early,
        "allow_switch": summary_payload["decision"]["allow_switch"],
        "target_critical_policy": summary_payload["decision"]["target_critical_policy"],
    }
    _write_json(run_json_path, run_payload)

    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "run_dir": run_dir,
        "run_payload": run_payload,
        "summary_payload": summary_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap local nightly gateway SLA history (readiness/governance/progress/transition chain)."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of full G2 chain iterations (default: 3).",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base runs directory (default: runs).",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_on_step_error.",
    )
    parser.add_argument(
        "--strict-stop",
        action="store_true",
        help="Stop immediately on first failed step and return exit_code=2.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_bootstrap_gateway_sla_nightly_history(
        iterations=args.iterations,
        runs_dir=args.runs_dir,
        policy=args.policy,
        strict_stop=bool(args.strict_stop),
    )
    summary = result["summary_payload"]
    print(f"[bootstrap_gateway_sla_nightly_history] run_dir: {result['run_dir']}")
    print(
        "[bootstrap_gateway_sla_nightly_history] "
        f"summary_json: {summary['paths']['summary_json']}"
    )
    print(
        "[bootstrap_gateway_sla_nightly_history] "
        f"summary_md: {summary['paths']['summary_md']}"
    )
    print(f"[bootstrap_gateway_sla_nightly_history] status: {summary['status']}")
    print(
        "[bootstrap_gateway_sla_nightly_history] "
        f"allow_switch={summary['decision']['allow_switch']}, "
        f"target_critical_policy={summary['decision']['target_critical_policy']}"
    )
    print(f"[bootstrap_gateway_sla_nightly_history] exit_code: {summary['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
