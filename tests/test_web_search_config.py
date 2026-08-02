from __future__ import annotations

import unittest

from src.app.cli import parse_args


class WebSearchConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args, _ = parse_args(
            ["--print-config"]
        )

        self.assertTrue(
            args.web_search_enabled
        )
        self.assertTrue(
            args.web_search_external_access
        )
        self.assertEqual(
            args.web_search_max_sources,
            5,
        )

    def test_cache_only_override(self) -> None:
        args, _ = parse_args(
            [
                "--print-config",
                "--web-search-cache-only",
            ]
        )

        self.assertFalse(
            args.web_search_external_access
        )


if __name__ == "__main__":
    unittest.main()
