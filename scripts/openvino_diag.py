from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-openvino")
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


def _load_openvino() -> Any:
    import openvino as ov

    return ov


def _load_numpy() -> Any:
    import numpy as np

    return np


def _as_jsonable_output(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def run_openvino_diag(
    *,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
    ov_module: Any | None = None,
    np_module: Any | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    diag_json_path = run_dir / "openvino_diag_all_devices.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "openvino_diag",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "diag_json": str(diag_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        ov = _load_openvino() if ov_module is None else ov_module
        np = _load_numpy() if np_module is None else np_module

        core = ov.Core()
        devices = list(core.available_devices)

        param = ov.opset10.parameter([1, 3], ov.Type.f32, name="x")
        model = ov.Model([ov.opset10.abs(param)], [param], "diag_abs")

        checks: list[dict[str, Any]] = []
        for device in devices:
            item: dict[str, Any] = {
                "device": device,
                "compile_ok": False,
                "infer_ok": False,
                "error": None,
            }
            try:
                compiled = core.compile_model(model, device)
                item["compile_ok"] = True
                infer = compiled.create_infer_request()
                output = infer.infer({"x": np.array([[-1.0, 2.0, -3.0]], dtype=np.float32)})
                first_key = next(iter(output))
                item["infer_ok"] = True
                item["output"] = _as_jsonable_output(output[first_key])
            except Exception as exc:  # pragma: no cover - exercised in integration runs
                item["error"] = str(exc)
            checks.append(item)

        diag_payload = {
            "openvino_version": getattr(ov, "__version__", "unknown"),
            "available_devices": devices,
            "checks": checks,
        }
        _write_json(diag_json_path, diag_payload)

        run_payload["status"] = "ok"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "diag_payload": diag_payload,
            "ok": True,
        }
    except Exception as exc:
        diag_payload = {
            "openvino_version": None,
            "available_devices": [],
            "checks": [],
            "error": str(exc),
        }
        _write_json(diag_json_path, diag_payload)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "diag_payload": diag_payload,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenVINO diagnostics and write artifacts to runs/<timestamp>-openvino.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_openvino_diag(runs_dir=args.runs_dir)
    run_dir = result["run_dir"]
    diag_payload = result["diag_payload"]

    print(f"[openvino_diag] run_dir: {run_dir}")
    print(f"[openvino_diag] run_json: {run_dir / 'run.json'}")
    print(f"[openvino_diag] diag_json: {run_dir / 'openvino_diag_all_devices.json'}")
    print(f"[openvino_diag] available_devices: {diag_payload.get('available_devices', [])}")

    if result["ok"]:
        return 0

    print(f"[openvino_diag] error: {diag_payload.get('error', 'unknown error')}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
