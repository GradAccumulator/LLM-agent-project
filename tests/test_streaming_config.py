from __future__ import annotations

import unittest

from src.app.cli import parse_args


class StreamingConfigTests(unittest.TestCase):
    def test_defaults_are_enabled(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )

        self.assertTrue(
            args.streaming_enabled
        )
        self.assertEqual(
            args.streaming_minimum_characters,
            24,
        )
        self.assertEqual(
            args.streaming_maximum_characters,
            160,
        )
        self.assertTrue(
            args.continuous_conversation
        )

    def test_cli_can_disable_streaming(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--disable-streaming",
            ]
        )
        self.assertFalse(
            args.streaming_enabled
        )


if __name__ == "__main__":
    unittest.main()
