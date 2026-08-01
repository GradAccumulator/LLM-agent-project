from __future__ import annotations

from dataclasses import dataclass
from threading import Event
import unittest

import numpy as np

from src.bargein import (
    BargeInConfig,
    BargeInMonitor,
)


@dataclass
class _Frame:
    samples: np.ndarray


class _Microphone:
    target_block_size = 1280

    def __init__(self, count: int) -> None:
        samples = np.full(
            self.target_block_size,
            3000,
            dtype=np.int16,
        )
        self.frames = [
            _Frame(samples.copy())
            for _ in range(count)
        ]

    def read(self, timeout: float = 1.0) -> _Frame:
        del timeout
        if not self.frames:
            raise TimeoutError
        return self.frames.pop(0)


class _Detector:
    class _Config:
        sample_rate = 16_000

    config = _Config()

    def __init__(self) -> None:
        self.index = 0
        self.probabilities = [
            0.10,
            0.95,
            0.95,
            0.90,
            0.20,
            0.10,
        ]

    def reset(self) -> None:
        self.index = 0

    def is_speech(
        self,
        samples: np.ndarray,
    ) -> tuple[bool, float]:
        del samples
        probability = self.probabilities[
            min(
                self.index,
                len(self.probabilities) - 1,
            )
        ]
        self.index += 1
        return probability >= 0.8, probability


class BargeInMonitorTests(unittest.TestCase):
    def test_detects_and_captures_interruption(self) -> None:
        triggered = Event()
        monitor = BargeInMonitor(
            BargeInConfig(
                grace_seconds=0.0,
                trigger_speech_seconds=0.16,
                end_silence_seconds=0.16,
                max_utterance_seconds=2.0,
                pre_roll_seconds=0.16,
                minimum_rms=0.0,
            ),
            detector=_Detector(),
        )
        monitor.start(
            _Microphone(count=12),
            on_trigger=triggered.set,
        )
        result = monitor.wait_for_result(timeout=2.0)

        self.assertTrue(triggered.is_set())
        self.assertTrue(monitor.triggered)
        self.assertIsNotNone(result)
        self.assertTrue(result.capture.speech_detected)
        self.assertGreater(
            result.capture.duration_seconds,
            0.0,
        )
        self.assertEqual(
            result.capture.end_reason,
            'barge_in_silence',
        )

    def test_stop_without_trigger_returns_none(self) -> None:
        detector = _Detector()
        detector.probabilities = [0.01]
        monitor = BargeInMonitor(
            BargeInConfig(
                grace_seconds=0.0,
                minimum_rms=0.0,
            ),
            detector=detector,
        )
        monitor.start(
            _Microphone(count=1),
            on_trigger=lambda: None,
        )
        result = monitor.stop(timeout=1.0)
        self.assertIsNone(result)
        self.assertFalse(monitor.triggered)


if __name__ == '__main__':
    unittest.main()
