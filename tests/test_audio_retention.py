from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

import numpy as np

# Keep retention tests independent from PortAudio and torch.
audio_stub = types.ModuleType("src.audio")
audio_stub.MicrophoneStream = type("MicrophoneStream", (), {})
sys.modules["src.audio"] = audio_stub
vad_stub = types.ModuleType("src.vad")
vad_stub.VoiceActivityDetector = type("VoiceActivityDetector", (), {})
sys.modules["src.vad"] = vad_stub

from src.speech.capture import prune_wave_files, save_wave_file


class AudioRetentionTests(unittest.TestCase):
    def test_keeps_only_latest_five_command_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(8):
                path = root / f"command_{index:02d}.wav"
                path.write_bytes(b"test")
                timestamp = 1_000 + index
                os.utime(path, (timestamp, timestamp))

            unrelated = root / "music.wav"
            unrelated.write_bytes(b"keep")
            deleted = prune_wave_files(root, max_files=5)

            remaining = sorted(
                path.name for path in root.glob("command_*.wav")
            )
            self.assertEqual(
                remaining,
                [
                    "command_03.wav",
                    "command_04.wav",
                    "command_05.wav",
                    "command_06.wav",
                    "command_07.wav",
                ],
            )
            self.assertEqual(len(deleted), 3)
            self.assertTrue(unrelated.exists())

    def test_save_wave_file_enforces_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = np.zeros(320, dtype=np.int16)
            for _ in range(7):
                save_wave_file(samples, root, max_saved_files=5)
            self.assertEqual(
                len(list(root.glob("command_*.wav"))),
                5,
            )


if __name__ == "__main__":
    unittest.main()
