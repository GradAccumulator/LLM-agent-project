from __future__ import annotations

from dataclasses import dataclass
from math import gcd
from queue import Empty, Full, Queue
from typing import TypeAlias

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly


Device: TypeAlias = int | str | None


def _is_input_device(info: dict) -> bool:
    return int(info.get("max_input_channels", 0)) > 0


def _device_supports_native_input(index: int, info: dict) -> bool:
    try:
        sample_rate = int(round(float(info["default_samplerate"])))
        sd.check_input_settings(
            device=index,
            channels=1,
            dtype="int16",
            samplerate=sample_rate,
        )
        return True
    except (KeyError, TypeError, ValueError, sd.PortAudioError):
        return False


def select_input_device(
    requested: Device = None,
    preferred_name: str = "BlackShark",
) -> int | str:
    """Resolve an input device without relying on an unstable device index."""

    if requested is not None:
        # Validate an explicitly requested device early.
        sd.query_devices(requested, "input")
        return requested

    devices = list(sd.query_devices())

    # 1. PortAudio/Windows default input, if one is configured and usable.
    try:
        default_input = int(sd.default.device[0])
    except (TypeError, ValueError, IndexError):
        default_input = -1

    if 0 <= default_input < len(devices):
        info = dict(devices[default_input])
        if _is_input_device(info) and _device_supports_native_input(
            default_input, info
        ):
            return default_input

    # 2. User-friendly preferred-name matching. Prefer actual microphone names
    # over loopback/stereo-mix devices when several names match.
    preferred = preferred_name.casefold().strip()
    ranked_matches: list[tuple[int, int]] = []

    if preferred:
        for index, raw_info in enumerate(devices):
            info = dict(raw_info)
            if not _is_input_device(info):
                continue

            name = str(info.get("name", ""))
            folded = name.casefold()
            if preferred not in folded:
                continue
            if not _device_supports_native_input(index, info):
                continue

            microphone_bonus = 0 if (
                "마이크" in folded or "microphone" in folded or "mic" in folded
            ) else 1
            host_api = int(info.get("hostapi", 0))
            ranked_matches.append((microphone_bonus * 100 + host_api, index))

    if ranked_matches:
        ranked_matches.sort()
        return ranked_matches[0][1]

    # 3. Last fallback: first usable physical/input device. Avoid obvious
    # loopback sources until no cleaner option exists.
    fallback: list[int] = []
    avoided: list[int] = []

    for index, raw_info in enumerate(devices):
        info = dict(raw_info)
        if not _is_input_device(info):
            continue
        if not _device_supports_native_input(index, info):
            continue

        name = str(info.get("name", "")).casefold()
        if "stereo mix" in name or "스테레오 믹스" in name:
            avoided.append(index)
        else:
            fallback.append(index)

    if fallback:
        return fallback[0]
    if avoided:
        return avoided[0]

    raise RuntimeError(
        "No usable microphone input device was found. "
        "Check Windows microphone permissions and audio drivers."
    )


@dataclass(frozen=True, slots=True)
class AudioConfig:
    target_sample_rate: int = 16_000
    channels: int = 1
    block_duration_ms: int = 80
    dtype: str = "int16"
    device: Device = None
    preferred_device_name: str = "BlackShark"
    queue_size: int = 32


@dataclass(frozen=True, slots=True)
class AudioFrame:
    samples: np.ndarray
    input_overflow: bool = False


class MicrophoneStream:
    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self.device = select_input_device(
            requested=config.device,
            preferred_name=config.preferred_device_name,
        )
        self._frames: Queue[AudioFrame] = Queue(maxsize=config.queue_size)
        self._stream: sd.InputStream | None = None
        self._dropped_frames = 0

        info = self.selected_device_info()
        self.input_sample_rate = int(round(float(info["default_samplerate"])))
        self.input_block_size = round(
            self.input_sample_rate * config.block_duration_ms / 1_000
        )
        self.target_block_size = round(
            config.target_sample_rate * config.block_duration_ms / 1_000
        )

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())

    def selected_device_info(self) -> dict:
        return dict(sd.query_devices(self.device, "input"))

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def validate(self) -> None:
        if self.config.target_sample_rate != 16_000:
            raise ValueError("openWakeWord requires 16000 Hz audio.")
        if self.config.channels != 1:
            raise ValueError("Wake-word input must be mono.")
        if self.config.dtype != "int16":
            raise ValueError("Wake-word input must use int16 PCM.")
        if self.input_sample_rate <= 0:
            raise ValueError("The input device reported an invalid sample rate.")

        sd.check_input_settings(
            device=self.device,
            channels=self.config.channels,
            dtype=self.config.dtype,
            samplerate=self.input_sample_rate,
        )

    def _resample_to_target(self, samples: np.ndarray) -> np.ndarray:
        if self.input_sample_rate == self.config.target_sample_rate:
            output = samples
        else:
            divisor = gcd(
                self.input_sample_rate,
                self.config.target_sample_rate,
            )
            up = self.config.target_sample_rate // divisor
            down = self.input_sample_rate // divisor

            output = resample_poly(
                samples.astype(np.float32),
                up=up,
                down=down,
            )
            output = np.clip(
                np.rint(output),
                np.iinfo(np.int16).min,
                np.iinfo(np.int16).max,
            ).astype(np.int16)

        if output.size > self.target_block_size:
            output = output[: self.target_block_size]
        elif output.size < self.target_block_size:
            output = np.pad(
                output,
                (0, self.target_block_size - output.size),
            )

        return np.ascontiguousarray(output, dtype=np.int16)

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time_info

        native = np.asarray(indata[:, 0], dtype=np.int16).copy()
        frame = AudioFrame(
            samples=self._resample_to_target(native),
            input_overflow=bool(status.input_overflow),
        )

        try:
            self._frames.put_nowait(frame)
            return
        except Full:
            self._dropped_frames += 1

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
            device=self.device,
            samplerate=self.input_sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.input_block_size,
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
