from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-hud-ocr")
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


def _run_tesseract_ocr(
    *,
    image_path: Path,
    lang: str,
    psm: int,
    oem: int,
    timeout_sec: float,
    tesseract_bin: str,
) -> str:
    if psm < 0:
        raise ValueError("psm must be >= 0.")
    if oem < 0:
        raise ValueError("oem must be >= 0.")

    resolved_tesseract = shutil.which(tesseract_bin)
    if not resolved_tesseract:
        raise RuntimeError(
            f"Tesseract binary is not available: {tesseract_bin!r}. "
            "Install Tesseract OCR and ensure it is in PATH."
        )

    cmd = [
        resolved_tesseract,
        str(image_path),
        "stdout",
        "--psm",
        str(psm),
        "--oem",
        str(oem),
        "-l",
        lang,
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"Tesseract OCR failed with exit code {completed.returncode}: {stderr}")
    return completed.stdout


def run_hud_ocr_baseline(
    *,
    image_in: Path,
    lang: str = "eng",
    psm: int = 6,
    oem: int = 1,
    timeout_sec: float = 20.0,
    tesseract_bin: str = "tesseract",
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    ocr_json_path = run_dir / "ocr.json"
    ocr_text_path = run_dir / "ocr.txt"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "hud_ocr_baseline",
        "status": "started",
        "request": {
            "image_in": str(image_in),
            "lang": lang,
            "psm": psm,
            "oem": oem,
            "timeout_sec": timeout_sec,
            "tesseract_bin": tesseract_bin,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "ocr_json": str(ocr_json_path),
            "ocr_txt": str(ocr_text_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        if not image_in.exists():
            raise FileNotFoundError(f"Input image does not exist: {image_in}")
        if not image_in.is_file():
            raise ValueError(f"Input image path must be a file: {image_in}")

        raw_text = _run_tesseract_ocr(
            image_path=image_in,
            lang=lang,
            psm=psm,
            oem=oem,
            timeout_sec=timeout_sec,
            tesseract_bin=tesseract_bin,
        )
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        ocr_payload = {
            "image_path": str(image_in),
            "raw_text": raw_text,
            "lines": lines,
            "line_count": len(lines),
        }
        _write_json(ocr_json_path, ocr_payload)
        ocr_text_path.write_text(raw_text, encoding="utf-8")

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "line_count": len(lines),
            "text_preview": " ".join(lines[:3])[:160],
        }
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "ocr_payload": ocr_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "input_path_missing"
        elif isinstance(exc, RuntimeError) and "Tesseract binary is not available" in str(exc):
            run_payload["error_code"] = "runtime_missing_dependency"
        elif isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_request"
        else:
            run_payload["error_code"] = "hud_ocr_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "ocr_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HUD OCR baseline: image -> OCR artifacts via Tesseract CLI.")
    parser.add_argument("--image-in", type=Path, required=True, help="Input screenshot/image path.")
    parser.add_argument("--lang", type=str, default="eng", help="Tesseract language code (default: eng).")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode (default: 6).")
    parser.add_argument("--oem", type=int, default=1, help="Tesseract OCR engine mode (default: 1).")
    parser.add_argument("--timeout-sec", type=float, default=20.0, help="Tesseract process timeout (default: 20).")
    parser.add_argument("--tesseract-bin", type=str, default="tesseract", help="Tesseract binary name/path.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_hud_ocr_baseline(
        image_in=args.image_in,
        lang=args.lang,
        psm=args.psm,
        oem=args.oem,
        timeout_sec=args.timeout_sec,
        tesseract_bin=args.tesseract_bin,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[hud_ocr_baseline] run_dir: {run_dir}")
    print(f"[hud_ocr_baseline] run_json: {run_dir / 'run.json'}")
    print(f"[hud_ocr_baseline] ocr_json: {run_dir / 'ocr.json'}")
    print(f"[hud_ocr_baseline] ocr_txt: {run_dir / 'ocr.txt'}")
    if not result["ok"]:
        print(f"[hud_ocr_baseline] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
