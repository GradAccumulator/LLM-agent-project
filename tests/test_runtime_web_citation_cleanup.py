from __future__ import annotations

import unittest

from src.app.runtime import (
    VoiceAssistantRuntime,
)
from src.llm import AgentReply


class RuntimeWebCitationCleanupTests(
    unittest.TestCase
):
    def _reply(
        self,
        *,
        text: str,
        web_search_calls: int,
    ) -> AgentReply:
        return AgentReply(
            text=text,
            response_id="response",
            model="test-model",
            elapsed_seconds=0.1,
            first_text_seconds=0.01,
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            tool_calls=(),
            web_search_calls=web_search_calls,
        )

    def test_hosted_search_reply_is_cleaned(self) -> None:
        reply = self._reply(
            text=(
                "답변입니다. "
                "([example.com]"
                "(https://example.com))"
            ),
            web_search_calls=1,
        )

        cleaned = (
            VoiceAssistantRuntime
            ._sanitize_agent_reply(reply)
        )

        self.assertEqual(
            cleaned.text,
            "답변입니다.",
        )

    def test_non_search_reply_is_unchanged(self) -> None:
        reply = self._reply(
            text=(
                "[문서](https://example.com)"
            ),
            web_search_calls=0,
        )

        cleaned = (
            VoiceAssistantRuntime
            ._sanitize_agent_reply(reply)
        )

        self.assertIs(cleaned, reply)


if __name__ == "__main__":
    unittest.main()
