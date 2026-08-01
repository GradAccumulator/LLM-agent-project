from __future__ import annotations

import unittest

from src.core import (
    AgentState,
    AgentStateMachine,
    InvalidStateTransition,
)


class AgentStateMachineTests(unittest.TestCase):
    def test_normal_voice_cycle(self) -> None:
        machine = AgentStateMachine()

        sequence = (
            AgentState.LISTENING,
            AgentState.CAPTURING,
            AgentState.TRANSCRIBING,
            AgentState.THINKING,
            AgentState.EXECUTING_TOOL,
            AgentState.THINKING,
            AgentState.SPEAKING,
            AgentState.LISTENING,
            AgentState.STOPPED,
        )

        for state in sequence:
            machine.transition(state, reason="test")

        self.assertEqual(machine.current, AgentState.STOPPED)
        self.assertEqual(len(machine.history), len(sequence))

    def test_invalid_transition_is_rejected(self) -> None:
        machine = AgentStateMachine()

        with self.assertRaises(InvalidStateTransition):
            machine.transition(
                AgentState.SPEAKING,
                reason="cannot speak before startup",
            )

    def test_error_recovery_path(self) -> None:
        machine = AgentStateMachine()
        machine.transition(AgentState.LISTENING, reason="ready")
        machine.transition(AgentState.CAPTURING, reason="wake")
        machine.transition(AgentState.ERROR, reason="failure")
        machine.transition(AgentState.RECOVERING, reason="reset")
        machine.transition(AgentState.LISTENING, reason="recovered")

        self.assertEqual(machine.current, AgentState.LISTENING)

    def test_listener_receives_transition(self) -> None:
        observed = []
        machine = AgentStateMachine(listeners=[observed.append])
        event = machine.transition(
            AgentState.LISTENING,
            reason="ready",
        )

        self.assertEqual(observed, [event])
        self.assertEqual(event.previous, AgentState.STARTING)
        self.assertEqual(event.current, AgentState.LISTENING)


if __name__ == "__main__":
    unittest.main()
