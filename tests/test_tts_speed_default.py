from __future__ import annotations

import unittest

from src.app.cli import parse_args
from src.tts import (
    SpeechSynthesizerConfig,
)


class TtsSpeedDefaultTests(
    unittest.TestCase
):
    def test_default_is_plus_fifty_percent(
        self,
    ) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertEqual(
            args.tts_rate,
            50,
        )
        self.assertEqual(
            SpeechSynthesizerConfig().rate,
            50,
        )

    def test_cli_can_override_speed(
        self,
    ) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--tts-rate",
                "20",
            ]
        )
        self.assertEqual(
            args.tts_rate,
            20,
        )


if __name__ == "__main__":
    unittest.main()
