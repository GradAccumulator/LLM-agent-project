from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event
from typing import TypeAlias

import numpy as np
import sounddevice as sd


Device: TypeAlias = int | str | None


@dataclass(frozen=True, slots=True)
class AudioConfig:
    """Configuration for mono microphone streaming."""

    sample_rate: int = 16_000
    channels: int = 1
    block_duration_ms: int = 80
    dtype: str = "float32"
    device: Device = None

    @property
    def block_size(self) -> int:
        return max(1, round(self.sample_rate * self.block_duration_ms / 1_000))


@dataclass(frozen=True, slots=True)
class AudioLevel:
    rms: float
    peak: float
    overflowed: bool = False


class MicrophoneMonitor:
    """Reads microphone frames and exposes lightweight audio-level data.

    The PortAudio callback only computes values and writes to a one-item queue.
    Console output and other slower work happen outside the real-time callback.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._levels: Queue[AudioLevel] = Queue(maxsize=1)
        self._stop_event = Event()

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())

    def selected_device_info(self) -> dict:
        return dict(sd.query_devices(self.config.device, "input"))

    def validate(self) -> None:
        if self.config.sample_rate <= 0:
            raise ValueError("sample_rate must be greater than 0.")
        if self.config.channels != 1:
            raise ValueError("Step 1 currently supports mono input only.")
        if self.config.block_duration_ms <= 0:
            raise ValueError("block_duration_ms must be greater than 0.")

        sd.check_input_settings(
            device=self.config.device,
            channels=self.config.channels,
            dtype=self.config.dtype,
            samplerate=self.config.sample_rate,
        )

    def stop(self) -> None:
        self._stop_event.set()

    def _publish_latest(self, level: AudioLevel) -> None:
        try:
            self._levels.put_nowait(level)
            return
        except Full:
            pass

        try:
            self._levels.get_nowait()
        except Empty:
            pass

        try:
            self._levels.put_nowait(level)
        except Full:
            # Losing one visual meter update is harmless.
            pass

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time_info

        samples = np.asarray(indata[:, 0], dtype=np.float32)
        if samples.size == 0:
            return

        rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))
        peak = float(np.max(np.abs(samples)))
        self._publish_latest(
            AudioLevel(rms=rms, peak=peak, overflowed=bool(status.input_overflow))
        )

    def run(self) -> None:
        self.validate()
        self._stop_event.clear()

        with sd.InputStream(
            device=self.config.device,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.block_size,
            callback=self._callback,
        ):
            while not self._stop_event.is_set():
                try:
                    level = self._levels.get(timeout=0.25)
                except Empty:
                    continue
                self._print_meter(level)

        print("\nMicrophone stream stopped.")

    @staticmethod
    def _print_meter(level: AudioLevel, width: int = 48) -> None:
        # Speech commonly occupies only a small part of the full [-1, 1] range,
        # so scale RMS for a useful visual meter without changing actual audio.
        normalized = min(level.rms * 12.0, 1.0)
        filled = round(normalized * width)
        bar = "█" * filled + "·" * (width - filled)
        warning = "  [INPUT OVERFLOW]" if level.overflowed else ""
        print(
            f"\rMIC [{bar}] rms={level.rms:0.4f} peak={level.peak:0.4f}{warning}",
            end="",
            flush=True,
        )
