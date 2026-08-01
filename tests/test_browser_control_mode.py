from __future__ import annotations

import unittest

from src.app.cli import parse_args
from src.browser import (
    BrowserAutomationConfig,
    SystemBrowserController,
)
from src.tools import build_default_tool_registry


class BrowserControlModeTests(unittest.TestCase):
    def test_default_mode_is_system(self) -> None:
        args, _ = parse_args(["--print-config"])
        self.assertEqual(
            args.browser_control_mode,
            "system",
        )

    def test_system_tools_registered(self) -> None:
        registry = build_default_tool_registry(
            BrowserAutomationConfig(
                browser="msedge"
            ),
            browser_control_mode="system",
        )
        try:
            self.assertIn(
                "close_jarvis_browser_window",
                registry.names,
            )
            self.assertIn(
                "list_jarvis_browser_windows",
                registry.names,
            )
        finally:
            registry.close()

    def test_controller_name(self) -> None:
        controller = SystemBrowserController(
            BrowserAutomationConfig(
                browser="msedge"
            )
        )
        self.assertEqual(
            controller.browser_name,
            "Microsoft Edge",
        )


if __name__ == "__main__":
    unittest.main()
