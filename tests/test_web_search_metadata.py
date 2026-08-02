from __future__ import annotations

import unittest

from src.llm.web_search import (
    extract_web_search_metadata,
    merge_web_search_metadata,
)


class WebSearchMetadataTests(unittest.TestCase):
    def test_extracts_queries_and_sources(self) -> None:
        response = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "type": "search",
                        "queries": [
                            "latest AI news",
                            "OpenAI news",
                        ],
                        "sources": [
                            {
                                "type": "computer_initialize_state",
                                "title": "Source A",
                                "url": "https://example.com/a",
                            }
                        ],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "answer",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "Source B",
                                    "url": "https://example.com/b",
                                },
                                {
                                    "type": "url_citation",
                                    "title": "Duplicate",
                                    "url": "https://example.com/a",
                                },
                            ],
                        }
                    ],
                },
            ]
        }

        metadata = extract_web_search_metadata(
            response
        )

        self.assertEqual(
            metadata.call_count,
            1,
        )
        self.assertEqual(
            metadata.queries,
            (
                "latest AI news",
                "OpenAI news",
            ),
        )
        self.assertEqual(
            [source.url for source in metadata.sources],
            [
                "https://example.com/a",
                "https://example.com/b",
            ],
        )

    def test_merge_deduplicates_sources(self) -> None:
        first = extract_web_search_metadata(
            {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "query": "one",
                            "sources": [
                                {
                                    "url": "https://example.com",
                                    "title": "Example",
                                }
                            ],
                        },
                    }
                ]
            }
        )
        second = extract_web_search_metadata(
            {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "query": "two",
                            "sources": [
                                {
                                    "url": "https://example.com",
                                    "title": "Example",
                                }
                            ],
                        },
                    }
                ]
            }
        )

        merged = merge_web_search_metadata(
            [first, second]
        )

        self.assertEqual(
            merged.call_count,
            2,
        )
        self.assertEqual(
            merged.queries,
            ("one", "two"),
        )
        self.assertEqual(
            len(merged.sources),
            1,
        )


if __name__ == "__main__":
    unittest.main()
