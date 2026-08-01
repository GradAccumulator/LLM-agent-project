from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.settings import ConfigError, load_settings


class BrowserConfigSelectionTests(unittest.TestCase):
    def test_edge_config_maps_to_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default.toml"
            path.write_text(
                (
                    '[browser]\n'
                    'enabled = true\n'
                    'headless = false\n'
                    'browser = "msedge"\n'
                    'executable_path = ""\n'
                    'profile_directory = "browser_profiles"\n'
                    'navigation_timeout_seconds = 20.0\n'
                    'action_timeout_seconds = 10.0\n'
                    'max_page_text_characters = 12000\n'
                ),
                encoding="utf-8",
            )

            loaded = load_settings(
                default_path=path,
                load_user=False,
            )

            self.assertEqual(
                loaded.argument_defaults[
                    "browser_selection"
                ],
                "msedge",
            )
            self.assertIsNone(
                loaded.argument_defaults[
                    "browser_executable_path"
                ]
            )

    def test_custom_requires_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default.toml"
            path.write_text(
                (
                    '[browser]\n'
                    'browser = "custom"\n'
                    'executable_path = ""\n'
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_settings(
                    default_path=path,
                    load_user=False,
                )


if __name__ == "__main__":
    unittest.main()
