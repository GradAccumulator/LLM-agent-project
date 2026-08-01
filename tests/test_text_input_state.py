from __future__ import annotations

import unittest

from src.core import AgentState, AgentStateMachine


class TextInputStateTests(unittest.TestCase):
    def test_text_command_from_sleep(self) -> None:
        machine = AgentStateMachine()
        machine.transition(
            AgentState.SLEEPING,
            reason="startup",
        )
        machine.transition(
            AgentState.TEXT_INPUT,
            reason="typed line",
        )
        machine.transition(
            AgentState.THINKING,
            reason="ask GPT",
        )
        machine.transition(
            AgentState.AWAITING_SPEECH,
            reason="follow-up",
        )
        self.assertEqual(
            machine.current,
            AgentState.AWAITING_SPEECH,
        )

    def test_text_can_preempt_capture(self) -> None:
        machine = AgentStateMachine()
        machine.transition(
            AgentState.SLEEPING,
            reason="startup",
        )
        machine.transition(
            AgentState.AWAITING_SPEECH,
            reason="wake",
        )
        machine.transition(
            AgentState.CAPTURING,
            reason="speech",
        )
        machine.transition(
            AgentState.TEXT_INPUT,
            reason="typed line",
        )
        self.assertEqual(
            machine.current,
            AgentState.TEXT_INPUT,
        )


if __name__ == "__main__":
    unittest.main()
