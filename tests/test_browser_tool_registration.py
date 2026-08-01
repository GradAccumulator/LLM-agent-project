from __future__ import annotations

import unittest

from src.browser import BrowserAutomationConfig
from src.tools import build_default_tool_registry


class BrowserToolRegistrationTests(unittest.TestCase):
    def test_browser_tools_registered_without_starting_browser(self) -> None:
        registry = build_default_tool_registry(
            BrowserAutomationConfig(enabled=False)
        )
        expected = {
            "browser_open_page",
            "browser_get_page_info",
            "browser_list_elements",
            "browser_click_text",
            "browser_fill_field",
            "browser_press_key",
            "browser_go_back",
            "browser_close",
        }
        self.assertTrue(expected.issubset(set(registry.names)))
        registry.close()


if __name__ == "__main__":
    unittest.main()
