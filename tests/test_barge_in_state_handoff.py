from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from src.app.runtime import VoiceAssistantRuntime
from src.bargein import (
    BargeInCapture,
    BargeInResult,
)
from src.conversation import (
    ConversationConfig,
    ConversationSession,
)
from src.core import (
    AgentState,
    AgentStateMachine,
)


class _Metrics:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def log(
        self,
        event: str,
        *,
        data=None,
        private=None,
    ) -> None:
        del private
        self.events.append(
            (event, dict(data or {}))
        )


class _BargeIn:
    def __init__(
        self,
        result: BargeInResult | None = None,
    ) -> None:
        self.triggered = result is not None
        self._result = result
        self.config = SimpleNamespace(
            max_utterance_seconds=12.0,
            end_silence_seconds=0.48,
        )

    def wait_for_result(self, timeout=None):
        del timeout
        return self._result

    def stop(self, timeout=1.0):
        del timeout
        return self._result


def _capture() -> BargeInCapture:
    return BargeInCapture(
        samples=np.zeros(
            1600,
            dtype=np.int16,
        ),
        speech_detected=True,
        duration_seconds=0.1,
        peak_probability=0.91,
        end_reason="barge_in_silence",
    )


def _capturing_state_machine() -> AgentStateMachine:
    machine = AgentStateMachine()
    machine.transition(
        AgentState.SLEEPING,
        reason="test startup",
    )
    machine.transition(
        AgentState.AWAITING_SPEECH,
        reason="test wake",
    )
    machine.transition(
        AgentState.CAPTURING,
        reason="test barge-in",
    )
    return machine


class BargeInStateHandoffTests(unittest.TestCase):
    def _runtime(
        self,
        *,
        max_turns: int,
        pending,
        barge_result=None,
    ):
        runtime = VoiceAssistantRuntime.__new__(
            VoiceAssistantRuntime
        )
        runtime.state = (
            _capturing_state_machine()
        )
        runtime.metrics = _Metrics()
        runtime.conversation = ConversationSession(
            ConversationConfig(
                enabled=True,
                max_turns=max_turns,
            )
        )
        runtime.conversation.start()
        runtime._pending_barge_in_capture = (
            pending
        )
        runtime.barge_in = _BargeIn(
            barge_result
        )
        runtime._active_command = (
            SimpleNamespace(
                command_id="original-command"
            )
        )

        runtime._finish_command = (
            lambda outcome: setattr(
                runtime,
                "_active_command",
                None,
            )
        )
        runtime._start_command = (
            lambda **kwargs: setattr(
                runtime,
                "_active_command",
                SimpleNamespace(
                    capture_audio_seconds=None
                ),
            )
        )
        runtime.processed = []
        runtime._process_capture = (
            lambda capture: (
                runtime.processed.append(
                    capture
                )
            )
        )
        runtime.slept = False
        runtime._return_to_sleep = (
            lambda **kwargs: setattr(
                runtime,
                "slept",
                True,
            )
        )
        runtime._continue_conversation = (
            lambda **kwargs: None
        )
        return runtime

    def test_barge_in_at_turn_limit_rolls_session(self) -> None:
        capture = _capture()
        runtime = self._runtime(
            max_turns=1,
            pending=capture,
        )
        old_session_id = (
            runtime.conversation.session_id
        )

        runtime._after_turn(
            outcome="success"
        )

        self.assertEqual(
            runtime.state.current,
            AgentState.CAPTURING,
        )
        self.assertEqual(
            runtime.processed,
            [capture],
        )
        self.assertFalse(runtime.slept)
        self.assertTrue(
            runtime.conversation.active
        )
        self.assertNotEqual(
            runtime.conversation.session_id,
            old_session_id,
        )
        self.assertEqual(
            runtime.conversation.turn_count,
            0,
        )

    def test_late_monitor_result_is_collected(self) -> None:
        capture = _capture()
        result = BargeInResult(
            capture=capture,
            trigger_latency_seconds=0.42,
        )
        runtime = self._runtime(
            max_turns=4,
            pending=None,
            barge_result=result,
        )

        runtime._after_turn(
            outcome="success"
        )

        self.assertEqual(
            runtime.processed,
            [capture],
        )
        self.assertFalse(runtime.slept)
        self.assertTrue(
            any(
                event == "barge_in_captured"
                and data.get(
                    "late_collection"
                )
                is True
                for event, data
                in runtime.metrics.events
            )
        )


if __name__ == "__main__":
    unittest.main()
