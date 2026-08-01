from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable, Protocol

import numpy as np


class _AudioFrame(Protocol):
    samples: np.ndarray


class MicrophoneLike(Protocol):
    target_block_size: int

    def read(self, timeout: float = 1.0) -> _AudioFrame:
        ...


class DetectorLike(Protocol):
    class ConfigLike(Protocol):
        sample_rate: int

    config: ConfigLike

    def reset(self) -> None:
        ...

    def is_speech(
        self,
        samples: np.ndarray,
    ) -> tuple[bool, float]:
        ...


@dataclass(frozen=True, slots=True)
class BargeInConfig:
    enabled: bool = True
    grace_seconds: float = 0.65
    trigger_speech_seconds: float = 0.32
    end_silence_seconds: float = 0.48
    max_utterance_seconds: float = 12.0
    pre_roll_seconds: float = 0.24
    minimum_rms: float = 0.008
    read_timeout_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.grace_seconds < 0:
            raise ValueError(
                'grace_seconds must not be negative.'
            )
        for name in (
            'trigger_speech_seconds',
            'end_silence_seconds',
            'max_utterance_seconds',
            'pre_roll_seconds',
            'read_timeout_seconds',
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f'{name} must be positive.')
        if self.minimum_rms < 0:
            raise ValueError(
                'minimum_rms must not be negative.'
            )


@dataclass(frozen=True, slots=True)
class BargeInCapture:
    samples: np.ndarray
    speech_detected: bool
    duration_seconds: float
    peak_probability: float
    end_reason: str


@dataclass(frozen=True, slots=True)
class BargeInResult:
    capture: BargeInCapture
    trigger_latency_seconds: float


def normalized_rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    scaled = (
        samples.astype(np.float32)
        / np.iinfo(np.int16).max
    )
    return float(
        np.sqrt(
            np.mean(
                np.square(scaled, dtype=np.float32)
            )
        )
    )


class BargeInMonitor:
    """Capture a user interruption while the assistant is speaking."""

    def __init__(
        self,
        config: BargeInConfig,
        detector: DetectorLike,
    ) -> None:
        self.config = config
        self.detector = detector
        self._stop_event = Event()
        self._triggered_event = Event()
        self._finished_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._result: BargeInResult | None = None
        self._error: BaseException | None = None

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def triggered(self) -> bool:
        return self._triggered_event.is_set()

    @property
    def result(self) -> BargeInResult | None:
        with self._lock:
            return self._result

    def start(
        self,
        microphone: MicrophoneLike,
        *,
        on_trigger: Callable[[], None],
    ) -> None:
        if not self.config.enabled:
            return
        if self.running:
            raise RuntimeError(
                'Barge-in monitor is already running.'
            )

        self._stop_event.clear()
        self._triggered_event.clear()
        self._finished_event.clear()
        with self._lock:
            self._result = None
            self._error = None

        self._thread = Thread(
            target=self._run,
            args=(microphone, on_trigger),
            name='jarvis-barge-in',
            daemon=True,
        )
        self._thread.start()

    def _run(
        self,
        microphone: MicrophoneLike,
        on_trigger: Callable[[], None],
    ) -> None:
        try:
            self.detector.reset()
            sample_rate = int(
                self.detector.config.sample_rate
            )
            frame_seconds = (
                microphone.target_block_size
                / sample_rate
            )
            pre_roll_frames = max(
                1,
                ceil(
                    self.config.pre_roll_seconds
                    / frame_seconds
                ),
            )
            pre_roll: deque[np.ndarray] = deque(
                maxlen=pre_roll_frames
            )

            started_at = monotonic()
            consecutive_speech = 0.0
            silence_seconds = 0.0
            peak_probability = 0.0
            captured: list[np.ndarray] = []
            trigger_latency = 0.0

            while not self._stop_event.is_set():
                try:
                    frame = microphone.read(
                        timeout=(
                            self.config.read_timeout_seconds
                        )
                    )
                except TimeoutError:
                    continue

                samples = np.ascontiguousarray(
                    frame.samples,
                    dtype=np.int16,
                )
                elapsed = monotonic() - started_at

                if not self._triggered_event.is_set():
                    if elapsed < self.config.grace_seconds:
                        continue

                    pre_roll.append(samples.copy())
                    is_speech, probability = (
                        self.detector.is_speech(samples)
                    )
                    peak_probability = max(
                        peak_probability,
                        probability,
                    )
                    loud_enough = (
                        normalized_rms(samples)
                        >= self.config.minimum_rms
                    )

                    if is_speech and loud_enough:
                        consecutive_speech += frame_seconds
                    else:
                        consecutive_speech = 0.0

                    if (
                        consecutive_speech
                        < self.config.trigger_speech_seconds
                    ):
                        continue

                    trigger_latency = elapsed
                    captured.extend(
                        item.copy()
                        for item in pre_roll
                    )
                    self._triggered_event.set()
                    on_trigger()
                    silence_seconds = 0.0
                    continue

                captured.append(samples.copy())
                is_speech, probability = (
                    self.detector.is_speech(samples)
                )
                peak_probability = max(
                    peak_probability,
                    probability,
                )

                if is_speech:
                    silence_seconds = 0.0
                else:
                    silence_seconds += frame_seconds

                duration = len(captured) * frame_seconds
                if (
                    silence_seconds
                    >= self.config.end_silence_seconds
                ):
                    self._store_result(
                        captured,
                        sample_rate=sample_rate,
                        peak_probability=peak_probability,
                        end_reason='barge_in_silence',
                        trigger_latency=trigger_latency,
                    )
                    return

                if (
                    duration
                    >= self.config.max_utterance_seconds
                ):
                    self._store_result(
                        captured,
                        sample_rate=sample_rate,
                        peak_probability=peak_probability,
                        end_reason='barge_in_max_duration',
                        trigger_latency=trigger_latency,
                    )
                    return

            if self._triggered_event.is_set() and captured:
                self._store_result(
                    captured,
                    sample_rate=sample_rate,
                    peak_probability=peak_probability,
                    end_reason='barge_in_stopped',
                    trigger_latency=trigger_latency,
                )
        except BaseException as exc:
            with self._lock:
                self._error = exc
        finally:
            self._finished_event.set()

    def _store_result(
        self,
        captured: list[np.ndarray],
        *,
        sample_rate: int,
        peak_probability: float,
        end_reason: str,
        trigger_latency: float,
    ) -> None:
        if not captured:
            return
        output = np.concatenate(captured).astype(
            np.int16,
            copy=False,
        )
        result = BargeInResult(
            capture=BargeInCapture(
                samples=output,
                speech_detected=True,
                duration_seconds=(
                    output.size / sample_rate
                ),
                peak_probability=peak_probability,
                end_reason=end_reason,
            ),
            trigger_latency_seconds=trigger_latency,
        )
        with self._lock:
            self._result = result

    def wait_for_result(
        self,
        timeout: float | None = None,
    ) -> BargeInResult | None:
        self._finished_event.wait(timeout=timeout)
        thread = self._thread
        if thread is not None and thread.is_alive():
            return None

        with self._lock:
            error = self._error
            result = self._result
        if error is not None:
            raise RuntimeError(
                f'Barge-in monitor failed: {error}'
            ) from error
        return result

    def stop(
        self,
        *,
        timeout: float = 2.0,
    ) -> BargeInResult | None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        return self.wait_for_result(timeout=0.0)

    def close(self) -> None:
        self.stop(timeout=2.0)
