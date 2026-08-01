from __future__ import annotations

from dataclasses import dataclass
import time
import unittest

from src.tts.synthesizer import (
    SpeechTiming,
    StreamingSpeechSession,
)


@dataclass
class _Config:
    max_characters: int = 1200
    playback_timeout_seconds: float = 2.0


class _FakeSynthesizer:
    def __init__(self) -> None:
        self.config = _Config()
        self.last_timing = SpeechTiming(
            chunks=0,
            requested_chunks=0,
            first_audio_seconds=0.0,
            total_seconds=0.0,
            interrupted=False,
        )
        self.spoken: list[str] = []
        self.stopped = False
        self._last_timing = self.last_timing

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        time.sleep(0.005)
        self.last_timing = SpeechTiming(
            chunks=1,
            requested_chunks=1,
            first_audio_seconds=0.002,
            total_seconds=0.005,
            interrupted=False,
        )
        self._last_timing = self.last_timing
        return True

    def stop(self) -> None:
        self.stopped = True


class StreamingSpeechSessionTests(unittest.TestCase):
    def test_speaks_enqueued_chunks_in_order(self) -> None:
        synthesizer = _FakeSynthesizer()
        session = StreamingSpeechSession(
            synthesizer
        )
        session.enqueue("첫 문장입니다.")
        session.enqueue("둘째 문장입니다.")

        timing = session.finish()

        self.assertEqual(
            synthesizer.spoken,
            [
                "첫 문장입니다.",
                "둘째 문장입니다.",
            ],
        )
        self.assertEqual(
            timing.requested_chunks,
            2,
        )
        self.assertEqual(timing.chunks, 2)

    def test_cancel_stops_synthesizer(self) -> None:
        synthesizer = _FakeSynthesizer()
        session = StreamingSpeechSession(
            synthesizer
        )

        timing = session.cancel()

        self.assertTrue(synthesizer.stopped)
        self.assertTrue(timing.interrupted)


if __name__ == "__main__":
    unittest.main()
