from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import secrets
from threading import RLock
from time import monotonic
from typing import Any, Callable, Mapping
from uuid import uuid4


class ConfirmationRisk(str, Enum):
    STANDARD = "standard"
    HIGH = "high"


class ConfirmationError(RuntimeError):
    pass


class ConfirmationBusyError(ConfirmationError):
    def __init__(
        self,
        pending: PendingAction,
    ) -> None:
        super().__init__(
            "Another action is already waiting for confirmation."
        )
        self.pending = pending


class ConfirmationCodeError(ConfirmationError):
    def __init__(
        self,
        message: str,
        *,
        remaining_attempts: int,
        cancelled: bool,
    ) -> None:
        super().__init__(message)
        self.remaining_attempts = remaining_attempts
        self.cancelled = cancelled


@dataclass(frozen=True, slots=True)
class ConfirmationConfig:
    enabled: bool = True
    timeout_seconds: float = 60.0
    high_risk_code_digits: int = 4
    max_code_attempts: int = 3

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive."
            )
        if not 4 <= self.high_risk_code_digits <= 8:
            raise ValueError(
                "high_risk_code_digits must be between 4 and 8."
            )
        if not 1 <= self.max_code_attempts <= 10:
            raise ValueError(
                "max_code_attempts must be between 1 and 10."
            )


ConfirmationSummary = Callable[
    [Mapping[str, Any]],
    str,
]


@dataclass(frozen=True, slots=True)
class ConfirmationRequirement:
    summary: ConfirmationSummary
    risk: ConfirmationRisk = (
        ConfirmationRisk.STANDARD
    )
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if (
            self.timeout_seconds is not None
            and self.timeout_seconds <= 0
        ):
            raise ValueError(
                "timeout_seconds must be positive."
            )


@dataclass(frozen=True, slots=True)
class PendingAction:
    action_id: str
    tool_name: str
    arguments: dict[str, Any]
    summary: str
    risk: ConfirmationRisk
    created_at: datetime
    expires_at: datetime
    created_monotonic: float
    expires_monotonic: float
    approval_code: str | None
    failed_code_attempts: int = 0

    @property
    def required_phrase(self) -> str:
        if self.approval_code is None:
            return "승인"
        return f"승인 {self.approval_code}"

    def remaining_seconds(
        self,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> float:
        return max(
            0.0,
            self.expires_monotonic - clock(),
        )

    def as_public_dict(
        self,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "tool_name": self.tool_name,
            "summary": self.summary,
            "risk": self.risk.value,
            "created_at": self.created_at.isoformat(
                timespec="seconds"
            ),
            "expires_at": self.expires_at.isoformat(
                timespec="seconds"
            ),
            "remaining_seconds": round(
                self.remaining_seconds(
                    clock=clock
                ),
                1,
            ),
            "required_phrase": (
                self.required_phrase
            ),
        }


class ConfirmationManager:
    """Holds at most one unexecuted action in process memory."""

    def __init__(
        self,
        config: ConfirmationConfig = (
            ConfirmationConfig()
        ),
        *,
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = (
            lambda: datetime.now().astimezone()
        ),
    ) -> None:
        self.config = config
        self._clock = clock
        self._now = now
        self._lock = RLock()
        self._pending: PendingAction | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def _clean_expired_locked(
        self,
    ) -> PendingAction | None:
        pending = self._pending
        if (
            pending is not None
            and self._clock()
            >= pending.expires_monotonic
        ):
            self._pending = None
            return pending
        return None

    def pop_expired(
        self,
    ) -> PendingAction | None:
        with self._lock:
            return self._clean_expired_locked()

    def peek(
        self,
    ) -> PendingAction | None:
        with self._lock:
            self._clean_expired_locked()
            return self._pending

    def has_pending(
        self,
    ) -> bool:
        return self.peek() is not None

    def request(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        summary: str,
        risk: ConfirmationRisk,
        timeout_seconds: float | None = None,
    ) -> PendingAction:
        if not self.enabled:
            raise ConfirmationError(
                "Confirmation manager is disabled."
            )

        clean_summary = " ".join(
            summary.strip().split()
        )
        if not clean_summary:
            clean_summary = (
                f"{tool_name} 작업 실행"
            )
        clean_summary = clean_summary[:600]
        copied_arguments = dict(arguments)

        with self._lock:
            self._clean_expired_locked()
            existing = self._pending
            if existing is not None:
                if (
                    existing.tool_name
                    == tool_name
                    and existing.arguments
                    == copied_arguments
                ):
                    return existing
                raise ConfirmationBusyError(
                    existing
                )

            ttl = (
                timeout_seconds
                if timeout_seconds is not None
                else self.config.timeout_seconds
            )
            if ttl <= 0:
                raise ValueError(
                    "Confirmation timeout must be positive."
                )

            created_monotonic = self._clock()
            created_at = self._now()
            approval_code: str | None = None
            if risk is ConfirmationRisk.HIGH:
                digits = (
                    self.config
                    .high_risk_code_digits
                )
                lower = 10 ** (digits - 1)
                upper = 10 ** digits
                approval_code = str(
                    secrets.randbelow(
                        upper - lower
                    )
                    + lower
                )

            pending = PendingAction(
                action_id=uuid4().hex[:10],
                tool_name=tool_name,
                arguments=copied_arguments,
                summary=clean_summary,
                risk=risk,
                created_at=created_at,
                expires_at=(
                    created_at
                    + timedelta(seconds=ttl)
                ),
                created_monotonic=(
                    created_monotonic
                ),
                expires_monotonic=(
                    created_monotonic + ttl
                ),
                approval_code=approval_code,
            )
            self._pending = pending
            return pending

    def approve(
        self,
        *,
        code: str | None = None,
    ) -> PendingAction:
        with self._lock:
            expired = (
                self._clean_expired_locked()
            )
            if expired is not None:
                raise ConfirmationError(
                    "The pending action expired."
                )

            pending = self._pending
            if pending is None:
                raise ConfirmationError(
                    "There is no pending action."
                )

            if pending.approval_code is not None:
                supplied = (
                    str(code).strip()
                    if code is not None
                    else ""
                )
                if supplied != pending.approval_code:
                    attempts = (
                        pending.failed_code_attempts
                        + 1
                    )
                    remaining = max(
                        0,
                        self.config.max_code_attempts
                        - attempts,
                    )
                    cancelled = remaining == 0
                    if cancelled:
                        self._pending = None
                    else:
                        self._pending = (
                            PendingAction(
                                action_id=(
                                    pending.action_id
                                ),
                                tool_name=(
                                    pending.tool_name
                                ),
                                arguments=dict(
                                    pending.arguments
                                ),
                                summary=pending.summary,
                                risk=pending.risk,
                                created_at=(
                                    pending.created_at
                                ),
                                expires_at=(
                                    pending.expires_at
                                ),
                                created_monotonic=(
                                    pending
                                    .created_monotonic
                                ),
                                expires_monotonic=(
                                    pending
                                    .expires_monotonic
                                ),
                                approval_code=(
                                    pending
                                    .approval_code
                                ),
                                failed_code_attempts=(
                                    attempts
                                ),
                            )
                        )
                    raise ConfirmationCodeError(
                        (
                            "Approval code did not match."
                            if not cancelled
                            else (
                                "Approval code failed too "
                                "many times; the action was "
                                "cancelled."
                            )
                        ),
                        remaining_attempts=remaining,
                        cancelled=cancelled,
                    )

            self._pending = None
            return pending

    def cancel(
        self,
    ) -> PendingAction | None:
        with self._lock:
            self._clean_expired_locked()
            pending = self._pending
            self._pending = None
            return pending

    def close(self) -> None:
        self.cancel()
