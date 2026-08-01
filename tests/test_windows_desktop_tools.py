from __future__ import annotations

import sys
import unittest

from src.tools import build_default_tool_registry
from src.tools.windows_desktop import get_active_window


class WindowsDesktopToolTests(unittest.TestCase):
    def test_tools_are_registered(self) -> None:
        registry = build_default_tool_registry()
        expected = {
            "get_active_window",
            "list_open_windows",
            "focus_window",
            "set_window_state",
            "media_control",
            "get_clipboard_text",
            "set_clipboard_text",
        }
        self.assertTrue(expected.issubset(set(registry.names)))

    @unittest.skipIf(sys.platform == "win32", "Non-Windows safety test")
    def test_non_windows_is_blocked(self) -> None:
        with self.assertRaises(RuntimeError):
            get_active_window()


if __name__ == "__main__":
    unittest.main()
