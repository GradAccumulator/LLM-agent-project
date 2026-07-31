from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from time import perf_counter
from typing import Any
import warnings

import numpy as np


_DLL_DIRECTORY_HANDLES: list[Any] = []


@dataclass(frozen=True, slots=True)
class SpeechRecognizerConfig:
    model_size: str = "turbo"
    language: str | None = "ko"
    device: str = "auto"
    compute_type: str = "auto"
    beam_size: int = 5
    sample_rate: int = 16_000
    download_root: Path = Path("models/faster-whisper")
    cpu_threads: int = 8


@dataclass(frozen=True, slots=True)
class TranscriptionSegment:
    start: float
    end: float
    text: str
    average_log_probability: float
    no_speech_probability: float


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str
    language_probability: float
    audio_duration_seconds: float
    inference_seconds: float
    segments: tuple[TranscriptionSegment, ...]


def _register_torch_dll_directory() -> None:
    """Make PyTorch CUDA/cuDNN DLLs visible to CTranslate2 on Windows."""

    if os.name != "nt":
        return

    try:
        import torch
    except ImportError:
        return

    torch_lib = Path(torch.__file__).resolve().parent / "lib"
    if not torch_lib.is_dir():
        return

    torch_lib_text = str(torch_lib)
    current_path = os.environ.get("PATH", "")
    if torch_lib_text.casefold() not in current_path.casefold():
        os.environ["PATH"] = torch_lib_text + os.pathsep + current_path

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if callable(add_dll_directory):
        try:
            handle = add_dll_directory(torch_lib_text)
        except OSError:
            return
        _DLL_DIRECTORY_HANDLES.append(handle)


def _cuda_device_available(ctranslate2: Any) -> bool:
    try:
        return int(ctranslate2.get_cuda_device_count()) > 0
    except (AttributeError, OSError, RuntimeError, ValueError):
        return False


def _looks_like_cuda_error(error: BaseException) -> bool:
    message = str(error).casefold()
    markers = (
        "cuda",
        "cudnn",
        "cublas",
        "nvcuda",
        "gpu",
        "float16",
        "dll",
        "dynamic library",
    )
    return any(marker in message for marker in markers)


class SpeechRecognizer:
    def __init__(self, config: SpeechRecognizerConfig) -> None:
        if config.sample_rate != 16_000:
            raise ValueError("Whisper input must use a 16000 Hz sample rate.")
        if config.device not in {"auto", "cuda", "cpu"}:
            raise ValueError("STT device must be auto, cuda, or cpu.")
        if config.beam_size <= 0:
            raise ValueError("beam_size must be positive.")
        if config.cpu_threads <= 0:
            raise ValueError("cpu_threads must be positive.")

        _register_torch_dll_directory()

        try:
            import ctranslate2
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        self.config = config
        self._ctranslate2 = ctranslate2
        self._whisper_model_type = WhisperModel
        self._automatic_device = config.device == "auto"
        self._used_cpu_fallback = False

        self.device = self._resolve_device(config.device)
        self.compute_type = self._resolve_compute_type(
            config.compute_type,
            self.device,
        )
        self._model = self._load_model_with_optional_fallback()

    def _resolve_device(self, requested: str) -> str:
        if requested != "auto":
            return requested
        return (
            "cuda"
            if _cuda_device_available(self._ctranslate2)
            else "cpu"
        )

    @staticmethod
    def _resolve_compute_type(requested: str, device: str) -> str:
        if requested != "auto":
            return requested
        return "float16" if device == "cuda" else "int8"

    def _create_model(self) -> Any:
        self.config.download_root.mkdir(parents=True, exist_ok=True)
        return self._whisper_model_type(
            self.config.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=str(self.config.download_root),
            cpu_threads=self.config.cpu_threads,
        )

    def _switch_to_cpu(self, error: BaseException) -> None:
        warnings.warn(
            "CUDA STT initialization failed; retrying on CPU int8. "
            f"Original error: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
        self.device = "cpu"
        self.compute_type = "int8"
        self._used_cpu_fallback = True

    def _load_model_with_optional_fallback(self) -> Any:
        try:
            return self._create_model()
        except (OSError, RuntimeError, ValueError) as exc:
            should_fallback = (
                self._automatic_device
                and self.device == "cuda"
                and not self._used_cpu_fallback
                and _looks_like_cuda_error(exc)
            )
            if not should_fallback:
                raise RuntimeError(
                    "Failed to load the Faster-Whisper model "
                    f"'{self.config.model_size}' on {self.device}/"
                    f"{self.compute_type}: {exc}"
                ) from exc

            self._switch_to_cpu(exc)
            return self._create_model()

    @property
    def model_name(self) -> str:
        return self.config.model_size

    @property
    def language(self) -> str | None:
        return self.config.language

    def _transcribe_once(
        self,
        audio: np.ndarray,
    ) -> TranscriptionResult:
        started_at = perf_counter()
        raw_segments, info = self._model.transcribe(
            audio,
            language=self.config.language,
            task="transcribe",
            beam_size=self.config.beam_size,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            word_timestamps=False,
        )

        # faster-whisper returns a generator. Iteration performs the
        # actual inference, so keep it inside the timed/error block.
        converted_segments = tuple(
            TranscriptionSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=str(segment.text).strip(),
                average_log_probability=float(segment.avg_logprob),
                no_speech_probability=float(segment.no_speech_prob),
            )
            for segment in raw_segments
        )
        inference_seconds = perf_counter() - started_at

        text = " ".join(
            segment.text
            for segment in converted_segments
            if segment.text
        ).strip()

        return TranscriptionResult(
            text=text,
            language=str(info.language),
            language_probability=float(info.language_probability),
            audio_duration_seconds=audio.size / self.config.sample_rate,
            inference_seconds=inference_seconds,
            segments=converted_segments,
        )

    def transcribe(self, samples: np.ndarray) -> TranscriptionResult:
        if samples.ndim != 1:
            raise ValueError("STT audio must be a one-dimensional mono array.")
        if samples.size == 0:
            raise ValueError("STT audio is empty.")

        if samples.dtype == np.int16:
            audio = samples.astype(np.float32) / 32768.0
        else:
            audio = np.asarray(samples, dtype=np.float32)
            audio = np.clip(audio, -1.0, 1.0)
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        try:
            return self._transcribe_once(audio)
        except (OSError, RuntimeError, ValueError) as exc:
            should_fallback = (
                self._automatic_device
                and self.device == "cuda"
                and not self._used_cpu_fallback
                and _looks_like_cuda_error(exc)
            )
            if not should_fallback:
                raise RuntimeError(f"Speech recognition failed: {exc}") from exc

            self._switch_to_cpu(exc)
            self._model = self._create_model()
            return self._transcribe_once(audio)
