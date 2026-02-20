import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.openvino_diag import run_openvino_diag


class _FakeArray:
    def __init__(self, values: list[list[float]]) -> None:
        self._values = values

    def tolist(self) -> list[list[float]]:
        return self._values


class _FakeNumpy:
    float32 = "float32"

    @staticmethod
    def array(value: list[list[float]], dtype: str) -> list[list[float]]:
        assert dtype == _FakeNumpy.float32
        return value


class _FakeInferRequest:
    @staticmethod
    def infer(_: dict[str, list[list[float]]]) -> dict[str, _FakeArray]:
        return {"y": _FakeArray([[1.0, 2.0, 3.0]])}


class _FakeCompiledModel:
    @staticmethod
    def create_infer_request() -> _FakeInferRequest:
        return _FakeInferRequest()


class _FakeCore:
    available_devices = ["CPU", "GPU"]

    @staticmethod
    def compile_model(model: object, device: str) -> _FakeCompiledModel:
        assert model is not None
        assert device in {"CPU", "GPU"}
        return _FakeCompiledModel()


class _FakeType:
    f32 = "f32"


class _FakeOpset10:
    @staticmethod
    def parameter(shape: list[int], dtype: str, name: str) -> dict[str, object]:
        return {"shape": shape, "dtype": dtype, "name": name}

    @staticmethod
    def abs(node: dict[str, object]) -> dict[str, object]:
        return {"op": "abs", "input": node}


class _FakeOV:
    __version__ = "fake-ov"
    Core = _FakeCore
    Type = _FakeType
    opset10 = _FakeOpset10

    @staticmethod
    def Model(outputs: list[dict[str, object]], inputs: list[dict[str, object]], name: str) -> dict[str, object]:
        return {"name": name, "outputs": outputs, "inputs": inputs}


def test_openvino_diag_creates_run_and_diag_artifacts(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 20, 14, 30, 0, tzinfo=timezone.utc)

    result = run_openvino_diag(runs_dir=runs_dir, now=now, ov_module=_FakeOV, np_module=_FakeNumpy)
    run_dir = result["run_dir"]
    run_json_path = run_dir / "run.json"
    diag_json_path = run_dir / "openvino_diag_all_devices.json"

    assert result["ok"] is True
    assert run_dir.exists()
    assert run_json_path.exists()
    assert diag_json_path.exists()
    assert run_dir.name == "20260220_143000-openvino"

    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    diag_payload = json.loads(diag_json_path.read_text(encoding="utf-8"))

    assert run_payload["mode"] == "openvino_diag"
    assert run_payload["status"] == "ok"
    assert run_payload["paths"]["run_dir"] == str(run_dir)
    assert diag_payload["openvino_version"] == "fake-ov"
    assert diag_payload["available_devices"] == ["CPU", "GPU"]
    assert all(item["compile_ok"] for item in diag_payload["checks"])
    assert all(item["infer_ok"] for item in diag_payload["checks"])
