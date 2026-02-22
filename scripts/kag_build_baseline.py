from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kag import build_kag_graph
from src.rag.retrieval import load_docs


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-build")
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


def run_kag_build_baseline(
    *,
    docs_in: Path,
    max_entities_per_doc: int = 128,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    graph_json_path = run_dir / "kag_graph.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "kag_build_baseline",
        "status": "started",
        "request": {
            "docs_in": str(docs_in),
            "max_entities_per_doc": max_entities_per_doc,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "kag_graph_json": str(graph_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        docs = load_docs(docs_in)
        graph_payload = build_kag_graph(docs, max_entities_per_doc=max_entities_per_doc)
        _write_json(graph_json_path, graph_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = graph_payload["stats"]
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "graph_payload": graph_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "input_path_missing"
        elif isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_input"
        else:
            run_payload["error_code"] = "kag_build_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "graph_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build KAG baseline graph from JSONL docs.")
    parser.add_argument(
        "--in",
        dest="docs_in",
        type=Path,
        default=Path("data") / "ftbquests_norm" / "quests.jsonl",
        help="Path to JSONL file or directory with *.jsonl files.",
    )
    parser.add_argument("--max-entities-per-doc", type=int, default=128, help="Entity cap per document.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_kag_build_baseline(
        docs_in=args.docs_in,
        max_entities_per_doc=args.max_entities_per_doc,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[kag_build_baseline] run_dir: {run_dir}")
    print(f"[kag_build_baseline] run_json: {run_dir / 'run.json'}")
    print(f"[kag_build_baseline] kag_graph_json: {run_dir / 'kag_graph.json'}")
    if not result["ok"]:
        print(f"[kag_build_baseline] error: {result['run_payload']['error']}")
        return 2
    stats = result["graph_payload"]["stats"]
    print(
        "[kag_build_baseline] "
        f"doc_nodes={stats['doc_nodes']} "
        f"entity_nodes={stats['entity_nodes']} "
        f"mention_edges={stats['mention_edges']} "
        f"cooccurs_edges={stats['cooccurs_edges']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
