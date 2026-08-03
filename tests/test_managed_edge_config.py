from __future__ import annotations

from pathlib import Path
import unittest

from src.app.cli import parse_args


class ManagedEdgeConfigTests(
    unittest.TestCase
):
    def test_defaults(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertTrue(
            args.edge_cdp_auto_start
        )
        self.assertEqual(
            args.edge_cdp_profile_dir,
            Path("data/edge_profile"),
        )
        self.assertTrue(
            args.edge_cdp_restore_session
        )
        self.assertTrue(
            args.edge_cdp_keep_running
        )

    def test_can_disable_auto_start(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--disable-edge-cdp-auto-start",
            ]
        )
        self.assertFalse(
            args.edge_cdp_auto_start
        )


if __name__ == "__main__":
    unittest.main()
