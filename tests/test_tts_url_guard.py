from __future__ import annotations

import unittest

from src.console_io import (
    sanitize_tts_chunk,
)
from src.streaming import (
    IncrementalSentenceChunker,
    SentenceChunkerConfig,
)
from src.tts.synthesizer import (
    clean_for_speech,
)


class TtsUrlGuardTests(unittest.TestCase):
    def test_raw_url_is_removed_not_spoken_as_link(self) -> None:
        cleaned = clean_for_speech(
            "확인했습니다. https://example.com/a"
        )

        self.assertEqual(
            cleaned,
            "확인했습니다.",
        )
        self.assertNotIn(
            "링크",
            cleaned,
        )

    def test_schemeless_domain_fragment_is_removed(self) -> None:
        cleaned = sanitize_tts_chunk(
            "coupang.com/vp/products/9153590867"
        )

        self.assertEqual(
            cleaned,
            "",
        )

    def test_split_path_fragment_is_removed(self) -> None:
        cleaned = sanitize_tts_chunk(
            "/vp/products/9153590867"
            "/items/123?utm_source=openai"
        )

        self.assertEqual(
            cleaned,
            "",
        )

    def test_query_fragment_is_removed(self) -> None:
        cleaned = sanitize_tts_chunk(
            "utm_source=openai"
        )

        self.assertEqual(
            cleaned,
            "",
        )

    def test_domain_dot_is_not_sentence_boundary(self) -> None:
        chunker = IncrementalSentenceChunker(
            SentenceChunkerConfig(
                minimum_characters=8,
                maximum_characters=200,
            )
        )

        first = chunker.feed(
            "자세한 내용은 https://www."
        )
        second = chunker.feed(
            "example.com에서 확인할 수 있습니다. "
        )

        self.assertEqual(
            first,
            (),
        )
        self.assertEqual(
            second,
            (
                "자세한 내용은 "
                "https://www.example.com에서 "
                "확인할 수 있습니다.",
            ),
        )

    def test_meaningful_text_survives_link_removal(self) -> None:
        cleaned = clean_for_speech(
            "자세한 내용은 "
            "[OpenAI 공식 문서]"
            "(https://example.com/docs)를 "
            "확인했습니다."
        )

        self.assertEqual(
            cleaned,
            "자세한 내용은 OpenAI 공식 문서를 "
            "확인했습니다.",
        )


if __name__ == "__main__":
    unittest.main()
