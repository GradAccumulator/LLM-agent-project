from __future__ import annotations

from dataclasses import dataclass
import sys
import types
import unittest

import numpy as np

# Keep this unit test independent from PortAudio and torch availability.
audio_stub = types.ModuleType('src.audio')
audio_stub.MicrophoneStream = type('MicrophoneStream', (), {})
sys.modules['src.audio'] = audio_stub
vad_stub = types.ModuleType('src.vad')
vad_stub.VoiceActivityDetector = type('VoiceActivityDetector', (), {})
sys.modules['src.vad'] = vad_stub

from src.speech import CaptureConfig, SpeechCapture


@dataclass
class _Frame:
    samples: np.ndarray


class _Microphone:
    target_block_size = 1280

    def __init__(self, frame_count: int) -> None:
        self._frames = [
            _Frame(np.zeros(self.target_block_size, dtype=np.int16))
            for _ in range(frame_count)
        ]

    def read(self, timeout: float) -> _Frame:
        if not self._frames:
            raise RuntimeError('No frames left.')
        return self._frames.pop(0)


class _Detector:
    class _Config:
        sample_rate = 16_000

    config = _Config()

    def reset(self) -> None:
        pass

    def is_speech(self, samples: np.ndarray) -> tuple[bool, float]:
        return False, 0.01


class SpeechCaptureFollowupTests(unittest.TestCase):
    def test_per_call_timeout_override(self) -> None:
        capture = SpeechCapture(CaptureConfig(start_timeout_seconds=4.0), detector=_Detector())
        result = capture.capture(_Microphone(frame_count=3), start_timeout_seconds=0.16)
        self.assertFalse(result.speech_detected)
        self.assertEqual(result.end_reason, 'start_timeout')


if __name__ == '__main__':
    unittest.main()
