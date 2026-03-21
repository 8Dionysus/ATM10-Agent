from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

_POLICIES: tuple[str, ...] = ("report_only", "fail_if_blocked")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-manual-preflight")
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


def _parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


ApiGetter = Callable[[str, Mapping[str, str]], Mapping[str, Any]]


def _default_api_getter(url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
    request = urllib.request.Request(url=url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(f"github api request failed ({exc.code}): {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"github api request failed: {exc.reason}") from exc

    if not isinstance(payload, Mapping):
        raise RuntimeError("github api response root must be JSON object")
    return payload


def _build_headers(*, token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "atm10-agent/gateway-sla-manual-preflight",
    }


def _build_workflow_runs_url(*, repo: str, workflow: str, branch: str, event: str, per_page: int) -> str:
    encoded_workflow = urllib.parse.quote(workflow, safe="")
    params = urllib.parse.urlencode(
        {
            "branch": branch,
            "event": event,
            "per_page": str(per_page),
        }
    )
    return f"https://api.github.com/repos/{repo}/actions/workflows/{encoded_workflow}/runs?{params}"


def _normalize_run_row(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at_raw = row.get("created_at")
    created_at = _parse_iso_datetime(created_at_raw)
    return {
        "run_id": row.get("id"),
        "run_number": row.get("run_number"),
        "run_url": row.get("html_url"),
        "created_at_utc": created_at.isoformat(),
        "event": row.get("event"),
        "head_branch": row.get("head_branch"),
        "status": row.get("status"),
        "conclusion": row.get("conclusion"),
        "created_at_epoch": created_at.timestamp(),
    }


def run_gateway_sla_manual_preflight(
    *,
    repo: str,
    workflow: str = "gateway-sla-readiness-nightly.yml",
    branch: str = "master",
    event: str = "workflow_dispatch",
    max_runs_per_utc_day: int = 1,
    per_page: int = 100,
    token_env: str = "GITHUB_TOKEN",
    policy: str = "report_only",
    runs_dir: Path = Path("runs") / "nightly-gateway-sla-preflight",
    summary_json: Path | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    api_getter: ApiGetter | None = None,
) -> dict[str, Any]:
    if "/" not in repo or repo.count("/") != 1:
        raise ValueError("repo must be in owner/name format.")
    if max_runs_per_utc_day <= 0:
        raise ValueError("max_runs_per_utc_day must be > 0.")
    if per_page <= 0:
        raise ValueError("per_page must be > 0.")
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")

    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    if env is None:
        env = os.environ
    if api_getter is None:
        api_getter = _default_api_getter

    run_dir = _create_run_dir(Path(runs_dir), now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (Path(runs_dir) / "preflight_summary.json")

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_manual_preflight",
        "status": "started",
        "params": {
            "repo": repo,
            "workflow": workflow,
            "branch": branch,
            "event": event,
            "max_runs_per_utc_day": max_runs_per_utc_day,
            "per_page": per_page,
            "token_source": "env",
            "policy": policy,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_out_path),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    today_utc = now.date()
    try:
        token = str(env.get(token_env, "")).strip()
        if not token:
            raise ValueError("missing GitHub token in configured environment variable")

        headers = _build_headers(token=token)
        url = _build_workflow_runs_url(
            repo=repo,
            workflow=workflow,
            branch=branch,
            event=event,
            per_page=per_page,
        )
        response = api_getter(url, headers)
        raw_runs = response.get("workflow_runs")
        if not isinstance(raw_runs, list):
            raise ValueError("github api response missing workflow_runs list")

        normalized_runs: list[dict[str, Any]] = []
        for raw in raw_runs:
            if not isinstance(raw, Mapping):
                warnings.append("skipped non-object workflow_run entry")
                continue
            try:
                normalized = _normalize_run_row(raw)
            except Exception as exc:
                warnings.append(f"skipped workflow_run with invalid created_at: {exc}")
                continue

            if normalized["event"] != event:
                continue
            if normalized["head_branch"] != branch:
                continue
            normalized_runs.append(normalized)

        normalized_runs.sort(
            key=lambda item: (
                float(item["created_at_epoch"]),
                int(item["run_id"]) if isinstance(item.get("run_id"), int) else 0,
            )
        )

        today_runs = [
            item
            for item in normalized_runs
            if _parse_iso_datetime(item["created_at_utc"]).date() == today_utc
        ]
        today_count = len(today_runs)
        latest_run = normalized_runs[-1] if normalized_runs else None

        accounted_dispatch_allowed = today_count < max_runs_per_utc_day
        reason_codes = [] if accounted_dispatch_allowed else ["utc_day_quota_exhausted"]
        decision_status = "allow_accounted_dispatch" if accounted_dispatch_allowed else "block_accounted_dispatch"
        next_accounted_dispatch_at = None
        if not accounted_dispatch_allowed:
            next_day = today_utc + timedelta(days=1)
            next_accounted_dispatch_at = datetime(
                year=next_day.year,
                month=next_day.month,
                day=next_day.day,
                tzinfo=timezone.utc,
            ).isoformat()

        exit_code = 0
        if policy == "fail_if_blocked" and not accounted_dispatch_allowed:
            exit_code = 2

        summary_payload: dict[str, Any] = {
            "schema_version": "gateway_sla_manual_preflight_v1",
            "status": "ok",
            "checked_at_utc": _utc_now(),
            "utc_date": today_utc.isoformat(),
            "policy": policy,
            "inputs": {
                "repo": repo,
                "workflow": workflow,
                "branch": branch,
                "event": event,
                "max_runs_per_utc_day": max_runs_per_utc_day,
                "per_page": per_page,
                "token_source": "env",
            },
            "observed": {
                "workflow_runs_observed": len(normalized_runs),
                "today_dispatch_count": today_count,
                "latest_dispatch_run": latest_run,
            },
            "decision": {
                "accounted_dispatch_allowed": accounted_dispatch_allowed,
                "decision_status": decision_status,
                "next_accounted_dispatch_at_utc": next_accounted_dispatch_at,
                "reason_codes": reason_codes,
            },
            "warnings": warnings,
            "error": None,
            "exit_code": exit_code,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
            },
        }
        _write_json(summary_out_path, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "decision_status": decision_status,
            "accounted_dispatch_allowed": accounted_dispatch_allowed,
            "today_dispatch_count": today_count,
            "next_accounted_dispatch_at_utc": next_accounted_dispatch_at,
            "exit_code": exit_code,
            "warnings_count": len(warnings),
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
        }
    except (ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        summary_payload = {
            "schema_version": "gateway_sla_manual_preflight_v1",
            "status": "error",
            "checked_at_utc": _utc_now(),
            "utc_date": today_utc.isoformat(),
            "policy": policy,
            "inputs": {
                "repo": repo,
                "workflow": workflow,
                "branch": branch,
                "event": event,
                "max_runs_per_utc_day": max_runs_per_utc_day,
                "per_page": per_page,
                "token_source": "env",
            },
            "observed": {
                "workflow_runs_observed": 0,
                "today_dispatch_count": 0,
                "latest_dispatch_run": None,
            },
            "decision": {
                "accounted_dispatch_allowed": False,
                "decision_status": "error",
                "next_accounted_dispatch_at_utc": None,
                "reason_codes": ["preflight_evaluation_failed"],
            },
            "warnings": warnings,
            "error": str(exc),
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
            },
        }
        _write_json(summary_out_path, summary_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_manual_preflight_failed"
        run_payload["error"] = str(exc)
        run_payload["result"] = {"exit_code": 2}
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "exit_code": 2,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check UTC calendar-day guardrail before manual nightly dispatch.")
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository in owner/name format.",
    )
    parser.add_argument(
        "--workflow",
        default="gateway-sla-readiness-nightly.yml",
        help="Workflow file name under .github/workflows.",
    )
    parser.add_argument(
        "--branch",
        default="master",
        help="Target branch for dispatch runs.",
    )
    parser.add_argument(
        "--event",
        default="workflow_dispatch",
        help="GitHub Actions event type for run filtering.",
    )
    parser.add_argument(
        "--max-runs-per-utc-day",
        type=int,
        default=1,
        help="Maximum accounted dispatch runs per UTC day.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Workflow runs page size for GitHub API call.",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable name with GitHub token.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_if_blocked.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-preflight",
        help="Run artifact base directory.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_manual_preflight_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_manual_preflight(
        repo=args.repo,
        workflow=args.workflow,
        branch=args.branch,
        event=args.event,
        max_runs_per_utc_day=args.max_runs_per_utc_day,
        per_page=args.per_page,
        token_env=args.token_env,
        policy=args.policy,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_manual_preflight] run_dir: {result['run_dir']}")
    print(
        "[check_gateway_sla_manual_preflight] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(
        "[check_gateway_sla_manual_preflight] "
        f"decision_status: {summary_payload['decision']['decision_status']}"
    )
    print(
        "[check_gateway_sla_manual_preflight] "
        f"accounted_dispatch_allowed: {summary_payload['decision']['accounted_dispatch_allowed']}"
    )
    print(f"[check_gateway_sla_manual_preflight] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
