from __future__ import annotations

import unittest

from src.browser import BrowserAutomationConfig
from src.tools import build_default_tool_registry


class BrowserFastPathSelectionTests(unittest.TestCase):
    def test_registry_builds_with_edge_selection(self) -> None:
        registry = build_default_tool_registry(
            BrowserAutomationConfig(
                browser="msedge"
            )
        )
        try:
            self.assertIn(
                "open_website",
                registry.names,
            )
            self.assertIn(
                "browser_open_page",
                registry.names,
            )
        finally:
            registry.close()


if __name__ == "__main__":
    unittest.main()
