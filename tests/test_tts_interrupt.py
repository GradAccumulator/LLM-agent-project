from __future__ import annotations

from threading import Event
import unittest

from src.tts import SpeechSynthesizer, SpeechTiming


class TtsInterruptTests(unittest.TestCase):
    def test_stop_sets_interrupt_event(self) -> None:
        synthesizer = SpeechSynthesizer.__new__(
            SpeechSynthesizer
        )
        synthesizer._interrupt_event = Event()
        synthesizer.stop()
        self.assertTrue(
            synthesizer._interrupt_event.is_set()
        )

    def test_timing_reports_interruption(self) -> None:
        timing = SpeechTiming(
            chunks=1,
            requested_chunks=3,
            first_audio_seconds=0.4,
            total_seconds=0.9,
            interrupted=True,
        )
        self.assertTrue(timing.interrupted)
        self.assertEqual(timing.chunks, 1)
        self.assertEqual(timing.requested_chunks, 3)


if __name__ == '__main__':
    unittest.main()
