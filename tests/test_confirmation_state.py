from __future__ import annotations

import unittest

from src.core import (
    AgentState,
    AgentStateMachine,
)


class ConfirmationStateTests(
    unittest.TestCase
):
    def test_confirmation_voice_cycle(
        self,
    ) -> None:
        state = AgentStateMachine(
            initial=AgentState.THINKING
        )

        state.transition(
            AgentState.AWAITING_CONFIRMATION,
            reason="approval required",
        )
        state.transition(
            AgentState.CAPTURING,
            reason="approval speech",
        )
        state.transition(
            AgentState.TRANSCRIBING,
            reason="captured",
        )
        state.transition(
            AgentState.EXECUTING_TOOL,
            reason="approved action",
        )

        self.assertEqual(
            state.current,
            AgentState.EXECUTING_TOOL,
        )

    def test_confirmation_text_cycle(
        self,
    ) -> None:
        state = AgentStateMachine(
            initial=(
                AgentState
                .AWAITING_CONFIRMATION
            )
        )
        state.transition(
            AgentState.TEXT_INPUT,
            reason="typed approval",
        )
        state.transition(
            AgentState.EXECUTING_TOOL,
            reason="approved action",
        )
        self.assertEqual(
            state.current,
            AgentState.EXECUTING_TOOL,
        )


if __name__ == "__main__":
    unittest.main()
