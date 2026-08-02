from __future__ import annotations

import unittest

from src.llm import AgentConfig, JarvisAgent


class _Registry:
    names = (
        "search_browser",
        "get_current_datetime",
    )
    schemas = [
        {
            "type": "function",
            "name": "search_browser",
        },
        {
            "type": "function",
            "name": "get_current_datetime",
        },
    ]


class AgentHostedWebSearchTests(unittest.TestCase):
    def _agent(
        self,
        *,
        allow_browser_search: bool,
    ) -> JarvisAgent:
        agent = JarvisAgent.__new__(
            JarvisAgent
        )
        agent.config = AgentConfig(
            web_search_enabled=True,
            web_search_external_access=True,
        )
        agent._tool_registry = _Registry()
        agent._allow_local_browser_search = (
            allow_browser_search
        )
        return agent

    def test_hosted_search_is_added(self) -> None:
        tools = self._agent(
            allow_browser_search=False
        )._request_tools()

        self.assertIn(
            {
                "type": "web_search",
                "external_web_access": True,
            },
            tools,
        )

    def test_local_search_browser_is_hidden_by_default(self) -> None:
        tools = self._agent(
            allow_browser_search=False
        )._request_tools()

        self.assertNotIn(
            "search_browser",
            {
                tool.get("name")
                for tool in tools
            },
        )
        self.assertIn(
            "get_current_datetime",
            {
                tool.get("name")
                for tool in tools
            },
        )

    def test_explicit_browser_request_exposes_local_search(self) -> None:
        tools = self._agent(
            allow_browser_search=True
        )._request_tools()

        self.assertIn(
            "search_browser",
            {
                tool.get("name")
                for tool in tools
            },
        )

    def test_browser_intent_detection(self) -> None:
        self.assertFalse(
            JarvisAgent
            ._explicit_browser_search_requested(
                "오늘 AI 뉴스 검색해서 알려줘"
            )
        )
        self.assertTrue(
            JarvisAgent
            ._explicit_browser_search_requested(
                "브라우저 검색창에 AI 뉴스 띄워줘"
            )
        )
        self.assertTrue(
            JarvisAgent
            ._explicit_browser_search_requested(
                "구글에서 AI 뉴스 검색해줘"
            )
        )


if __name__ == "__main__":
    unittest.main()
