from __future__ import annotations

import unittest

from src.app.cli import parse_args


class CalendarWriteConfigTests(
    unittest.TestCase
):
    def test_writes_enabled_by_default(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertTrue(
            args.google_calendar_allow_writes
        )

    def test_writes_can_be_disabled(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--disable-google-calendar-writes",
            ]
        )
        self.assertFalse(
            args.google_calendar_allow_writes
        )


if __name__ == "__main__":
    unittest.main()
