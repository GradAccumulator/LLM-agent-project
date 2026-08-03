from __future__ import annotations

import unittest

from src.app.cli import parse_args
from src.windows_uia import WindowsUiAutomationConfig


class WindowsUiAutomationConfigTests(unittest.TestCase):
    def test_defaults(self):
        args, _ = parse_args(["--print-config"])
        self.assertTrue(args.windows_uia_enabled)
        self.assertTrue(args.windows_uia_allow_actions)
        self.assertEqual(args.windows_uia_backend, "uia")
        self.assertEqual(args.windows_uia_element_ttl, 180.0)
        self.assertEqual(args.windows_uia_max_elements, 200)

    def test_actions_can_be_disabled(self):
        args, _ = parse_args([
            "--print-config",
            "--disable-windows-uia-actions",
        ])
        self.assertFalse(args.windows_uia_allow_actions)

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            WindowsUiAutomationConfig(max_elements=5)


if __name__ == "__main__":
    unittest.main()
