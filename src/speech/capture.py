from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
import wave
from typing import Callable

import numpy as np

from src.audio import MicrophoneStream
from src.vad import VoiceActivityDetector


@dataclass(frozen=True, slots=True)
class CaptureConfig:
    sample_rate: int = 16_000
    start_timeout_seconds: float = 4.0
    end_silence_seconds: float = 0.8
    max_utterance_seconds: float = 15.0
    minimum_speech_seconds: float = 0.16
    pre_roll_seconds: float = 0.24


@dataclass(frozen=True, slots=True)
class CaptureResult:
    samples: np.ndarray
    speech_detected: bool
    duration_seconds: float
    peak_probability: float
    end_reason: str


def prune_wave_files(
    directory: str | Path,
    max_files: int = 5,
) -> tuple[Path, ...]:
    """Delete old command recordings but leave unrelated WAV files."""
    if max_files <= 0:
        raise ValueError("max_files must be positive.")

    output_directory = Path(directory)
    if not output_directory.is_dir():
        return ()

    candidates = [
        path
        for path in output_directory.glob("command_*.wav")
        if path.is_file()
    ]
    candidates.sort(
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )

    deleted: list[Path] = []
    for path in candidates[max_files:]:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        deleted.append(path)
    return tuple(deleted)


def save_wave_file(
    samples: np.ndarray,
    directory: str | Path,
    sample_rate: int = 16_000,
    max_saved_files: int = 5,
) -> Path:
    if max_saved_files <= 0:
        raise ValueError("max_saved_files must be positive.")

    output_directory = Path(directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_directory / f"command_{timestamp}.wav"

    with wave.open(str(output_path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(
            np.ascontiguousarray(samples, dtype=np.int16).tobytes()
        )

    prune_wave_files(output_directory, max_files=max_saved_files)
    return output_path


class SpeechCapture:
    def __init__(
        self,
        config: CaptureConfig,
        detector: VoiceActivityDetector,
    ) -> None:
        if config.sample_rate != detector.config.sample_rate:
            raise ValueError(
                "SpeechCapture and VoiceActivityDetector sample rates differ."
            )
        if config.start_timeout_seconds <= 0:
            raise ValueError("start_timeout_seconds must be positive.")
        if config.end_silence_seconds <= 0:
            raise ValueError("end_silence_seconds must be positive.")
        if config.max_utterance_seconds <= 0:
            raise ValueError("max_utterance_seconds must be positive.")

        self.config = config
        self.detector = detector

    def capture(
        self,
        microphone: MicrophoneStream,
        *,
        start_timeout_seconds: float | None = None,
        on_speech_start: Callable[[], None] | None = None,
    ) -> CaptureResult:
        self.detector.reset()

        effective_start_timeout = (
            self.config.start_timeout_seconds
            if start_timeout_seconds is None
            else start_timeout_seconds
        )
        if effective_start_timeout <= 0:
            raise ValueError('start_timeout_seconds must be positive.')

        frame_seconds = (
            microphone.target_block_size / self.config.sample_rate
        )
        pre_roll_frames = max(
            1,
            ceil(self.config.pre_roll_seconds / frame_seconds),
        )
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_frames)

        captured: list[np.ndarray] = []
        elapsed_seconds = 0.0
        speech_seconds = 0.0
        silence_seconds = 0.0
        speech_started = False
        peak_probability = 0.0

        while True:
            frame = microphone.read(timeout=2.0)
            samples = frame.samples
            is_speech, probability = self.detector.is_speech(samples)

            elapsed_seconds += frame_seconds
            peak_probability = max(peak_probability, probability)

            if not speech_started:
                pre_roll.append(samples.copy())

                if is_speech:
                    speech_started = True
                    if on_speech_start is not None:
                        on_speech_start()
                    captured.extend(pre_roll)
                    speech_seconds += frame_seconds
                    silence_seconds = 0.0
                elif elapsed_seconds >= effective_start_timeout:
                    return CaptureResult(
                        samples=np.empty(0, dtype=np.int16),
                        speech_detected=False,
                        duration_seconds=0.0,
                        peak_probability=peak_probability,
                        end_reason="start_timeout",
                    )

                continue

            captured.append(samples.copy())

            if is_speech:
                speech_seconds += frame_seconds
                silence_seconds = 0.0
            else:
                silence_seconds += frame_seconds

            captured_seconds = len(captured) * frame_seconds

            if (
                speech_seconds >= self.config.minimum_speech_seconds
                and silence_seconds >= self.config.end_silence_seconds
            ):
                output = np.concatenate(captured).astype(np.int16, copy=False)
                return CaptureResult(
                    samples=output,
                    speech_detected=True,
                    duration_seconds=output.size / self.config.sample_rate,
                    peak_probability=peak_probability,
                    end_reason="silence",
                )

            if captured_seconds >= self.config.max_utterance_seconds:
                output = np.concatenate(captured).astype(np.int16, copy=False)
                return CaptureResult(
                    samples=output,
                    speech_detected=True,
                    duration_seconds=output.size / self.config.sample_rate,
                    peak_probability=peak_probability,
                    end_reason="max_duration",
                )
