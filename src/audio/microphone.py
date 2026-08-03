from __future__ import annotations

from dataclasses import dataclass
from math import gcd
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
from typing import Any, TypeAlias

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly


Device: TypeAlias = int | str | None
_AUTO_DEVICE_NAMES = {
    "",
    "auto",
    "default",
    "none",
}
def _recoverable_audio_errors() -> tuple[type[BaseException], ...]:
    return (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        sd.PortAudioError,
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
    allow_device_recovery: bool = True
    probe_devices_on_startup: bool = True
    persist_recovered_device: bool = True
    recovery_config_path: Path | None = None

    def __post_init__(self) -> None:
        if self.target_sample_rate <= 0:
            raise ValueError(
                "target_sample_rate must be positive."
            )
        if self.channels != 1:
            raise ValueError(
                "Wake-word input must be mono."
            )
        if self.block_duration_ms <= 0:
            raise ValueError(
                "block_duration_ms must be positive."
            )
        if self.queue_size <= 0:
            raise ValueError(
                "queue_size must be positive."
            )


@dataclass(frozen=True, slots=True)
class AudioFrame:
    samples: np.ndarray
    input_overflow: bool = False


@dataclass(frozen=True, slots=True)
class _ResolvedDevice:
    device: int | str
    info: dict[str, Any]
    reason: str
    requested_failed: bool = False


def normalize_device(
    value: Device,
) -> Device:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.casefold() in (
            _AUTO_DEVICE_NAMES
        ):
            return None
        if stripped.isdigit():
            return int(stripped)
        return stripped
    return value


def _is_input_device(
    info: dict[str, Any],
) -> bool:
    return (
        int(
            info.get(
                "max_input_channels",
                0,
            )
        )
        > 0
    )


def _sample_rate(
    info: dict[str, Any],
) -> int:
    try:
        value = int(
            round(
                float(
                    info[
                        "default_samplerate"
                    ]
                )
            )
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "The input device reported an "
            "invalid default sample rate."
        ) from exc
    if value <= 0:
        raise ValueError(
            "The input device reported an "
            "invalid default sample rate."
        )
    return value


def _host_api_name(
    info: dict[str, Any],
) -> str:
    try:
        host_api = int(
            info.get("hostapi", -1)
        )
        if host_api < 0:
            return ""
        data = sd.query_hostapis(
            host_api
        )
        return str(
            dict(data).get(
                "name",
                "",
            )
        )
    except Exception:
        return ""


def _host_api_rank(
    info: dict[str, Any],
) -> int:
    name = _host_api_name(
        info
    ).casefold()
    # WASAPI is usually the most stable shared-mode choice on
    # current Windows. WDM-KS is placed later because it is more
    # likely to fail when a device is busy or changes state.
    if "wasapi" in name:
        return 0
    if "mme" in name:
        return 1
    if "directsound" in name:
        return 2
    if "wdm-ks" in name or "wdm ks" in name:
        return 3
    return 4


def _device_key(
    value: int | str,
) -> str:
    return (
        f"index:{value}"
        if isinstance(value, int)
        else f"name:{value.casefold()}"
    )


def _check_device(
    device: int | str,
    info: dict[str, Any],
    *,
    config: AudioConfig,
    probe_open: bool,
) -> bool:
    if not _is_input_device(info):
        return False

    sample_rate = _sample_rate(
        info
    )
    try:
        sd.check_input_settings(
            device=device,
            channels=config.channels,
            dtype=config.dtype,
            samplerate=sample_rate,
        )
    except _recoverable_audio_errors():
        return False

    if not probe_open:
        return True

    stream = None
    try:
        stream = sd.InputStream(
            device=device,
            samplerate=sample_rate,
            channels=config.channels,
            dtype=config.dtype,
            blocksize=max(
                1,
                round(
                    sample_rate
                    * config.block_duration_ms
                    / 1_000
                ),
            ),
        )
        stream.start()
        stream.stop()
        stream.close()
        stream = None
        return True
    except _recoverable_audio_errors():
        return False
    finally:
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass


def _preferred_rank(
    index: int,
    info: dict[str, Any],
    *,
    preferred: str,
) -> tuple[int, int, int, int]:
    name = str(
        info.get("name", "")
    )
    folded = name.casefold()
    if folded == preferred:
        match_rank = 0
    elif folded.startswith(
        preferred
    ):
        match_rank = 1
    else:
        match_rank = 2

    microphone_rank = (
        0
        if (
            "마이크" in folded
            or "microphone" in folded
            or " mic" in folded
            or folded.startswith("mic")
        )
        else 1
    )
    return (
        match_rank,
        microphone_rank,
        _host_api_rank(info),
        index,
    )


def _resolve_input_device(
    config: AudioConfig,
    *,
    requested: Device,
    exclude: set[str] | None = None,
    probe_open: bool,
) -> _ResolvedDevice:
    requested = normalize_device(
        requested
    )
    excluded = exclude or set()
    devices = [
        dict(item)
        for item in sd.query_devices()
    ]
    requested_failed = False

    if requested is not None:
        key = _device_key(
            requested
        )
        if key not in excluded:
            try:
                info = dict(
                    sd.query_devices(
                        requested,
                        "input",
                    )
                )
                if _check_device(
                    requested,
                    info,
                    config=config,
                    probe_open=probe_open,
                ):
                    return _ResolvedDevice(
                        device=requested,
                        info=info,
                        reason=(
                            "requested device"
                        ),
                    )
            except _recoverable_audio_errors():
                pass
        requested_failed = True

    preferred = (
        config
        .preferred_device_name
        .strip()
        .casefold()
    )
    preferred_matches: list[
        tuple[
            tuple[int, int, int, int],
            int,
            dict[str, Any],
        ]
    ] = []

    if preferred:
        for index, info in enumerate(
            devices
        ):
            if (
                _device_key(index)
                in excluded
            ):
                continue
            name = str(
                info.get("name", "")
            )
            if preferred not in (
                name.casefold()
            ):
                continue
            if not _check_device(
                index,
                info,
                config=config,
                probe_open=probe_open,
            ):
                continue
            preferred_matches.append(
                (
                    _preferred_rank(
                        index,
                        info,
                        preferred=preferred,
                    ),
                    index,
                    info,
                )
            )

    if preferred_matches:
        preferred_matches.sort(
            key=lambda item: item[0]
        )
        _, index, info = (
            preferred_matches[0]
        )
        return _ResolvedDevice(
            device=index,
            info=info,
            reason=(
                "preferred-name recovery"
                if requested_failed
                else "preferred-name match"
            ),
            requested_failed=(
                requested_failed
            ),
        )

    try:
        default_input = int(
            sd.default.device[0]
        )
    except (
        TypeError,
        ValueError,
        IndexError,
    ):
        default_input = -1

    if (
        0 <= default_input
        < len(devices)
        and _device_key(
            default_input
        )
        not in excluded
    ):
        info = devices[
            default_input
        ]
        if _check_device(
            default_input,
            info,
            config=config,
            probe_open=probe_open,
        ):
            return _ResolvedDevice(
                device=default_input,
                info=info,
                reason=(
                    "default-device recovery"
                    if requested_failed
                    else "system default"
                ),
                requested_failed=(
                    requested_failed
                ),
            )

    normal: list[
        tuple[int, int, dict[str, Any]]
    ] = []
    avoided: list[
        tuple[int, int, dict[str, Any]]
    ] = []

    for index, info in enumerate(
        devices
    ):
        if (
            _device_key(index)
            in excluded
        ):
            continue
        if not _check_device(
            index,
            info,
            config=config,
            probe_open=probe_open,
        ):
            continue

        name = str(
            info.get("name", "")
        ).casefold()
        item = (
            _host_api_rank(info),
            index,
            info,
        )
        if (
            "stereo mix" in name
            or "스테레오 믹스"
            in name
            or "loopback" in name
        ):
            avoided.append(item)
        else:
            normal.append(item)

    candidates = (
        normal
        if normal
        else avoided
    )
    if candidates:
        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )
        _, index, info = (
            candidates[0]
        )
        return _ResolvedDevice(
            device=index,
            info=info,
            reason=(
                "fallback recovery"
                if requested_failed
                else "first usable input"
            ),
            requested_failed=(
                requested_failed
            ),
        )

    raise RuntimeError(
        "No usable microphone input device was found. "
        "Check Windows microphone permissions, reconnect "
        "the headset, and run `python -m src.main "
        "--list-devices`."
    )


def select_input_device(
    requested: Device = None,
    preferred_name: str = "BlackShark",
) -> int | str:
    """Resolve a usable input device, treating stale indices as hints."""

    config = AudioConfig(
        device=requested,
        preferred_device_name=(
            preferred_name
        ),
        probe_devices_on_startup=False,
        persist_recovered_device=False,
    )
    return _resolve_input_device(
        config,
        requested=requested,
        probe_open=False,
    ).device


def rewrite_audio_device_to_auto(
    path: Path,
) -> bool:
    """Atomically replace a stale numeric [audio].device with 'auto'."""

    path = path.expanduser()
    if not path.is_file():
        return False

    original = path.read_text(
        encoding="utf-8"
    )
    newline = (
        "\r\n"
        if "\r\n" in original
        else "\n"
    )
    lines = original.splitlines()
    audio_start: int | None = None
    audio_end = len(lines)

    for index, line in enumerate(
        lines
    ):
        stripped = line.strip()
        if (
            stripped.casefold()
            == "[audio]"
        ):
            audio_start = index
            continue
        if (
            audio_start is not None
            and index > audio_start
            and stripped.startswith("[")
            and stripped.endswith("]")
        ):
            audio_end = index
            break

    changed = False
    if audio_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(
            [
                "[audio]",
                'device = "auto"',
            ]
        )
        changed = True
    else:
        pattern = re.compile(
            r"^(\s*)device\s*=.*$",
            re.IGNORECASE,
        )
        for index in range(
            audio_start + 1,
            audio_end,
        ):
            match = pattern.match(
                lines[index]
            )
            if match is None:
                continue
            replacement = (
                match.group(1)
                + 'device = "auto"'
            )
            if (
                lines[index]
                != replacement
            ):
                lines[index] = (
                    replacement
                )
                changed = True
            break
        else:
            lines.insert(
                audio_start + 1,
                'device = "auto"',
            )
            changed = True

    if not changed:
        return False

    output = (
        newline.join(lines)
        + (
            newline
            if original.endswith(
                ("\n", "\r")
            )
            else ""
        )
    )
    temporary = path.with_name(
        path.name + ".tmp"
    )
    temporary.write_text(
        output,
        encoding="utf-8",
    )
    os.replace(
        temporary,
        path,
    )
    return True


class MicrophoneStream:
    def __init__(
        self,
        config: AudioConfig,
    ) -> None:
        self.config = config
        self.requested_device = (
            normalize_device(
                config.device
            )
        )
        self._frames: Queue[
            AudioFrame
        ] = Queue(
            maxsize=config.queue_size
        )
        self._stream: (
            sd.InputStream | None
        ) = None
        self._dropped_frames = 0
        self._recoveries: list[
            dict[str, Any]
        ] = []
        self._config_updated = False

        resolved = (
            _resolve_input_device(
                config,
                requested=(
                    self.requested_device
                ),
                probe_open=(
                    config
                    .probe_devices_on_startup
                ),
            )
        )
        self._apply_device(
            resolved
        )
        if (
            resolved.requested_failed
            and self.requested_device
            is not None
        ):
            self._record_recovery(
                failed_device=(
                    self.requested_device
                ),
                resolved=resolved,
                error=(
                    "configured device was stale "
                    "or could not be opened"
                ),
            )

    @staticmethod
    def list_devices() -> str:
        return str(
            sd.query_devices()
        )

    def _apply_device(
        self,
        resolved: _ResolvedDevice,
    ) -> None:
        self.device = resolved.device
        self._selected_info = dict(
            resolved.info
        )
        self.selection_reason = (
            resolved.reason
        )
        self.input_sample_rate = (
            _sample_rate(
                self._selected_info
            )
        )
        self.input_block_size = max(
            1,
            round(
                self.input_sample_rate
                * self.config
                .block_duration_ms
                / 1_000
            ),
        )
        self.target_block_size = max(
            1,
            round(
                self.config
                .target_sample_rate
                * self.config
                .block_duration_ms
                / 1_000
            ),
        )

    def selected_device_info(
        self,
    ) -> dict[str, Any]:
        return dict(
            self._selected_info
        )

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    @property
    def recovered(self) -> bool:
        return bool(
            self._recoveries
        )

    @property
    def recovery_count(self) -> int:
        return len(
            self._recoveries
        )

    @property
    def config_updated(self) -> bool:
        return self._config_updated

    @property
    def latest_recovery(
        self,
    ) -> dict[str, Any] | None:
        return (
            dict(
                self._recoveries[-1]
            )
            if self._recoveries
            else None
        )

    def _record_recovery(
        self,
        *,
        failed_device: Device,
        resolved: _ResolvedDevice,
        error: str,
    ) -> None:
        event = {
            "failed_device": (
                failed_device
            ),
            "selected_device": (
                resolved.device
            ),
            "selected_name": str(
                resolved.info.get(
                    "name",
                    "",
                )
            ),
            "reason": (
                resolved.reason
            ),
            "error": error,
        }
        self._recoveries.append(
            event
        )

        path = (
            self.config
            .recovery_config_path
        )
        if (
            self.config
            .persist_recovered_device
            and path is not None
        ):
            try:
                self._config_updated = (
                    rewrite_audio_device_to_auto(
                        path
                    )
                    or self._config_updated
                )
            except OSError:
                pass

        print(
            "Audio recovery  : "
            f"[{failed_device}] -> "
            f"[{resolved.device}] "
            f"{event['selected_name']}"
        )
        if self._config_updated:
            print(
                "Audio config    : stale numeric device "
                "changed to device=\"auto\""
            )

    def validate(self) -> None:
        if (
            self.config
            .target_sample_rate
            != 16_000
        ):
            raise ValueError(
                "openWakeWord requires 16000 Hz audio."
            )
        if self.config.channels != 1:
            raise ValueError(
                "Wake-word input must be mono."
            )
        if self.config.dtype != "int16":
            raise ValueError(
                "Wake-word input must use int16 PCM."
            )
        if self.input_sample_rate <= 0:
            raise ValueError(
                "The input device reported an "
                "invalid sample rate."
            )

        sd.check_input_settings(
            device=self.device,
            channels=(
                self.config.channels
            ),
            dtype=self.config.dtype,
            samplerate=(
                self.input_sample_rate
            ),
        )

    def _resample_to_target(
        self,
        samples: np.ndarray,
    ) -> np.ndarray:
        if (
            self.input_sample_rate
            == self.config
            .target_sample_rate
        ):
            output = samples
        else:
            divisor = gcd(
                self.input_sample_rate,
                self.config
                .target_sample_rate,
            )
            up = (
                self.config
                .target_sample_rate
                // divisor
            )
            down = (
                self.input_sample_rate
                // divisor
            )

            output = resample_poly(
                samples.astype(
                    np.float32
                ),
                up=up,
                down=down,
            )
            output = np.clip(
                np.rint(output),
                np.iinfo(
                    np.int16
                ).min,
                np.iinfo(
                    np.int16
                ).max,
            ).astype(np.int16)

        if (
            output.size
            > self.target_block_size
        ):
            output = output[
                : self.target_block_size
            ]
        elif (
            output.size
            < self.target_block_size
        ):
            output = np.pad(
                output,
                (
                    0,
                    self.target_block_size
                    - output.size,
                ),
            )

        return np.ascontiguousarray(
            output,
            dtype=np.int16,
        )

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time_info

        native = np.asarray(
            indata[:, 0],
            dtype=np.int16,
        ).copy()
        frame = AudioFrame(
            samples=(
                self
                ._resample_to_target(
                    native
                )
            ),
            input_overflow=bool(
                status.input_overflow
            ),
        )

        try:
            self._frames.put_nowait(
                frame
            )
            return
        except Full:
            self._dropped_frames += 1

        try:
            self._frames.get_nowait()
        except Empty:
            pass

        try:
            self._frames.put_nowait(
                frame
            )
        except Full:
            self._dropped_frames += 1

    def _open_stream(self) -> None:
        stream = sd.InputStream(
            device=self.device,
            samplerate=(
                self.input_sample_rate
            ),
            channels=(
                self.config.channels
            ),
            dtype=self.config.dtype,
            blocksize=(
                self.input_block_size
            ),
            callback=self._callback,
        )
        try:
            stream.start()
        except Exception:
            try:
                stream.close()
            except Exception:
                pass
            raise
        self._stream = stream

    def _recover_after_open_failure(
        self,
        error: Exception,
    ) -> None:
        failed_device = self.device
        resolved = (
            _resolve_input_device(
                self.config,
                requested=None,
                exclude={
                    _device_key(
                        failed_device
                    )
                },
                probe_open=True,
            )
        )
        self._apply_device(
            resolved
        )
        self._record_recovery(
            failed_device=(
                failed_device
            ),
            resolved=resolved,
            error=(
                str(error).strip()
                or type(error).__name__
            ),
        )

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError(
                "Microphone stream is already running."
            )

        self.validate()
        try:
            self._open_stream()
            return
        except _recoverable_audio_errors() as exc:
            if not (
                self.config
                .allow_device_recovery
            ):
                raise

            try:
                self._recover_after_open_failure(
                    exc
                )
                self.validate()
                self._open_stream()
                return
            except Exception as recovery_exc:
                raise RuntimeError(
                    "The configured microphone could not "
                    f"be opened ({exc}). Automatic recovery "
                    "also failed: "
                    f"{recovery_exc}"
                ) from recovery_exc

    def read(
        self,
        timeout: float = 1.0,
    ) -> AudioFrame:
        try:
            return self._frames.get(
                timeout=timeout
            )
        except Empty as exc:
            raise TimeoutError(
                "No microphone frame arrived in time."
            ) from exc

    def clear_pending(self) -> int:
        removed = 0
        while True:
            try:
                self._frames.get_nowait()
            except Empty:
                return removed
            removed += 1

    def close(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return

        try:
            stream.stop()
        finally:
            stream.close()

    def __enter__(
        self,
    ) -> "MicrophoneStream":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        del exc_type, exc, traceback
        self.close()
