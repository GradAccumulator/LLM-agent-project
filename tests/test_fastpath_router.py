from __future__ import annotations

import unittest

from src.fastpath import LocalCommandRouter
from src.tools import ToolRegistry, ToolSpec


def _empty() -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


class FastPathRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = []
        registry = ToolRegistry()

        def register(name, handler, parameters=None):
            registry.register(
                ToolSpec(
                    name=name,
                    description="test",
                    parameters=parameters or _empty(),
                    handler=handler,
                )
            )

        register(
            "get_current_datetime",
            lambda: {
                "time": "10:31:00",
                "date": "2026-08-01",
            },
        )
        register(
            "open_application",
            lambda application: (
                self.calls.append(("app", application))
                or {"application": application}
            ),
            {
                "type": "object",
                "properties": {"application": {"type": "string"}},
                "required": ["application"],
                "additionalProperties": False,
            },
        )
        register(
            "search_browser",
            lambda engine, query: (
                self.calls.append((engine, query))
                or {"engine": engine, "query": query}
            ),
            {
                "type": "object",
                "properties": {
                    "engine": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["engine", "query"],
                "additionalProperties": False,
            },
        )
        self.router = LocalCommandRouter(registry)

    def test_time_bypasses_gpt(self) -> None:
        result = self.router.try_execute("지금 몇 시야")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertIn("10:31:00", result.reply)

    def test_application_open(self) -> None:
        result = self.router.try_execute("계산기 켜줘")
        self.assertIsNotNone(result)
        self.assertEqual(self.calls, [("app", "calculator")])

    def test_search_command(self) -> None:
        result = self.router.try_execute(
            "구글에서 Faster Whisper 검색해줘"
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            self.calls,
            [("google", "Faster Whisper")],
        )

    def test_ambiguous_command_falls_through_to_gpt(self) -> None:
        result = self.router.try_execute(
            "요즘 좋은 브라우저가 뭔지 비교해줘"
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
