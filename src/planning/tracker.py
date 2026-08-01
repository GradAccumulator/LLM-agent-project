from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class PlanStatus(str, Enum):
    IDLE = "idle"
    REQUIRED = "required"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class StepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class PlanStep:
    number: int
    instruction: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    evidence: list[dict[str, Any]] = field(
        default_factory=list
    )
    failure_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "instruction": self.instruction,
            "status": self.status.value,
            "attempts": self.attempts,
            "evidence": list(self.evidence),
            "failure_reason": self.failure_reason,
        }


class TaskPlanTracker:
    """Tracks one model request's plan and verified step progress."""

    def __init__(self) -> None:
        self._required = False
        self._max_steps = 6
        self._max_repair_attempts = 2
        self._plan_id: str | None = None
        self._goal: str | None = None
        self._status = PlanStatus.IDLE
        self._steps: list[PlanStep] = []
        self._current_index: int | None = None
        self._summary: str | None = None

    @property
    def required(self) -> bool:
        return self._required

    @property
    def active(self) -> bool:
        return self._status is PlanStatus.ACTIVE

    @property
    def status(self) -> PlanStatus:
        return self._status

    @property
    def current_step(self) -> PlanStep | None:
        if self._current_index is None:
            return None
        if not 0 <= self._current_index < len(self._steps):
            return None
        return self._steps[self._current_index]

    def begin_request(
        self,
        *,
        required: bool,
        max_steps: int,
        max_repair_attempts: int,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive.")
        if max_repair_attempts < 0:
            raise ValueError(
                "max_repair_attempts must not be negative."
            )

        self._required = required
        self._max_steps = max_steps
        self._max_repair_attempts = max_repair_attempts
        self._plan_id = None
        self._goal = None
        self._steps = []
        self._current_index = None
        self._summary = None
        self._status = (
            PlanStatus.REQUIRED
            if required
            else PlanStatus.IDLE
        )

    def begin_plan(
        self,
        goal: str,
        steps: list[str],
    ) -> dict[str, Any]:
        goal = goal.strip()
        normalized_steps = [
            step.strip()
            for step in steps
            if isinstance(step, str) and step.strip()
        ]

        if not goal:
            raise ValueError("Plan goal must not be empty.")
        if len(normalized_steps) < 2:
            raise ValueError(
                "A multi-step plan requires at least 2 steps."
            )
        if len(normalized_steps) > self._max_steps:
            raise ValueError(
                f"Plan exceeds the {self._max_steps}-step limit."
            )
        if self.active:
            raise RuntimeError(
                "A task plan is already active."
            )

        self._plan_id = uuid4().hex
        self._goal = goal
        self._steps = [
            PlanStep(number=index, instruction=instruction)
            for index, instruction in enumerate(
                normalized_steps,
                start=1,
            )
        ]
        self._current_index = 0
        self._steps[0].status = StepStatus.ACTIVE
        self._status = PlanStatus.ACTIVE
        self._summary = None
        return self.snapshot()

    def record_action(
        self,
        *,
        tool_name: str,
        verified: bool,
        verification: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.active:
            return self.snapshot() if self._required else None

        step = self.current_step
        if step is None:
            raise RuntimeError(
                "Active plan does not have a current step."
            )

        step.attempts += 1
        step.evidence.append(
            {
                "tool": tool_name,
                "verified": verified,
                "verification": verification,
            }
        )

        if verified:
            step.status = StepStatus.COMPLETED
            self._advance()
        elif step.attempts > self._max_repair_attempts:
            step.status = StepStatus.FAILED
            step.failure_reason = (
                "Automatic verification failed after "
                f"{step.attempts} attempts."
            )
            self._status = PlanStatus.FAILED

        return self.snapshot()

    def complete_current_step(
        self,
        evidence: str,
    ) -> dict[str, Any]:
        if not self.active:
            raise RuntimeError(
                "There is no active task plan."
            )
        step = self.current_step
        if step is None:
            raise RuntimeError(
                "Active plan does not have a current step."
            )

        evidence = evidence.strip()
        if not evidence:
            raise ValueError("Evidence must not be empty.")

        step.attempts += 1
        step.evidence.append(
            {
                "tool": "complete_plan_step",
                "verified": True,
                "verification": {
                    "mode": "model_supplied_observation",
                    "evidence": evidence,
                },
            }
        )
        step.status = StepStatus.COMPLETED
        self._advance()
        return self.snapshot()

    def fail_current_step(
        self,
        reason: str,
    ) -> dict[str, Any]:
        if not self.active:
            raise RuntimeError(
                "There is no active task plan."
            )
        reason = reason.strip()
        if not reason:
            raise ValueError("Failure reason must not be empty.")

        step = self.current_step
        if step is None:
            raise RuntimeError(
                "Active plan does not have a current step."
            )

        step.status = StepStatus.FAILED
        step.failure_reason = reason
        self._status = PlanStatus.FAILED
        return self.snapshot()

    def finish_plan(
        self,
        summary: str,
    ) -> dict[str, Any]:
        summary = summary.strip()
        if not summary:
            raise ValueError("Plan summary must not be empty.")
        if self._status is not PlanStatus.COMPLETED:
            raise RuntimeError(
                "The plan cannot be finished until every step "
                "is completed."
            )
        self._summary = summary
        return self.snapshot()

    def abandon_plan(
        self,
        reason: str,
    ) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ValueError(
                "Abandon reason must not be empty."
            )
        self._status = PlanStatus.ABANDONED
        self._summary = reason
        return self.snapshot()

    def _advance(self) -> None:
        if self._current_index is None:
            return

        next_index = self._current_index + 1
        if next_index >= len(self._steps):
            self._current_index = None
            self._status = PlanStatus.COMPLETED
            return

        self._current_index = next_index
        self._steps[next_index].status = StepStatus.ACTIVE

    def snapshot(self) -> dict[str, Any]:
        current = self.current_step
        completed = sum(
            step.status is StepStatus.COMPLETED
            for step in self._steps
        )
        return {
            "required": self._required,
            "plan_id": self._plan_id,
            "goal": self._goal,
            "status": self._status.value,
            "current_step": (
                current.number if current is not None else None
            ),
            "completed_steps": completed,
            "total_steps": len(self._steps),
            "max_repair_attempts": (
                self._max_repair_attempts
            ),
            "summary": self._summary,
            "steps": [
                step.as_dict() for step in self._steps
            ],
        }
