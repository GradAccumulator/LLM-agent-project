from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.windows_uia import (
    WindowsUiAutomation,
    WindowsUiAutomationConfig,
)


class _Rect:
    left = 10
    top = 20
    right = 310
    bottom = 220


class _Info:
    name = "Settings"
    control_type = "Window"
    automation_id = ""
    class_name = "ApplicationFrameWindow"
    process_id = 123
    offscreen = False
    is_keyboard_focusable = True
    is_password = False


class _Window:
    handle = 99
    element_info = _Info()

    def exists(self, timeout=0):
        return True

    def rectangle(self):
        return _Rect()

    def window_text(self):
        return "Settings"

    def is_enabled(self):
        return True

    def is_visible(self):
        return True

    def has_keyboard_focus(self):
        return True

    def children(self):
        return []


class _Desktop:
    def window(self, *, handle):
        if handle != 99:
            raise RuntimeError()
        return self

    def wrapper_object(self):
        return _Window()


class UiaWindowContextTests(
    unittest.TestCase
):
    def test_capture_returns_image_and_elements(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            def capture(bounds, path):
                self.assertEqual(
                    bounds["width"],
                    300,
                )
                Path(path).write_bytes(
                    b"PNG"
                )
                return path

            controller = WindowsUiAutomation(
                WindowsUiAutomationConfig(
                    screenshot_directory=(
                        Path(temp)
                    )
                ),
                desktop_factory=lambda **_: (
                    _Desktop()
                ),
                platform="win32",
                screenshot_capture=capture,
            )
            result = (
                controller
                .capture_window_context(
                    window_id=99,
                    max_depth=2,
                    limit=20,
                    include_value=False,
                )
            )

            self.assertTrue(
                Path(
                    result["image_path"]
                ).is_file()
            )
            self.assertEqual(
                result["window_id"],
                99,
            )
            self.assertEqual(
                result["element_count"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
