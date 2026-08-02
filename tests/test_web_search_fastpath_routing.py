from __future__ import annotations

import unittest

from src.fastpath import LocalCommandRouter


class _Memory:
    enabled = True

    def get_preference(self, key: str):
        del key
        return "google"

    def resolve_alias(self, alias: str):
        del alias
        return None


class _Registry:
    memory_store = _Memory()

    def begin_request(self, **kwargs) -> None:
        del kwargs


class WebSearchFastPathRoutingTests(
    unittest.TestCase
):
    def test_generic_search_falls_through_to_gpt(self) -> None:
        router = LocalCommandRouter(
            _Registry()
        )

        self.assertIsNone(
            router.match(
                "오늘 AI 뉴스 검색해서 알려줘"
            )
        )
        self.assertIsNone(
            router.match(
                "RTX 5090 최신 가격 찾아줘"
            )
        )

    def test_explicit_engine_search_still_opens_browser(self) -> None:
        router = LocalCommandRouter(
            _Registry()
        )

        matched = router.match(
            "구글에서 RTX 5090 검색해줘"
        )

        self.assertIsNotNone(matched)
        self.assertEqual(
            matched.route,
            "search:google",
        )


if __name__ == "__main__":
    unittest.main()
