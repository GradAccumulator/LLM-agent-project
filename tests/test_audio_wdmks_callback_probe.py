from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch


class _PortAudioError(Exception):
    pass


_stub = types.ModuleType("sounddevice")
_stub.PortAudioError = _PortAudioError
_stub.CallbackFlags = object
_stub.default = types.SimpleNamespace(
    device=(-1, -1)
)
sys.modules.setdefault(
    "sounddevice",
    _stub,
)

import src.audio.microphone as microphone


class _Stream:
    def __init__(self, callback) -> None:
        self.callback = callback

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


class _WdmKsSoundDevice:
    PortAudioError = _PortAudioError
    CallbackFlags = object
    default = types.SimpleNamespace(
        device=(0, -1)
    )

    def __init__(self) -> None:
        self.callback_seen = None
        self.info = {
            "name": (
                "마이크 "
                "(BlackShark V3 Pro - Chat)"
            ),
            "index": 0,
            "hostapi": 3,
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 48000,
        }

    def query_devices(
        self,
        device=None,
        kind=None,
    ):
        del kind
        if device is None:
            return [dict(self.info)]
        if device != 0:
            raise _PortAudioError(
                "invalid device"
            )
        return dict(self.info)

    def query_hostapis(self, index):
        if index != 3:
            raise AssertionError(index)
        return {
            "name": "Windows WDM-KS",
        }

    def check_input_settings(
        self,
        **kwargs,
    ) -> None:
        del kwargs

    def InputStream(
        self,
        *,
        callback=None,
        **kwargs,
    ):
        del kwargs
        if callback is None:
            raise _PortAudioError(
                "Blocking API not supported yet"
            )
        self.callback_seen = callback
        return _Stream(callback)


class WdmKsCallbackProbeTests(
    unittest.TestCase
):
    def test_startup_probe_passes_callback(
        self,
    ) -> None:
        fake = _WdmKsSoundDevice()

        with patch.object(
            microphone,
            "sd",
            fake,
        ):
            stream = (
                microphone
                .MicrophoneStream(
                    microphone.AudioConfig(
                        device=0,
                        preferred_device_name=(
                            "BlackShark"
                        ),
                        probe_devices_on_startup=True,
                    )
                )
            )

        self.assertEqual(stream.device, 0)
        self.assertIsNotNone(
            fake.callback_seen
        )
        self.assertFalse(stream.recovered)

    def test_same_fake_rejects_blocking_mode(
        self,
    ) -> None:
        fake = _WdmKsSoundDevice()
        with self.assertRaises(
            _PortAudioError
        ):
            fake.InputStream(
                device=0,
                samplerate=48000,
                channels=1,
                dtype="int16",
            )


if __name__ == "__main__":
    unittest.main()
