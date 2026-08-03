from __future__ import annotations

import unittest

from src.app.cli import parse_args


class EdgeCdpConfigTests(
    unittest.TestCase
):
    def test_defaults(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )
        self.assertTrue(
            args.edge_cdp_enabled
        )
        self.assertEqual(
            args.edge_cdp_endpoint,
            "http://127.0.0.1:9222",
        )
        self.assertTrue(
            args.edge_cdp_allow_tab_close
        )

    def test_can_disable_tab_close(
        self,
    ) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--disable-edge-cdp-tab-close",
            ]
        )
        self.assertFalse(
            args.edge_cdp_allow_tab_close
        )


if __name__ == "__main__":
    unittest.main()
