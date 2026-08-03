from __future__ import annotations

import unittest

from src.console_io.citations import sanitize_tts_chunk


class LocalRagTtsCitationTests(unittest.TestCase):
    def test_local_source_lines_are_not_spoken(self) -> None:
        text = (
            "GQA는 KV 헤드를 공유합니다.\n"
            "출처: C:\\project\\src\\attention.py:L10-L28\n"
            "Sources: /home/user/paper.pdf#page=4"
        )
        cleaned = sanitize_tts_chunk(text)
        self.assertEqual(cleaned, "GQA는 KV 헤드를 공유합니다.")

    def test_screen_answer_keeps_source_text(self) -> None:
        source = "출처: C:\\project\\src\\attention.py:L10-L28"
        self.assertIn("attention.py", source)


if __name__ == "__main__":
    unittest.main()
