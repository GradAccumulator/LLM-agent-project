from __future__ import annotations

import unittest

from src.app.cli import parse_args


class ConfirmationConfigTests(
    unittest.TestCase
):
    def test_defaults(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertTrue(
            args.confirmation_enabled
        )
        self.assertEqual(
            args.confirmation_timeout,
            60.0,
        )
        self.assertEqual(
            args.confirmation_code_digits,
            4,
        )
        self.assertEqual(
            args.confirmation_max_attempts,
            3,
        )

    def test_can_disable(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--disable-confirmation",
            ]
        )
        self.assertFalse(
            args.confirmation_enabled
        )


if __name__ == "__main__":
    unittest.main()
