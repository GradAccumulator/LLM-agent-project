from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from src.llm.agent import JarvisAgent


@dataclass
class _Event:
    type: str
    delta: str = ""
    item: object | None = None
    response: object | None = None


class _Stream:
    def __init__(self, events) -> None:
        self._events = events
        self.closed = False

    def __iter__(self):
        return iter(self._events)

    def close(self) -> None:
        self.closed = True


class LlmStreamEventTests(unittest.TestCase):
    def _agent_with_stream(self, events):
        agent = JarvisAgent.__new__(JarvisAgent)
        stream = _Stream(events)
        agent._create_response_stream = (
            lambda **kwargs: stream
        )
        return agent, stream

    def test_text_deltas_are_forwarded(self) -> None:
        response = SimpleNamespace()
        agent, stream = self._agent_with_stream(
            [
                _Event(
                    "response.output_text.delta",
                    delta="안녕",
                ),
                _Event(
                    "response.output_text.delta",
                    delta="하세요.",
                ),
                _Event(
                    "response.completed",
                    response=response,
                ),
            ]
        )
        deltas: list[str] = []

        final, first, emitted = (
            agent._consume_response_stream(
                input_items=[],
                previous_response_id=None,
                request_started_at=0.0,
                on_text_delta=deltas.append,
                on_text_cancel=None,
            )
        )

        self.assertIs(final, response)
        self.assertEqual(
            deltas,
            ["안녕", "하세요."],
        )
        self.assertTrue(emitted)
        self.assertIsNotNone(first)
        self.assertTrue(stream.closed)

    def test_function_call_cancels_provisional_text(self) -> None:
        response = SimpleNamespace()
        function_item = SimpleNamespace(
            type="function_call"
        )
        agent, _ = self._agent_with_stream(
            [
                _Event(
                    "response.output_text.delta",
                    delta="확인해볼게요.",
                ),
                _Event(
                    "response.output_item.added",
                    item=function_item,
                ),
                _Event(
                    "response.completed",
                    response=response,
                ),
            ]
        )
        cancellations: list[bool] = []

        agent._consume_response_stream(
            input_items=[],
            previous_response_id=None,
            request_started_at=0.0,
            on_text_delta=lambda _: None,
            on_text_cancel=lambda: (
                cancellations.append(True)
            ),
        )

        self.assertEqual(
            cancellations,
            [True],
        )


if __name__ == "__main__":
    unittest.main()
