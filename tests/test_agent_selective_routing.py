from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from src.llm import AgentConfig, JarvisAgent
from src.model_routing import (
    ModelRoutingConfig,
    SelectiveModelDelegate,
)


class _Responses:
    def create(self, **kwargs):
        return SimpleNamespace(
            model=kwargs["model"],
            output_text="전문 판단",
            usage=None,
        )


class _Client:
    responses = _Responses()


class _Registry:
    names = ("get_current_datetime",)
    schemas = [
        {
            "type": "function",
            "name": "get_current_datetime",
        }
    ]

    def begin_request(self, **kwargs):
        del kwargs


class AgentSelectiveRoutingTests(unittest.TestCase):
    def _agent(self) -> JarvisAgent:
        agent = JarvisAgent.__new__(JarvisAgent)
        agent.config = AgentConfig(
            model_routing=ModelRoutingConfig(),
            web_search_enabled=False,
        )
        agent._client = _Client()
        agent._tool_registry = _Registry()
        agent._model_delegate = SelectiveModelDelegate(
            client=agent._client,
            base_model=agent.config.model,
            config=agent.config.model_routing,
        )
        agent._allow_local_browser_search = False
        agent._memory_store = None
        agent._request_instructions = agent.config.instructions
        return agent

    def test_delegate_tool_is_exposed(self) -> None:
        agent = self._agent()
        agent._model_delegate.begin_turn("검토해줘")
        names = {
            tool.get("name")
            for tool in agent._request_tools()
        }
        self.assertIn("delegate_reasoning", names)

    def test_explicit_request_forces_delegate(self) -> None:
        agent = self._agent()
        agent._model_delegate.begin_turn(
            "강한 모델로 판단해줘"
        )
        self.assertEqual(
            agent._request_tool_choice(),
            {
                "type": "function",
                "name": "delegate_reasoning",
            },
        )

    def test_delegate_execution_is_internal(self) -> None:
        agent = self._agent()
        agent._model_delegate.begin_turn(
            "강한 모델로 판단해줘"
        )
        result = agent._execute_function_call(
            tool_name="delegate_reasoning",
            arguments_json=json.dumps(
                {
                    "task": "후보 검토",
                    "relevant_context": "A, B",
                    "reason": "충돌",
                    "target_tier": "strong",
                    "output_format": "결론",
                }
            ),
        )
        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertTrue(payload["judgment_only"])
        self.assertEqual(
            payload["model"],
            "gpt-5.6-sol",
        )


if __name__ == "__main__":
    unittest.main()
