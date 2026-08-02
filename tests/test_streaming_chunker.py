from __future__ import annotations

import unittest

from src.streaming import (
    IncrementalSentenceChunker,
    SentenceChunkerConfig,
)


class StreamingChunkerTests(unittest.TestCase):
    def test_emits_complete_sentences(self) -> None:
        chunker = IncrementalSentenceChunker(
            SentenceChunkerConfig(
                minimum_characters=5,
                maximum_characters=30,
            )
        )

        first = chunker.feed(
            "첫 번째 문장입니다. 두 번째"
        )
        second = chunker.feed(
            " 문장입니다."
        )

        self.assertEqual(
            first,
            ("첫 번째 문장입니다.",),
        )
        self.assertEqual(
            second,
            (),
        )
        self.assertEqual(
            chunker.flush(),
            ("두 번째 문장입니다.",),
        )

    def test_splits_long_unpunctuated_text(self) -> None:
        chunker = IncrementalSentenceChunker(
            SentenceChunkerConfig(
                minimum_characters=4,
                maximum_characters=10,
            )
        )

        chunks = chunker.feed(
            "하나 둘 셋 넷 다섯 여섯"
        )

        self.assertTrue(chunks)
        self.assertLessEqual(
            len(chunks[0]),
            10,
        )

    def test_flush_returns_remainder(self) -> None:
        chunker = IncrementalSentenceChunker(
            SentenceChunkerConfig()
        )
        chunker.feed("남아 있는 문장")

        self.assertEqual(
            chunker.flush(),
            ("남아 있는 문장",),
        )
        self.assertEqual(
            chunker.pending_text,
            "",
        )


if __name__ == "__main__":
    unittest.main()
