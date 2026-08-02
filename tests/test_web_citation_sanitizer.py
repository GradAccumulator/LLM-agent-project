from __future__ import annotations

import unittest

from src.console_io import (
    sanitize_tts_chunk,
    sanitize_web_citations,
)


class WebCitationSanitizerTests(
    unittest.TestCase
):
    def test_removes_parenthesized_domain_link(self) -> None:
        text = (
            "네, 알아요. "
            "([coupang.com]"
            "(https://www.coupang.com/item?utm_source=openai))"
        )

        cleaned = sanitize_web_citations(
            text
        )

        self.assertEqual(
            cleaned,
            "네, 알아요.",
        )

    def test_drops_standalone_citation_line(self) -> None:
        text = (
            "첫 번째 문장입니다.\n"
            "([example.com](https://example.com/a))"
        )

        cleaned = sanitize_web_citations(
            text
        )

        self.assertEqual(
            cleaned,
            "첫 번째 문장입니다.",
        )

    def test_preserves_meaningful_link_label(self) -> None:
        text = (
            "[OpenAI 공식 문서]"
            "(https://example.com/docs)를 확인했습니다."
        )

        cleaned = sanitize_web_citations(
            text
        )

        self.assertEqual(
            cleaned,
            "OpenAI 공식 문서를 확인했습니다.",
        )

    def test_removes_raw_url_and_numeric_citation(self) -> None:
        text = (
            "자세한 내용은 https://example.com/a "
            "에서 확인할 수 있습니다. [1]"
        )

        cleaned = sanitize_web_citations(
            text
        )

        self.assertEqual(
            cleaned,
            "자세한 내용은 에서 확인할 수 있습니다.",
        )

    def test_tts_skips_citation_only_chunk(self) -> None:
        chunk = (
            "([coupang.com]"
            "(https://www.coupang.com/product))"
        )

        self.assertEqual(
            sanitize_tts_chunk(chunk),
            "",
        )


if __name__ == "__main__":
    unittest.main()
