from __future__ import annotations

import unittest

from src.console_io import (
    format_numbered_reply,
    split_reply_units,
)


class ConsoleReplyFormatTests(unittest.TestCase):
    def test_sentences_are_numbered_on_separate_lines(self) -> None:
        text = "첫 문장입니다. 둘째 문장입니다! 셋째인가요?"
        units = split_reply_units(text)
        rendered = format_numbered_reply(text)

        self.assertEqual(len(units), 3)
        self.assertIn("JARVIS | 1/3 |", rendered)
        self.assertIn("| 2/3 |", rendered)
        self.assertIn("| 3/3 |", rendered)
        self.assertEqual(rendered.count("\n"), 2)

    def test_code_block_is_kept_as_one_unit(self) -> None:
        text = "설명입니다.\n```python\nprint('x')\n```"
        units = split_reply_units(text)
        self.assertEqual(len(units), 2)
        self.assertTrue(units[1].startswith("```python"))


if __name__ == "__main__":
    unittest.main()
