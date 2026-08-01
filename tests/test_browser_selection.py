from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.browser import BrowserAutomationConfig


class BrowserSelectionTests(unittest.TestCase):
    def test_edge_is_default_channel(self) -> None:
        config = BrowserAutomationConfig()

        self.assertEqual(config.browser, "msedge")
        self.assertEqual(
            config.launch_options()["channel"],
            "msedge",
        )
        self.assertEqual(
            config.effective_profile_directory,
            Path("browser_profiles") / "msedge",
        )

    def test_chrome_uses_chrome_channel(self) -> None:
        config = BrowserAutomationConfig(
            browser="chrome"
        )

        self.assertEqual(
            config.launch_options()["channel"],
            "chrome",
        )
        self.assertEqual(
            config.effective_profile_directory,
            Path("browser_profiles") / "chrome",
        )

    def test_custom_browser_uses_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = (
                Path(directory) / "brave.exe"
            )
            executable.write_bytes(b"fake")

            config = BrowserAutomationConfig(
                browser="custom",
                executable_path=executable,
            )
            options = config.launch_options()

            self.assertEqual(
                Path(options["executable_path"]),
                executable.resolve(),
            )
            self.assertEqual(
                config.profile_key,
                "custom-brave",
            )

    def test_custom_requires_executable(self) -> None:
        with self.assertRaises(ValueError):
            BrowserAutomationConfig(
                browser="custom"
            )

    def test_non_custom_rejects_executable(self) -> None:
        with self.assertRaises(ValueError):
            BrowserAutomationConfig(
                browser="msedge",
                executable_path=Path("edge.exe"),
            )

    def test_chromium_has_no_channel_or_custom_path(self) -> None:
        config = BrowserAutomationConfig(
            browser="chromium"
        )
        options = config.launch_options()

        self.assertNotIn("channel", options)
        self.assertNotIn("executable_path", options)


if __name__ == "__main__":
    unittest.main()
