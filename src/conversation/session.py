from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ConversationConfig:
    enabled: bool = True
    followup_timeout_seconds: float = 12.0
    max_turns: int = 8

    def __post_init__(self) -> None:
        if self.followup_timeout_seconds <= 0:
            raise ValueError('followup_timeout_seconds must be positive.')
        if self.max_turns <= 0:
            raise ValueError('max_turns must be positive.')


@dataclass(frozen=True, slots=True)
class ConversationSnapshot:
    active: bool
    session_id: str | None
    turn_count: int
    elapsed_seconds: float
    remaining_turns: int


class ConversationSession:
    """Tracks one wake-word-activated conversation window."""

    def __init__(self, config: ConversationConfig) -> None:
        self.config = config
        self._active = False
        self._session_id: str | None = None
        self._turn_count = 0
        self._started_at = 0.0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def next_turn_index(self) -> int:
        return self._turn_count + 1

    @property
    def can_accept_followup(self) -> bool:
        return (
            self.config.enabled
            and self._active
            and self._turn_count < self.config.max_turns
        )

    def start(self) -> str:
        if self._active:
            raise RuntimeError('A conversation session is already active.')
        self._active = True
        self._session_id = uuid4().hex
        self._turn_count = 0
        self._started_at = monotonic()
        return self._session_id

    def complete_turn(self) -> int:
        if not self._active:
            raise RuntimeError('Cannot complete a turn without an active session.')
        self._turn_count += 1
        return self._turn_count

    def snapshot(self) -> ConversationSnapshot:
        elapsed = monotonic() - self._started_at if self._active else 0.0
        return ConversationSnapshot(
            active=self._active,
            session_id=self._session_id,
            turn_count=self._turn_count,
            elapsed_seconds=elapsed,
            remaining_turns=max(0, self.config.max_turns - self._turn_count),
        )

    def end(self) -> ConversationSnapshot:
        snapshot = self.snapshot()
        self._active = False
        self._session_id = None
        self._turn_count = 0
        self._started_at = 0.0
        return snapshot
