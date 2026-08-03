from __future__ import annotations

import unittest

from src.app.cli import parse_args


class ModelRoutingConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args, _ = parse_args(["--print-config"])
        self.assertTrue(args.model_routing_enabled)
        self.assertEqual(
            args.routing_balanced_model,
            "gpt-5.6-terra",
        )
        self.assertEqual(
            args.routing_strong_model,
            "gpt-5.6-sol",
        )
        self.assertEqual(
            args.routing_max_delegations,
            1,
        )

    def test_automatic_can_be_disabled(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--disable-routing-automatic",
            ]
        )
        self.assertFalse(
            args.routing_allow_automatic
        )


if __name__ == "__main__":
    unittest.main()
