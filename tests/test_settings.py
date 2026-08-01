from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.app.cli import build_parser
from src.settings import ConfigError, load_settings


class SettingsTests(unittest.TestCase):
    def test_precedence_and_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default = root / "default.toml"
            user = root / "user.toml"
            custom = root / "custom.toml"

            default.write_text(
                """
[wakeword]
threshold = 0.45
[tts]
enabled = true
rate_percent = 0
""",
                encoding="utf-8",
            )
            user.write_text(
                """
[wakeword]
threshold = 0.50
[tts]
rate_percent = 4
""",
                encoding="utf-8",
            )
            custom.write_text(
                """
[wakeword]
threshold = 0.55
""",
                encoding="utf-8",
            )

            loaded = load_settings(
                default_path=default,
                user_path=user,
                custom_path=custom,
            )

            self.assertEqual(
                loaded.argument_defaults[
                    "wake_threshold"
                ],
                0.55,
            )
            self.assertEqual(
                loaded.argument_defaults[
                    "tts_rate"
                ],
                4,
            )
            self.assertTrue(
                loaded.argument_defaults[
                    "tts_enabled"
                ]
            )

    def test_unknown_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory) / "default.toml"
            )
            path.write_text(
                """
[stt]
imaginary_option = 123
""",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_settings(
                    default_path=path,
                    load_user=False,
                )

    def test_cli_overrides_toml_default(self) -> None:
        parser = build_parser(
            {
                "wake_threshold": 0.55,
                "tts_enabled": True,
            }
        )
        args = parser.parse_args(
            [
                "--wake-threshold",
                "0.70",
                "--disable-tts",
            ]
        )

        self.assertEqual(
            args.wake_threshold,
            0.70,
        )
        self.assertFalse(args.tts_enabled)


if __name__ == "__main__":
    unittest.main()
