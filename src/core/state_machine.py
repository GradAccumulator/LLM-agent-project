from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from time import monotonic
from typing import Callable, Iterable


class AgentState(str, Enum):
    STARTING = 'STARTING'
    SLEEPING = 'SLEEPING'
    AWAITING_SPEECH = 'AWAITING_SPEECH'
    CAPTURING = 'CAPTURING'
    TRANSCRIBING = 'TRANSCRIBING'
    THINKING = 'THINKING'
    EXECUTING_TOOL = 'EXECUTING_TOOL'
    SPEAKING = 'SPEAKING'
    ERROR = 'ERROR'
    RECOVERING = 'RECOVERING'
    STOPPED = 'STOPPED'


@dataclass(frozen=True, slots=True)
class StateTransition:
    previous: AgentState
    current: AgentState
    reason: str
    occurred_at: datetime
    previous_state_seconds: float


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    current: AgentState
    entered_at: datetime
    elapsed_seconds: float
    transition_count: int


class InvalidStateTransition(RuntimeError):
    pass


StateListener = Callable[[StateTransition], None]


def _build_allowed_transitions() -> dict[AgentState, frozenset[AgentState]]:
    normal: dict[AgentState, set[AgentState]] = {
        AgentState.STARTING: {AgentState.SLEEPING},
        AgentState.SLEEPING: {AgentState.AWAITING_SPEECH},
        AgentState.AWAITING_SPEECH: {AgentState.CAPTURING, AgentState.SLEEPING},
        AgentState.CAPTURING: {AgentState.TRANSCRIBING},
        AgentState.TRANSCRIBING: {
            AgentState.THINKING,
            AgentState.EXECUTING_TOOL,
            AgentState.SPEAKING,
            AgentState.AWAITING_SPEECH,
            AgentState.SLEEPING,
        },
        AgentState.THINKING: {
            AgentState.EXECUTING_TOOL,
            AgentState.SPEAKING,
            AgentState.AWAITING_SPEECH,
            AgentState.SLEEPING,
        },
        AgentState.EXECUTING_TOOL: {
            AgentState.THINKING,
            AgentState.SPEAKING,
            AgentState.AWAITING_SPEECH,
            AgentState.SLEEPING,
        },
        AgentState.SPEAKING: {
            AgentState.CAPTURING,
            AgentState.AWAITING_SPEECH,
            AgentState.SLEEPING,
        },
        AgentState.ERROR: {AgentState.RECOVERING},
        AgentState.RECOVERING: {AgentState.SLEEPING},
        AgentState.STOPPED: set(),
    }
    for state in AgentState:
        if state not in {AgentState.ERROR, AgentState.STOPPED}:
            normal[state].add(AgentState.ERROR)
        if state is not AgentState.STOPPED:
            normal[state].add(AgentState.STOPPED)
    return {state: frozenset(targets) for state, targets in normal.items()}


_ALLOWED_TRANSITIONS = _build_allowed_transitions()


class AgentStateMachine:
    def __init__(
        self,
        *,
        initial: AgentState = AgentState.STARTING,
        history_limit: int = 256,
        listeners: Iterable[StateListener] = (),
    ) -> None:
        if history_limit <= 0:
            raise ValueError('history_limit must be positive.')
        self._lock = RLock()
        self._current = initial
        self._entered_monotonic = monotonic()
        self._entered_at = datetime.now().astimezone()
        self._history: deque[StateTransition] = deque(maxlen=history_limit)
        self._listeners: list[StateListener] = list(listeners)

    @property
    def current(self) -> AgentState:
        with self._lock:
            return self._current

    @property
    def history(self) -> tuple[StateTransition, ...]:
        with self._lock:
            return tuple(self._history)

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                current=self._current,
                entered_at=self._entered_at,
                elapsed_seconds=monotonic() - self._entered_monotonic,
                transition_count=len(self._history),
            )

    def add_listener(self, listener: StateListener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: StateListener) -> None:
        with self._lock:
            self._listeners.remove(listener)

    def can_transition(self, target: AgentState) -> bool:
        with self._lock:
            return target in _ALLOWED_TRANSITIONS[self._current]

    def transition(self, target: AgentState, *, reason: str) -> StateTransition:
        reason = reason.strip() or 'unspecified'
        with self._lock:
            previous = self._current
            if target is previous:
                raise InvalidStateTransition(f'State is already {target.value}.')
            allowed = _ALLOWED_TRANSITIONS[previous]
            if target not in allowed:
                allowed_text = ', '.join(
                    state.value for state in sorted(allowed, key=lambda item: item.value)
                ) or '<none>'
                raise InvalidStateTransition(
                    f'Invalid transition {previous.value} -> {target.value}. '
                    f'Allowed: {allowed_text}.'
                )
            now_monotonic = monotonic()
            occurred_at = datetime.now().astimezone()
            transition = StateTransition(
                previous=previous,
                current=target,
                reason=reason,
                occurred_at=occurred_at,
                previous_state_seconds=now_monotonic - self._entered_monotonic,
            )
            self._current = target
            self._entered_monotonic = now_monotonic
            self._entered_at = occurred_at
            self._history.append(transition)
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(transition)
        return transition

    def stop(self, *, reason: str) -> StateTransition | None:
        with self._lock:
            if self._current is AgentState.STOPPED:
                return None
        return self.transition(AgentState.STOPPED, reason=reason)
