from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class _PortAudioError(Exception):
    pass


_sounddevice_stub = types.ModuleType("sounddevice")
_sounddevice_stub.PortAudioError = _PortAudioError
_sounddevice_stub.CallbackFlags = object
_sounddevice_stub.default = types.SimpleNamespace(
    device=(-1, -1)
)
sys.modules.setdefault(
    "sounddevice",
    _sounddevice_stub,
)

import src.audio.microphone as microphone
from src.app.cli import parse_args


class _Default:
    device = (0, -1)


class _Stream:
    def __init__(
        self,
        fake,
        device,
    ) -> None:
        self.fake = fake
        self.device = device
        self.closed = False

    def start(self) -> None:
        count = self.fake.start_counts.get(
            self.device,
            0,
        )
        self.fake.start_counts[
            self.device
        ] = count + 1
        failures = (
            self.fake.start_failures.get(
                self.device,
                0,
            )
        )
        if count < failures:
            raise _PortAudioError(
                f"cannot open {self.device}"
            )

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakeSoundDevice:
    PortAudioError = _PortAudioError
    CallbackFlags = object
    default = _Default()

    def __init__(
        self,
        devices,
        hostapis,
    ) -> None:
        self.devices = devices
        self.hostapis = hostapis
        self.start_failures = {}
        self.start_counts = {}

    def query_devices(
        self,
        device=None,
        kind=None,
    ):
        del kind
        if device is None:
            return list(
                self.devices
            )
        if isinstance(device, int):
            if (
                device < 0
                or device
                >= len(self.devices)
            ):
                raise _PortAudioError(
                    "invalid device"
                )
            return dict(
                self.devices[device]
            )
        folded = str(
            device
        ).casefold()
        for info in self.devices:
            if folded in str(
                info["name"]
            ).casefold():
                return dict(info)
        raise _PortAudioError(
            "invalid device"
        )

    def query_hostapis(self, index):
        return {
            "name": (
                self.hostapis[index]
            )
        }

    def check_input_settings(
        self,
        **kwargs,
    ) -> None:
        device = kwargs["device"]
        if isinstance(device, int):
            info = self.devices[device]
            if (
                info["max_input_channels"]
                <= 0
            ):
                raise _PortAudioError(
                    "not input"
                )

    def InputStream(
        self,
        *,
        device,
        **kwargs,
    ):
        del kwargs
        return _Stream(
            self,
            device,
        )


def _devices():
    return [
        {
            "name": "내장 마이크",
            "max_input_channels": 1,
            "default_samplerate": 48000,
            "hostapi": 0,
        },
        {
            "name": (
                "마이크 (BlackShark V3 Pro - Chat)"
            ),
            "max_input_channels": 1,
            "default_samplerate": 48000,
            "hostapi": 3,
        },
        {
            "name": (
                "마이크 (BlackShark V3 Pro - Chat)"
            ),
            "max_input_channels": 1,
            "default_samplerate": 48000,
            "hostapi": 1,
        },
    ]


class AudioDeviceRecoveryTests(
    unittest.TestCase
):
    def test_auto_parsing(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--device",
                "auto",
            ]
        )
        self.assertIsNone(
            args.device
        )
        self.assertTrue(
            args.device_was_explicit
        )

    def test_stale_index_recovers_by_name(
        self,
    ) -> None:
        fake = _FakeSoundDevice(
            _devices(),
            [
                "MME",
                "Windows WASAPI",
                "DirectSound",
                "Windows WDM-KS",
            ],
        )
        with patch.object(
            microphone,
            "sd",
            fake,
        ):
            stream = (
                microphone
                .MicrophoneStream(
                    microphone.AudioConfig(
                        device=18,
                        preferred_device_name=(
                            "BlackShark"
                        ),
                    )
                )
            )

        self.assertEqual(
            stream.device,
            2,
        )
        self.assertTrue(
            stream.recovered
        )

    def test_probe_skips_unopenable_match(
        self,
    ) -> None:
        fake = _FakeSoundDevice(
            _devices(),
            [
                "MME",
                "Windows WASAPI",
                "DirectSound",
                "Windows WDM-KS",
            ],
        )
        fake.start_failures[2] = 1
        with patch.object(
            microphone,
            "sd",
            fake,
        ):
            stream = (
                microphone
                .MicrophoneStream(
                    microphone.AudioConfig(
                        device=None,
                        preferred_device_name=(
                            "BlackShark"
                        ),
                        probe_devices_on_startup=True,
                    )
                )
            )

        self.assertEqual(
            stream.device,
            1,
        )

    def test_runtime_open_failure_recovers(
        self,
    ) -> None:
        fake = _FakeSoundDevice(
            _devices(),
            [
                "MME",
                "Windows WASAPI",
                "DirectSound",
                "Windows WDM-KS",
            ],
        )
        # No startup probing: index 1 is initially accepted. Its
        # first actual runtime open fails, then index 2 succeeds.
        fake.start_failures[1] = 1
        with patch.object(
            microphone,
            "sd",
            fake,
        ):
            stream = (
                microphone
                .MicrophoneStream(
                    microphone.AudioConfig(
                        device=1,
                        preferred_device_name=(
                            "BlackShark"
                        ),
                        probe_devices_on_startup=False,
                    )
                )
            )
            stream.start()
            try:
                self.assertEqual(
                    stream.device,
                    2,
                )
                self.assertTrue(
                    stream.recovered
                )
            finally:
                stream.close()

    def test_stale_config_is_changed_to_auto(
        self,
    ) -> None:
        fake = _FakeSoundDevice(
            _devices(),
            [
                "MME",
                "Windows WASAPI",
                "DirectSound",
                "Windows WDM-KS",
            ],
        )
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "user.toml"
            )
            path.write_text(
                (
                    "[audio]\n"
                    "device = 18\n"
                    'preferred_device = "BlackShark"\n'
                    "\n[tts]\n"
                    "rate_percent = 50\n"
                ),
                encoding="utf-8",
            )

            with patch.object(
                microphone,
                "sd",
                fake,
            ):
                stream = (
                    microphone
                    .MicrophoneStream(
                        microphone.AudioConfig(
                            device=18,
                            preferred_device_name=(
                                "BlackShark"
                            ),
                            recovery_config_path=(
                                path
                            ),
                        )
                    )
                )

            content = path.read_text(
                encoding="utf-8"
            )
            self.assertIn(
                'device = "auto"',
                content,
            )
            self.assertTrue(
                stream.config_updated
            )
            self.assertIn(
                "[tts]",
                content,
            )

    def test_auto_rewrite_is_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "user.toml"
            )
            path.write_text(
                (
                    "[audio]\n"
                    'device = "auto"\n'
                ),
                encoding="utf-8",
            )
            changed = (
                microphone
                .rewrite_audio_device_to_auto(
                    path
                )
            )
            self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
