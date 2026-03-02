from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scripts.gateway_artifact_policy as artifact_policy


def _set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


def test_redact_error_entry_masks_sensitive_keys_and_text() -> None:
    payload = {
        "error": "token=abcd1234 value leaked",
        "traceback": 'Authorization: Bearer verysecretvalue12345\n{"api_key":"abc-123"}',
        "request_context": {
            "operation": "health",
            "password": "super-secret",
            "nested": {"cookie": "session=abc", "safe": "ok"},
        },
    }

    redacted = artifact_policy.redact_error_entry(payload, enable_redaction=True)

    assert redacted["request_context"]["operation"] == "health"
    assert redacted["request_context"]["password"] == "[REDACTED]"
    assert redacted["request_context"]["nested"]["cookie"] == "[REDACTED]"
    assert "abcd1234" not in redacted["error"]
    assert "verysecretvalue12345" not in redacted["traceback"]
    assert '"api_key":"abc-123"' not in redacted["traceback"]
    assert "[REDACTED]" in redacted["traceback"]

    metadata = redacted["redaction"]
    assert metadata["checklist_version"] == "gateway_error_redaction_v1"
    assert metadata["applied"] is True
    assert "request_context.password" in metadata["fields_redacted"]
    assert "request_context.nested.cookie" in metadata["fields_redacted"]


def test_rotate_jsonl_respects_max_files(tmp_path: Path) -> None:
    log_path = tmp_path / "gateway_http_errors.jsonl"

    for index in range(8):
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"index": index, "blob": "x" * 80}) + "\n")
        artifact_policy.rotate_jsonl(log_path, max_bytes=64, max_files=3)

    log_path.write_text("{\"final\":true}\n", encoding="utf-8")
    files = sorted(path.name for path in tmp_path.glob("gateway_http_errors*.jsonl"))
    assert len(files) <= 3
    assert "gateway_http_errors.1.jsonl" in files
    assert "gateway_http_errors.2.jsonl" in files


def test_cleanup_old_gateway_artifacts_removes_expired_gateway_entries(tmp_path: Path) -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    old = now - timedelta(days=30)
    recent = now - timedelta(days=1)

    old_log = tmp_path / "gateway_http_errors.1.jsonl"
    old_log.write_text("{\"old\":true}\n", encoding="utf-8")
    recent_log = tmp_path / "gateway_http_errors.jsonl"
    recent_log.write_text("{\"recent\":true}\n", encoding="utf-8")
    old_gateway_dir = tmp_path / "20260101_010101-gateway-v1"
    old_gateway_dir.mkdir(parents=True)
    recent_gateway_dir = tmp_path / "20260228_010101-gateway-v1"
    recent_gateway_dir.mkdir(parents=True)
    unrelated_old_dir = tmp_path / "20260101_010101-phase-a-smoke"
    unrelated_old_dir.mkdir(parents=True)

    _set_mtime(old_log, old)
    _set_mtime(recent_log, recent)
    _set_mtime(old_gateway_dir, old)
    _set_mtime(recent_gateway_dir, recent)
    _set_mtime(unrelated_old_dir, old)

    summary = artifact_policy.cleanup_old_gateway_artifacts(tmp_path, retention_days=14, now=now)

    assert not old_log.exists()
    assert recent_log.exists()
    assert not old_gateway_dir.exists()
    assert recent_gateway_dir.exists()
    assert unrelated_old_dir.exists()
    assert summary["removed_files_count"] == 1
    assert summary["removed_dirs_count"] == 1
    assert summary["warnings"] == []


def test_cleanup_old_gateway_artifacts_keeps_running_on_delete_failure(
    tmp_path: Path, monkeypatch
) -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    old = now - timedelta(days=30)
    old_gateway_dir = tmp_path / "20260101_010101-gateway-v1"
    old_gateway_dir.mkdir(parents=True)
    _set_mtime(old_gateway_dir, old)

    def _boom(*args, **kwargs) -> None:
        raise OSError("simulated remove failure")

    monkeypatch.setattr(artifact_policy.shutil, "rmtree", _boom)
    summary = artifact_policy.cleanup_old_gateway_artifacts(tmp_path, retention_days=14, now=now)

    assert old_gateway_dir.exists()
    assert summary["removed_dirs_count"] == 0
    assert summary["warnings"]
    assert "simulated remove failure" in summary["warnings"][0]
