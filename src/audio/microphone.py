from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import TypeAlias

import numpy as np
import sounddevice as sd


Device: TypeAlias = int | str | None


@dataclass(frozen=True, slots=True)
class AudioConfig:
    """Audio format required by the current wake-word model."""

    sample_rate: int = 16_000
    channels: int = 1
    block_duration_ms: int = 80
    dtype: str = "int16"
    device: Device = None
    queue_size: int = 32

    @property
    def block_size(self) -> int:
        return round(self.sample_rate * self.block_duration_ms / 1_000)


@dataclass(frozen=True, slots=True)
class AudioFrame:
    samples: np.ndarray
    input_overflow: bool = False


class MicrophoneStream:
    """Non-blocking microphone producer backed by a bounded frame queue.

    PortAudio's callback must stay fast. It only copies the current frame into
    a queue; model inference and terminal output happen in the main thread.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._frames: Queue[AudioFrame] = Queue(maxsize=config.queue_size)
        self._stream: sd.InputStream | None = None
        self._dropped_frames = 0

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())

    def selected_device_info(self) -> dict:
        return dict(sd.query_devices(self.config.device, "input"))

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def validate(self) -> None:
        if self.config.sample_rate != 16_000:
            raise ValueError("Wake-word input must use a 16000 Hz sample rate.")
        if self.config.channels != 1:
            raise ValueError("Wake-word input must be mono.")
        if self.config.dtype != "int16":
            raise ValueError("Wake-word input must use signed 16-bit PCM.")
        if self.config.block_duration_ms != 80:
            raise ValueError("Step 2 uses fixed 80 ms audio frames.")
        if self.config.queue_size <= 0:
            raise ValueError("queue_size must be greater than zero.")

        sd.check_input_settings(
            device=self.config.device,
            channels=self.config.channels,
            dtype=self.config.dtype,
            samplerate=self.config.sample_rate,
        )

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time_info

        # PortAudio may reuse `indata` after the callback returns.
        samples = np.asarray(indata[:, 0], dtype=np.int16).copy()
        frame = AudioFrame(
            samples=samples,
            input_overflow=bool(status.input_overflow),
        )

        try:
            self._frames.put_nowait(frame)
            return
        except Full:
            self._dropped_frames += 1

        # Prefer recent audio when the consumer temporarily falls behind.
        try:
            self._frames.get_nowait()
        except Empty:
            pass

        try:
            self._frames.put_nowait(frame)
        except Full:
            self._dropped_frames += 1

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("Microphone stream is already running.")

        self.validate()
        self._stream = sd.InputStream(
            device=self.config.device,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.block_size,
            callback=self._callback,
        )
        self._stream.start()

    def read(self, timeout: float = 1.0) -> AudioFrame:
        try:
            return self._frames.get(timeout=timeout)
        except Empty as exc:
            raise TimeoutError("No microphone frame arrived in time.") from exc

    def close(self) -> None:
        stream = self._stream
        self._stream = None

        if stream is None:
            return

        try:
            stream.stop()
        finally:
            stream.close()

    def __enter__(self) -> "MicrophoneStream":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()
