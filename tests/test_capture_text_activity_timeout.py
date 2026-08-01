from __future__ import annotations

from dataclasses import dataclass
import unittest

import numpy as np

from src.speech import CaptureConfig, SpeechCapture


@dataclass
class _Frame:
    samples: np.ndarray


class _Microphone:
    target_block_size = 1600

    def __init__(self, on_read) -> None:
        self.read_count = 0
        self._on_read = on_read

    def read(self, timeout=2.0):
        del timeout
        self.read_count += 1
        self._on_read(self.read_count)
        return _Frame(
            np.zeros(
                self.target_block_size,
                dtype=np.int16,
            )
        )


class _DetectorConfig:
    sample_rate = 16000


class _Detector:
    config = _DetectorConfig()

    def reset(self) -> None:
        pass

    def is_speech(self, samples):
        del samples
        return False, 0.0


class CaptureTextActivityTimeoutTests(unittest.TestCase):
    def test_keyboard_activity_resets_start_timeout(self) -> None:
        activity = {"sequence": 0}

        def on_read(read_count: int) -> None:
            # With 0.1-second frames and a 0.3-second timeout, these
            # edits reset the timer twice before it can expire.
            if read_count in {2, 4}:
                activity["sequence"] += 1

        microphone = _Microphone(on_read)
        capture = SpeechCapture(
            CaptureConfig(
                sample_rate=16000,
                start_timeout_seconds=0.3,
            ),
            _Detector(),
        )

        result = capture.capture(
            microphone,
            start_timeout_seconds=0.3,
            start_timeout_activity=(
                lambda: activity["sequence"]
            ),
        )

        self.assertEqual(
            result.end_reason,
            "start_timeout",
        )
        self.assertGreaterEqual(
            microphone.read_count,
            7,
        )

    def test_no_activity_uses_normal_timeout(self) -> None:
        microphone = _Microphone(
            lambda _count: None
        )
        capture = SpeechCapture(
            CaptureConfig(
                sample_rate=16000,
                start_timeout_seconds=0.3,
            ),
            _Detector(),
        )

        result = capture.capture(
            microphone,
            start_timeout_seconds=0.3,
            start_timeout_activity=lambda: 0,
        )

        self.assertEqual(
            result.end_reason,
            "start_timeout",
        )
        self.assertEqual(
            microphone.read_count,
            3,
        )


if __name__ == "__main__":
    unittest.main()
