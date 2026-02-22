from __future__ import annotations

import base64
import json
import os
import wave
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np


DEFAULT_QWEN3_ASR_MODEL = "Qwen/Qwen3-ASR-0.6B"
DEFAULT_WHISPER_GENAI_MODEL_DIR = "models/whisper-large-v3-turbo-ov"
DEFAULT_QWEN3_TTS_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
DEFAULT_FAST_TTS_RUNTIME = "ovms"


class VoiceRuntimeUnavailableError(RuntimeError):
    """Raised when voice runtime dependency is not available in environment."""


def _extract_audio_wav_b64(payload: Any) -> str | None:
    if isinstance(payload, dict):
        direct = payload.get("audio_wav_b64")
        if isinstance(direct, str) and direct.strip():
            return direct
        result = payload.get("result")
        if isinstance(result, dict):
            nested = result.get("audio_wav_b64")
            if isinstance(nested, str) and nested.strip():
                return nested
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                nested_choice = first.get("audio_wav_b64")
                if isinstance(nested_choice, str) and nested_choice.strip():
                    return nested_choice
    return None


def synthesize_ovms_tts_to_wav(
    *,
    text: str,
    output_path: Path,
    endpoint_url: str | None = None,
    model_id: str | None = None,
    speaker: str | None = None,
    language: str = "Auto",
    instruct: str | None = None,
    timeout_sec: float = 20.0,
) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("text must be non-empty for fast fallback TTS.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_endpoint_url = endpoint_url or os.getenv("OVMS_TTS_URL")
    if not resolved_endpoint_url:
        raise VoiceRuntimeUnavailableError(
            "OVMS endpoint is required. Set OVMS_TTS_URL or pass endpoint_url."
        )
    resolved_model_id = model_id or os.getenv("OVMS_TTS_MODEL")
    payload: dict[str, Any] = {
        "text": text,
        "speaker": speaker,
        "language": language,
        "instruct": instruct,
    }
    if resolved_model_id:
        payload["model"] = resolved_model_id
    request = Request(
        url=resolved_endpoint_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise VoiceRuntimeUnavailableError(f"OVMS TTS HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", str(exc))
        raise VoiceRuntimeUnavailableError(f"OVMS TTS endpoint unreachable: {reason}") from exc
    except Exception as exc:
        raise VoiceRuntimeUnavailableError(f"OVMS TTS request failed: {exc}") from exc

    wav_b64 = _extract_audio_wav_b64(response_payload)
    if not wav_b64:
        raise RuntimeError("OVMS TTS response does not contain 'audio_wav_b64'.")
    try:
        wav_bytes = base64.b64decode(wav_b64, validate=True)
    except Exception as exc:
        raise RuntimeError("Invalid base64 audio payload from OVMS TTS response.") from exc
    output_path.write_bytes(wav_bytes)
    if output_path.stat().st_size == 0:
        raise RuntimeError(f"OVMS TTS produced empty output file: {output_path}")

    return {
        "runtime": DEFAULT_FAST_TTS_RUNTIME,
        "engine": "ovms",
        "endpoint_url": resolved_endpoint_url,
        "model_id": resolved_model_id,
        "speaker": speaker,
        "audio_out_wav": str(output_path),
    }


def _resolve_torch_dtype(dtype: str) -> Any:
    normalized = dtype.strip().lower()
    if normalized == "auto":
        return "auto"
    try:
        import torch
    except Exception as exc:  # pragma: no cover - environment specific
        raise VoiceRuntimeUnavailableError(
            "PyTorch is required to resolve explicit --dtype values. Install qwen-asr/qwen-tts dependencies first."
        ) from exc

    mapping = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    if normalized not in mapping:
        raise ValueError(f"Unsupported dtype: {dtype}. Use one of: auto|float16|bfloat16|float32.")
    return mapping[normalized]


def write_wav_pcm16(*, path: Path, waveform: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    clipped = np.clip(mono, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm16.tobytes())


def _chunk_waveform(*, waveform: np.ndarray, chunk_size_samples: int) -> Iterator[np.ndarray]:
    if chunk_size_samples <= 0:
        raise ValueError("chunk_size_samples must be > 0.")
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    for offset in range(0, int(mono.shape[0]), int(chunk_size_samples)):
        yield mono[offset : offset + int(chunk_size_samples)]


def _resolve_input_device_index(sd_module: Any) -> int:
    devices = sd_module.query_devices()
    default_device = sd_module.default.device
    default_input_index = None
    if isinstance(default_device, (list, tuple)) and default_device:
        default_input_index = default_device[0]
    elif isinstance(default_device, int):
        default_input_index = default_device

    if isinstance(default_input_index, int) and default_input_index >= 0:
        default_info = devices[default_input_index]
        if int(default_info.get("max_input_channels", 0)) > 0:
            return int(default_input_index)

    for index, item in enumerate(devices):
        if int(item.get("max_input_channels", 0)) > 0:
            return index
    raise RuntimeError("No audio input device with input channels is available.")


def record_audio_to_wav(
    *,
    output_path: Path,
    seconds: float,
    sample_rate: int = 16000,
) -> dict[str, Any]:
    if seconds <= 0:
        raise ValueError("seconds must be > 0 for recording.")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be > 0.")

    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "Recording requires sounddevice. Install dependency: sounddevice."
        ) from exc

    input_device_index = _resolve_input_device_index(sd)
    frame_count = int(round(seconds * sample_rate))
    if frame_count <= 0:
        raise ValueError("seconds * sample_rate must produce at least one frame.")

    audio = sd.rec(
        frame_count,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=input_device_index,
    )
    sd.wait()
    waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
    write_wav_pcm16(path=output_path, waveform=waveform, sample_rate=sample_rate)

    devices = sd.query_devices()
    device_name = str(devices[input_device_index].get("name", f"device_{input_device_index}"))
    return {
        "mode": "recorded_microphone",
        "input_device_index": int(input_device_index),
        "input_device_name": device_name,
        "sample_rate": int(sample_rate),
        "duration_sec": float(seconds),
        "num_samples": int(frame_count),
        "audio_path": str(output_path),
    }


def play_audio(*, waveform: np.ndarray, sample_rate: int) -> None:
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "Audio playback requires sounddevice. Install dependency: sounddevice."
        ) from exc
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    sd.play(mono, samplerate=int(sample_rate))
    sd.wait()


class QwenASRClient:
    def __init__(self, model: Any) -> None:
        self._model = model

    @classmethod
    def from_pretrained(
        cls,
        *,
        model_id: str = DEFAULT_QWEN3_ASR_MODEL,
        device_map: str = "auto",
        dtype: str = "auto",
        max_new_tokens: int = 512,
    ) -> "QwenASRClient":
        try:
            from qwen_asr import Qwen3ASRModel
        except Exception as exc:  # pragma: no cover - dependency presence
            raise VoiceRuntimeUnavailableError(
                "Qwen ASR runtime is not installed. Install dependency: qwen-asr."
            ) from exc

        model = Qwen3ASRModel.from_pretrained(
            model_id,
            trust_remote_code=True,
            device_map=device_map,
            dtype=_resolve_torch_dtype(dtype),
            max_new_tokens=max_new_tokens,
        )
        return cls(model=model)

    def transcribe_path(
        self,
        *,
        audio_path: Path,
        context: str = "",
        language: str | None = None,
    ) -> dict[str, Any]:
        language_arg: str | None = language if language and language.strip() else None
        outputs = self._model.transcribe(
            audio=[str(audio_path)],
            context=[context],
            language=None if language_arg is None else [language_arg],
        )
        if not outputs:
            return {"text": "", "language": ""}
        first = outputs[0]
        return {
            "text": str(getattr(first, "text", "")),
            "language": str(getattr(first, "language", "")),
        }


def _read_wav_mono_f32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        num_channels = int(wav_file.getnchannels())
        sample_width = int(wav_file.getsampwidth())
        sample_rate = int(wav_file.getframerate())
        num_frames = int(wav_file.getnframes())
        raw_bytes = wav_file.readframes(num_frames)

    if sample_width == 1:
        data_u8 = np.frombuffer(raw_bytes, dtype=np.uint8)
        data = ((data_u8.astype(np.float32) - 128.0) / 128.0).astype(np.float32)
    elif sample_width == 2:
        data_i16 = np.frombuffer(raw_bytes, dtype=np.int16)
        data = (data_i16.astype(np.float32) / 32768.0).astype(np.float32)
    elif sample_width == 4:
        data_i32 = np.frombuffer(raw_bytes, dtype=np.int32)
        data = (data_i32.astype(np.float32) / 2147483648.0).astype(np.float32)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes.")

    if num_channels > 1:
        if data.size % num_channels != 0:
            raise ValueError("Corrupted WAV payload: sample count is not divisible by channel count.")
        data = data.reshape(-1, num_channels).mean(axis=1).astype(np.float32)

    return np.clip(data, -1.0, 1.0), sample_rate


def _linear_resample(waveform: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return waveform.astype(np.float32, copy=False)
    if src_sr <= 0 or dst_sr <= 0:
        raise ValueError("Sample rates must be > 0 for resampling.")
    if waveform.size == 0:
        return np.zeros(0, dtype=np.float32)

    duration_sec = waveform.shape[0] / float(src_sr)
    target_size = max(1, int(round(duration_sec * float(dst_sr))))
    x_old = np.linspace(0.0, duration_sec, num=waveform.shape[0], endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, duration_sec, num=target_size, endpoint=False, dtype=np.float64)
    resampled = np.interp(x_new, x_old, waveform.astype(np.float64))
    return resampled.astype(np.float32)


def _load_audio_mono_16k(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".wav":
        wav, sr = _read_wav_mono_f32(path)
    else:
        try:
            import librosa  # pragma: no cover - optional dependency
        except Exception as exc:  # pragma: no cover - dependency presence
            raise VoiceRuntimeUnavailableError(
                "Non-WAV input requires librosa. Install dependency: librosa."
            ) from exc
        wav, sr = librosa.load(str(path), sr=None, mono=True)
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        sr = int(sr)

    wav_16k = _linear_resample(wav, src_sr=sr, dst_sr=16000)
    return np.clip(wav_16k, -1.0, 1.0).astype(np.float32)


def _normalize_whisper_language_tag(language: str | None) -> str | None:
    if language is None:
        return None
    normalized = language.strip()
    if not normalized:
        return None
    if normalized.startswith("<|") and normalized.endswith("|>"):
        return normalized
    return f"<|{normalized.lower()}|>"


class WhisperGenAIASRClient:
    def __init__(
        self,
        *,
        pipeline: Any,
        task: str = "transcribe",
        max_new_tokens: int = 128,
        static_language: str | None = None,
        return_timestamps: bool = False,
        word_timestamps: bool = False,
    ) -> None:
        self._pipeline = pipeline
        self._task = task
        self._max_new_tokens = int(max_new_tokens)
        self._static_language = _normalize_whisper_language_tag(static_language)
        self._return_timestamps = bool(return_timestamps)
        self._word_timestamps = bool(word_timestamps)

    @classmethod
    def from_pretrained(
        cls,
        *,
        model_dir: str | Path = DEFAULT_WHISPER_GENAI_MODEL_DIR,
        device: str = "NPU",
        task: str = "transcribe",
        max_new_tokens: int = 128,
        static_language: str | None = None,
        return_timestamps: bool = False,
        word_timestamps: bool = False,
    ) -> "WhisperGenAIASRClient":
        try:
            import openvino_genai as ov_genai
        except Exception as exc:  # pragma: no cover - dependency presence
            raise VoiceRuntimeUnavailableError(
                "OpenVINO GenAI runtime is not installed. Install dependency: openvino-genai."
            ) from exc

        resolved_model_dir = Path(model_dir)
        if not resolved_model_dir.exists():
            raise FileNotFoundError(f"Whisper model directory does not exist: {resolved_model_dir}")

        normalized_device = str(device).strip().upper()
        if normalized_device not in {"CPU", "GPU", "NPU"}:
            raise ValueError("device must be one of: CPU, GPU, NPU.")

        pipeline_kwargs: dict[str, Any] = {}
        if normalized_device == "NPU":
            pipeline_kwargs["STATIC_PIPELINE"] = True
        if word_timestamps:
            pipeline_kwargs["word_timestamps"] = True

        pipe = ov_genai.WhisperPipeline(str(resolved_model_dir), normalized_device, **pipeline_kwargs)
        return cls(
            pipeline=pipe,
            task=task,
            max_new_tokens=max_new_tokens,
            static_language=static_language,
            return_timestamps=return_timestamps,
            word_timestamps=word_timestamps,
        )

    def transcribe_path(
        self,
        *,
        audio_path: Path,
        context: str = "",
        language: str | None = None,
    ) -> dict[str, Any]:
        del context  # Whisper pipeline does not use text context prompt in this runtime path.

        speech = _load_audio_mono_16k(audio_path)
        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": self._max_new_tokens,
            "task": self._task,
        }
        normalized_language = _normalize_whisper_language_tag(language) or self._static_language
        if normalized_language is not None:
            generate_kwargs["language"] = normalized_language
        if self._return_timestamps:
            generate_kwargs["return_timestamps"] = True
        if self._word_timestamps:
            generate_kwargs["word_timestamps"] = True

        result = self._pipeline.generate(speech.tolist(), **generate_kwargs)
        texts = getattr(result, "texts", None)
        if isinstance(texts, (list, tuple)) and texts:
            text = str(texts[0])
        else:
            text = str(getattr(result, "text", ""))
            if not text:
                text = str(result)

        return {
            "text": text,
            "language": str(getattr(result, "language", "")),
        }


class QwenTTSClient:
    def __init__(self, model: Any) -> None:
        self._model = model

    @classmethod
    def from_pretrained(
        cls,
        *,
        model_id: str = DEFAULT_QWEN3_TTS_MODEL,
        device_map: str = "auto",
        dtype: str = "auto",
    ) -> "QwenTTSClient":
        try:
            from qwen_tts import Qwen3TTSModel
        except Exception as exc:  # pragma: no cover - dependency presence
            raise VoiceRuntimeUnavailableError(
                "Qwen TTS runtime is not installed. Install dependency: qwen-tts."
            ) from exc

        model = Qwen3TTSModel.from_pretrained(
            model_id,
            trust_remote_code=True,
            device_map=device_map,
            dtype=_resolve_torch_dtype(dtype),
        )
        return cls(model=model)

    def get_supported_speakers(self) -> list[str]:
        speakers = self._model.get_supported_speakers()
        if not speakers:
            return []
        return [str(item) for item in speakers]

    def resolve_speaker(self, requested_speaker: str | None) -> str:
        if requested_speaker and requested_speaker.strip():
            return requested_speaker.strip()
        speakers = self.get_supported_speakers()
        if not speakers:
            raise RuntimeError(
                "TTS model did not return supported speakers; pass --speaker explicitly."
            )
        return speakers[0]

    def synthesize_custom_voice(
        self,
        *,
        text: str,
        speaker: str,
        language: str = "Auto",
        instruct: str | None = None,
    ) -> tuple[np.ndarray, int]:
        wavs, sample_rate = self._model.generate_custom_voice(
            text=text,
            speaker=speaker,
            language=language,
            instruct=instruct,
        )
        if not wavs:
            raise RuntimeError("TTS model returned empty waveform list.")
        waveform = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
        return waveform, int(sample_rate)

    @staticmethod
    def _normalize_stream_item(item: Any) -> tuple[np.ndarray, int | None]:
        waveform_payload: Any = item
        sample_rate: int | None = None

        if isinstance(item, dict):
            waveform_payload = item.get("waveform")
            if waveform_payload is None:
                waveform_payload = item.get("audio")
            if waveform_payload is None:
                waveform_payload = item.get("wav")
            if waveform_payload is None:
                waveform_payload = item.get("chunk")
            sample_rate_value = item.get("sample_rate", item.get("sr"))
            if isinstance(sample_rate_value, (int, float)):
                sample_rate = int(sample_rate_value)
        elif (
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[1], (int, float))
        ):
            waveform_payload = item[0]
            sample_rate = int(item[1])

        if waveform_payload is None:
            return np.zeros(0, dtype=np.float32), sample_rate
        waveform = np.asarray(waveform_payload, dtype=np.float32).reshape(-1)
        return waveform, sample_rate

    def stream_synthesize_custom_voice(
        self,
        *,
        text: str,
        speaker: str,
        language: str = "Auto",
        instruct: str | None = None,
        chunk_duration_ms: int = 200,
    ) -> Iterator[tuple[np.ndarray, int, str]]:
        if chunk_duration_ms <= 0:
            raise ValueError("chunk_duration_ms must be > 0.")

        stream_fn = None
        for fn_name in (
            "generate_custom_voice_stream",
            "stream_generate_custom_voice",
            "generate_stream_custom_voice",
            "stream_custom_voice",
        ):
            candidate = getattr(self._model, fn_name, None)
            if callable(candidate):
                stream_fn = candidate
                break

        if stream_fn is not None:
            stream_output = stream_fn(
                text=text,
                speaker=speaker,
                language=language,
                instruct=instruct,
            )
            looks_like_non_streaming_tuple = (
                isinstance(stream_output, tuple)
                and len(stream_output) == 2
                and isinstance(stream_output[1], (int, float))
            )
            if not looks_like_non_streaming_tuple:
                sample_rate_hint: int | None = None
                emitted_any = False
                for item in stream_output:
                    chunk, chunk_sample_rate = self._normalize_stream_item(item)
                    if chunk_sample_rate is not None:
                        sample_rate_hint = chunk_sample_rate
                    if chunk.size == 0:
                        continue
                    emitted_any = True
                    yield chunk, int(sample_rate_hint or 24000), "native"
                if emitted_any:
                    return

        waveform, sample_rate = self.synthesize_custom_voice(
            text=text,
            speaker=speaker,
            language=language,
            instruct=instruct,
        )
        chunk_samples = max(1, int(sample_rate * (float(chunk_duration_ms) / 1000.0)))
        for chunk in _chunk_waveform(waveform=waveform, chunk_size_samples=chunk_samples):
            if chunk.size == 0:
                continue
            yield chunk, int(sample_rate), "fallback_chunked"
