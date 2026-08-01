from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from src.speech import CaptureConfig, SpeechCapture


class _Detector:
    config = SimpleNamespace(sample_rate=16000)

    def reset(self) -> None:
        pass

    def is_speech(self, samples):
        del samples
        return False, 0.0


class _Microphone:
    target_block_size = 1280

    def read(self, timeout=1.0):
        del timeout
        return SimpleNamespace(
            samples=np.zeros(1280, dtype=np.int16)
        )


class SpeechCaptureTextCancelTests(unittest.TestCase):
    def test_text_input_cancels_voice_wait(self) -> None:
        capture = SpeechCapture(
            CaptureConfig(),
            detector=_Detector(),
        )
        result = capture.capture(
            _Microphone(),
            should_cancel=lambda: True,
        )
        self.assertFalse(result.speech_detected)
        self.assertEqual(
            result.end_reason,
            "text_input",
        )


if __name__ == "__main__":
    unittest.main()
