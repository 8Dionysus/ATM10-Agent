from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as url_error
from urllib import request

try:  # pragma: no cover - import presence is validated via runtime/smoke
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


REPO_ROOT = Path(__file__).resolve().parents[1]

TAB_NAMES = (
    "Stack Health",
    "Run Explorer",
    "Latest Metrics",
    "Safe Actions",
)

SAFE_ACTIONS: dict[str, dict[str, str]] = {
    "gateway_local_core": {
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "core",
        "runs_subdir": "ui-safe-gateway-core",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_local_automation": {
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "automation",
        "runs_subdir": "ui-safe-gateway-automation",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_http_core": {
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "core",
        "runs_subdir": "ui-safe-gateway-http-core",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "gateway_http_automation": {
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "automation",
        "runs_subdir": "ui-safe-gateway-http-automation",
        "summary_name": "gateway_http_smoke_summary.json",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_summary_sources(runs_dir: Path) -> dict[str, Path]:
    base = Path(runs_dir)
    return {
        "phase_a": base / "ci-smoke-phase-a" / "smoke_summary.json",
        "retrieve": base / "ci-smoke-retrieve" / "smoke_summary.json",
        "eval": base / "ci-smoke-eval" / "smoke_summary.json",
        "gateway_core": base / "ci-smoke-gateway-core" / "gateway_smoke_summary.json",
        "gateway_automation": base / "ci-smoke-gateway-automation" / "gateway_smoke_summary.json",
        "gateway_http_core": base
        / "ci-smoke-gateway-http-core"
        / "gateway_http_smoke_summary.json",
        "gateway_http_automation": base
        / "ci-smoke-gateway-http-automation"
        / "gateway_http_smoke_summary.json",
    }


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing file: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"failed to parse JSON {path}: {exc}"
    if not isinstance(payload, dict):
        return None, f"json root must be object: {path}"
    return payload, None


def fetch_gateway_health(gateway_url: str, timeout_sec: float) -> tuple[dict[str, Any] | None, str | None]:
    url = gateway_url.rstrip("/") + "/healthz"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except Exception as exc:
        return None, f"gateway health request failed: {exc}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway health JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway health payload must be object"
    return payload, None


def build_metrics_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_name, path in sources.items():
        payload, load_error = load_json_object(path)
        row: dict[str, Any] = {
            "source": source_name,
            "summary_json": str(path),
            "status": "missing" if payload is None else str(payload.get("status", "unknown")),
            "details": "-" if load_error is None else load_error,
            "request_count": None,
            "failed_requests_count": None,
            "query_count": None,
            "mean_mrr_at_k": None,
            "results_count": None,
        }
        if payload is not None:
            observed = payload.get("observed")
            if isinstance(observed, dict):
                row["results_count"] = observed.get("results_count")
                row["query_count"] = observed.get("query_count")
                row["mean_mrr_at_k"] = observed.get("mean_mrr_at_k")
            row["request_count"] = payload.get("request_count")
            row["failed_requests_count"] = payload.get("failed_requests_count")
        rows.append(row)
    return rows


def build_run_explorer_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_name, path in sources.items():
        payload, load_error = load_json_object(path)
        row: dict[str, Any] = {
            "source": source_name,
            "summary_json": str(path),
            "status": "missing" if payload is None else str(payload.get("status", "unknown")),
            "scenario": None,
            "run_dir": None,
            "run_json": None,
            "request_count": None,
            "failed_requests_count": None,
            "error": load_error,
        }
        if payload is not None:
            paths_payload = payload.get("paths")
            if isinstance(paths_payload, dict):
                row["run_dir"] = paths_payload.get("run_dir")
                row["run_json"] = paths_payload.get("run_json")
            row["scenario"] = payload.get("scenario")
            row["request_count"] = payload.get("request_count")
            row["failed_requests_count"] = payload.get("failed_requests_count")
        rows.append(row)
    return rows


def resolve_safe_action(action_key: str, runs_dir: Path) -> tuple[list[str], Path]:
    config = SAFE_ACTIONS.get(action_key)
    if config is None:
        raise ValueError(f"unsupported safe action: {action_key!r}")
    action_runs_dir = Path(runs_dir) / config["runs_subdir"]
    summary_path = action_runs_dir / config["summary_name"]
    command = [
        sys.executable,
        config["script"],
        "--scenario",
        config["scenario"],
        "--runs-dir",
        str(action_runs_dir),
        "--summary-json",
        str(summary_path),
    ]
    return command, summary_path


def run_safe_action(action_key: str, runs_dir: Path, *, timeout_sec: float = 300.0) -> dict[str, Any]:
    command, summary_path = resolve_safe_action(action_key, runs_dir)
    command_text = " ".join(command)
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "action_key": action_key,
            "command": command_text,
            "exit_code": 2,
            "status": "error",
            "ok": False,
            "summary_json": str(summary_path),
            "error": f"safe action timeout: {exc}",
            "stdout": "",
            "stderr": "",
        }
    summary_payload, load_error = load_json_object(summary_path)
    summary_status = None if summary_payload is None else str(summary_payload.get("status"))
    ok = completed.returncode == 0 and summary_status == "ok" and load_error is None
    return {
        "action_key": action_key,
        "command": command_text,
        "exit_code": int(completed.returncode),
        "status": "ok" if ok else "error",
        "ok": ok,
        "summary_json": str(summary_path),
        "summary_status": summary_status,
        "error": load_error,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_panel_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Streamlit operator panel v0.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument(
        "--gateway-url",
        default="http://127.0.0.1:8770",
        help="Gateway HTTP base URL (default: http://127.0.0.1:8770).",
    )
    parser.add_argument(
        "--gateway-timeout-sec",
        type=float,
        default=3.0,
        help="Gateway health timeout in seconds (default: 3.0).",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def _render_stack_health_tab(gateway_url: str, gateway_timeout_sec: float) -> None:
    health_payload, health_error = fetch_gateway_health(gateway_url, gateway_timeout_sec)
    if health_error is not None:
        st.error(health_error)
        return
    st.success("Gateway transport health loaded.")
    st.json(health_payload)
    policy = health_payload.get("policy") if isinstance(health_payload, dict) else None
    if isinstance(policy, dict):
        st.subheader("Gateway policy snapshot")
        st.json(policy)


def _render_run_explorer_tab(sources: dict[str, Path]) -> None:
    rows = build_run_explorer_rows(sources)
    st.dataframe(rows, use_container_width=True)
    st.subheader("Artifact paths")
    for row in rows:
        st.code(
            "\n".join(
                [
                    f"source={row['source']}",
                    f"summary_json={row['summary_json']}",
                    f"run_dir={row.get('run_dir')}",
                    f"run_json={row.get('run_json')}",
                ]
            )
        )


def _render_latest_metrics_tab(sources: dict[str, Path]) -> None:
    rows = build_metrics_rows(sources)
    st.dataframe(rows, use_container_width=True)


def _render_safe_actions_tab(runs_dir: Path) -> None:
    action_labels = {
        "Gateway local smoke core": "gateway_local_core",
        "Gateway local smoke automation": "gateway_local_automation",
        "Gateway HTTP smoke core": "gateway_http_core",
        "Gateway HTTP smoke automation": "gateway_http_automation",
    }
    selected_label = st.selectbox("Safe action", list(action_labels.keys()))
    action_runs_dir_raw = st.text_input("Action runs_dir", value=str(runs_dir))
    if st.button("Execute safe action"):
        selected_key = action_labels[selected_label]
        result = run_safe_action(selected_key, Path(action_runs_dir_raw))
        if result["ok"]:
            st.success("Safe action finished with status=ok.")
        else:
            st.error("Safe action finished with status=error.")
        st.json(result)


def render_panel(args: argparse.Namespace) -> None:
    if st is None:
        raise RuntimeError("streamlit is required. Install dependency and re-run.")

    st.set_page_config(page_title="ATM10 Operator Panel", layout="wide")
    st.title("ATM10 Operator Panel v0")

    if "runs_dir" not in st.session_state:
        st.session_state["runs_dir"] = str(args.runs_dir)
    if "gateway_url" not in st.session_state:
        st.session_state["gateway_url"] = args.gateway_url
    if "last_refreshed_utc" not in st.session_state:
        st.session_state["last_refreshed_utc"] = _utc_now()

    col1, col2, col3 = st.columns([2, 3, 1])
    with col1:
        runs_dir_raw = st.text_input("runs_dir", value=st.session_state["runs_dir"])
    with col2:
        gateway_url = st.text_input("gateway_url", value=st.session_state["gateway_url"])
    with col3:
        if st.button("Refresh"):
            st.session_state["last_refreshed_utc"] = _utc_now()

    st.session_state["runs_dir"] = runs_dir_raw
    st.session_state["gateway_url"] = gateway_url
    st.caption(f"last_refreshed_utc: {st.session_state['last_refreshed_utc']}")

    runs_dir = Path(st.session_state["runs_dir"])
    sources = canonical_summary_sources(runs_dir)
    tabs = st.tabs(list(TAB_NAMES))

    with tabs[0]:
        _render_stack_health_tab(gateway_url, args.gateway_timeout_sec)
    with tabs[1]:
        _render_run_explorer_tab(sources)
    with tabs[2]:
        _render_latest_metrics_tab(sources)
    with tabs[3]:
        _render_safe_actions_tab(runs_dir)


def main(argv: list[str] | None = None) -> int:
    args = parse_panel_args(argv)
    render_panel(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
