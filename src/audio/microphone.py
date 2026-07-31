from __future__ import annotations

from dataclasses import dataclass
from math import gcd
from queue import Empty, Full, Queue
from typing import TypeAlias

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

Device: TypeAlias = int | str | None

@dataclass(frozen=True, slots=True)
class AudioConfig:
    target_sample_rate: int = 16_000
    channels: int = 1
    block_duration_ms: int = 80
    dtype: str = "int16"
    device: Device = None
    queue_size: int = 32

@dataclass(frozen=True, slots=True)
class AudioFrame:
    samples: np.ndarray
    input_overflow: bool = False

class MicrophoneStream:
    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._frames: Queue[AudioFrame] = Queue(maxsize=config.queue_size)
        self._stream: sd.InputStream | None = None
        self._dropped_frames = 0
        info = self.selected_device_info()
        self.input_sample_rate = int(round(float(info["default_samplerate"])))
        self.input_block_size = round(self.input_sample_rate * config.block_duration_ms / 1000)
        self.target_block_size = round(config.target_sample_rate * config.block_duration_ms / 1000)

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())

    def selected_device_info(self) -> dict:
        return dict(sd.query_devices(self.config.device, "input"))

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def validate(self) -> None:
        if self.config.target_sample_rate != 16_000:
            raise ValueError("openWakeWord requires 16000 Hz audio.")
        sd.check_input_settings(device=self.config.device, channels=1, dtype="int16", samplerate=self.input_sample_rate)

    def _resample(self, samples: np.ndarray) -> np.ndarray:
        if self.input_sample_rate == self.config.target_sample_rate:
            output = samples
        else:
            d = gcd(self.input_sample_rate, self.config.target_sample_rate)
            output = resample_poly(samples.astype(np.float32), self.config.target_sample_rate // d, self.input_sample_rate // d)
            output = np.clip(np.rint(output), -32768, 32767).astype(np.int16)
        if output.size > self.target_block_size:
            output = output[:self.target_block_size]
        elif output.size < self.target_block_size:
            output = np.pad(output, (0, self.target_block_size-output.size))
        return np.ascontiguousarray(output, dtype=np.int16)

    def _callback(self, indata, frames, time_info, status) -> None:
        del frames, time_info
        frame = AudioFrame(self._resample(np.asarray(indata[:,0], dtype=np.int16).copy()), bool(status.input_overflow))
        try:
            self._frames.put_nowait(frame)
        except Full:
            self._dropped_frames += 1
            try: self._frames.get_nowait()
            except Empty: pass
            try: self._frames.put_nowait(frame)
            except Full: self._dropped_frames += 1

    def start(self) -> None:
        self.validate()
        self._stream = sd.InputStream(device=self.config.device, samplerate=self.input_sample_rate, channels=1, dtype="int16", blocksize=self.input_block_size, callback=self._callback)
        self._stream.start()

    def read(self, timeout: float = 1.0) -> AudioFrame:
        try: return self._frames.get(timeout=timeout)
        except Empty as exc: raise TimeoutError("No microphone frame arrived.") from exc

    def close(self) -> None:
        if self._stream is None: return
        try: self._stream.stop()
        finally: self._stream.close(); self._stream=None

    def __enter__(self): self.start(); return self
    def __exit__(self, exc_type, exc, tb): self.close()
