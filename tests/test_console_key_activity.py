from __future__ import annotations

from collections import deque
from io import StringIO
import unittest

from src.console_io import ConsoleTextInput


class ConsoleKeyActivityTests(unittest.TestCase):
    def _reader(self, characters: str):
        queue = deque(characters)

        def read() -> str:
            return queue.popleft()

        return read

    def test_first_character_is_preserved(self) -> None:
        output = StringIO()
        console = ConsoleTextInput(
            output=output,
            use_windows_key_reader=True,
            key_reader=self._reader("안녕\r"),
        )

        line = console._read_windows_line()

        self.assertEqual(line, "안녕")
        self.assertIn("안녕", output.getvalue())
        self.assertEqual(
            console.activity_sequence,
            2,
        )

    def test_each_edit_increments_activity(self) -> None:
        output = StringIO()
        console = ConsoleTextInput(
            output=output,
            use_windows_key_reader=True,
            key_reader=self._reader("abc\bD\r"),
        )

        line = console._read_windows_line()

        self.assertEqual(line, "abD")
        self.assertEqual(
            console.activity_sequence,
            5,
        )
        self.assertFalse(console.line_has_text)


if __name__ == "__main__":
    unittest.main()
