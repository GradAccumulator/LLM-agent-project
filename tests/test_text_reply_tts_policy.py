from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.app.runtime import VoiceAssistantRuntime


class TextReplyTtsPolicyTests(unittest.TestCase):
    def test_text_reply_does_not_call_tts(self) -> None:
        runtime = VoiceAssistantRuntime.__new__(
            VoiceAssistantRuntime
        )
        runtime._active_command = SimpleNamespace(
            reply=None
        )
        runtime.tts_enabled = True
        runtime._speak = lambda text: self.fail(
            f"TTS was called for text reply: {text}"
        )

        with patch(
            "src.app.runtime.print_numbered_reply"
        ) as output:
            runtime._local_reply(
                "텍스트 답변",
                speak_response=False,
            )

        output.assert_called_once_with(
            "텍스트 답변"
        )
        self.assertEqual(
            runtime._active_command.reply,
            "텍스트 답변",
        )


if __name__ == "__main__":
    unittest.main()
