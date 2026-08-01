from __future__ import annotations

import unittest

from src.core import AgentState, AgentStateMachine, InvalidStateTransition


class AgentStateMachineTests(unittest.TestCase):
    def test_continuous_conversation_cycle(self) -> None:
        machine = AgentStateMachine()
        sequence = (
            AgentState.SLEEPING,
            AgentState.AWAITING_SPEECH,
            AgentState.CAPTURING,
            AgentState.TRANSCRIBING,
            AgentState.THINKING,
            AgentState.EXECUTING_TOOL,
            AgentState.THINKING,
            AgentState.SPEAKING,
            AgentState.AWAITING_SPEECH,
            AgentState.CAPTURING,
            AgentState.TRANSCRIBING,
            AgentState.THINKING,
            AgentState.SPEAKING,
            AgentState.SLEEPING,
            AgentState.STOPPED,
        )
        for state in sequence:
            machine.transition(state, reason='test')
        self.assertEqual(machine.current, AgentState.STOPPED)

    def test_invalid_transition_is_rejected(self) -> None:
        machine = AgentStateMachine()
        with self.assertRaises(InvalidStateTransition):
            machine.transition(AgentState.SPEAKING, reason='invalid')

    def test_error_recovery_returns_to_sleep(self) -> None:
        machine = AgentStateMachine()
        for state in (
            AgentState.SLEEPING,
            AgentState.AWAITING_SPEECH,
            AgentState.ERROR,
            AgentState.RECOVERING,
            AgentState.SLEEPING,
        ):
            machine.transition(state, reason='test')
        self.assertEqual(machine.current, AgentState.SLEEPING)


if __name__ == '__main__':
    unittest.main()
