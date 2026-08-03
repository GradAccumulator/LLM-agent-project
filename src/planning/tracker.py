from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .recovery import assess_failure


class PlanStatus(str, Enum):
    IDLE = "idle"
    REQUIRED = "required"
    ACTIVE = "active"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class StepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    NEEDS_REPAIR = "needs_repair"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLACED = "replaced"


@dataclass(slots=True)
class PlanStep:
    number: int
    instruction: str
    step_id: str = field(
        default_factory=lambda: uuid4().hex[:12]
    )
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    repair_count: int = 0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None
    last_failure: dict[str, Any] | None = None
    failure_counts: dict[str, int] = field(default_factory=dict)
    tried_tools: list[str] = field(default_factory=list)
    preferred_tool: str | None = None
    expected_evidence: str | None = None
    repair_strategy: str | None = None

    def as_dict(self, *, attempt_budget: int) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "number": self.number,
            "instruction": self.instruction,
            "status": self.status.value,
            "attempts": self.attempts,
            "attempt_budget": attempt_budget,
            "remaining_attempts": max(0, attempt_budget - self.attempts),
            "repair_count": self.repair_count,
            "evidence": list(self.evidence),
            "failure_reason": self.failure_reason,
            "last_failure": self.last_failure,
            "tried_tools": list(self.tried_tools),
            "preferred_tool": self.preferred_tool,
            "expected_evidence": self.expected_evidence,
            "repair_strategy": self.repair_strategy,
        }


class TaskPlanTracker:
    """Tracks a request plan with bounded partial repair and failure guards."""

    _REPAIR_STRATEGIES = {
        "retry",
        "switch_tool",
        "replace_current",
        "replace_remaining",
    }

    def __init__(self) -> None:
        self._required = False
        self._max_steps = 6
        self._max_repair_attempts = 2
        self._max_plan_revisions = 3
        self._max_same_failure_repeats = 2
        self._tool_switching_enabled = True
        self._plan_id: str | None = None
        self._goal: str | None = None
        self._status = PlanStatus.IDLE
        self._steps: list[PlanStep] = []
        self._current_index: int | None = None
        self._summary: str | None = None
        self._revision_count = 0
        self._revisions: list[dict[str, Any]] = []

    @property
    def required(self) -> bool:
        return self._required

    @property
    def active(self) -> bool:
        return self._status is PlanStatus.ACTIVE

    @property
    def repairing(self) -> bool:
        return self._status is PlanStatus.REPAIRING

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

    @property
    def attempt_budget(self) -> int:
        return 1 + self._max_repair_attempts

    def begin_request(
        self,
        *,
        required: bool,
        max_steps: int,
        max_repair_attempts: int,
        max_plan_revisions: int = 3,
        max_same_failure_repeats: int = 2,
        tool_switching_enabled: bool = True,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive.")
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must not be negative.")
        if max_plan_revisions < 0:
            raise ValueError("max_plan_revisions must not be negative.")
        if max_same_failure_repeats < 1:
            raise ValueError("max_same_failure_repeats must be at least 1.")

        self._required = required
        self._max_steps = max_steps
        self._max_repair_attempts = max_repair_attempts
        self._max_plan_revisions = max_plan_revisions
        self._max_same_failure_repeats = max_same_failure_repeats
        self._tool_switching_enabled = tool_switching_enabled
        self._plan_id = None
        self._goal = None
        self._steps = []
        self._current_index = None
        self._summary = None
        self._revision_count = 0
        self._revisions = []
        self._status = PlanStatus.REQUIRED if required else PlanStatus.IDLE

    def begin_plan(self, goal: str, steps: list[str]) -> dict[str, Any]:
        goal = goal.strip()
        normalized_steps = [
            step.strip()
            for step in steps
            if isinstance(step, str) and step.strip()
        ]
        if not goal:
            raise ValueError("Plan goal must not be empty.")
        if len(normalized_steps) < 2:
            raise ValueError("A multi-step plan requires at least 2 steps.")
        if len(normalized_steps) > self._max_steps:
            raise ValueError(f"Plan exceeds the {self._max_steps}-step limit.")
        if self._status not in {PlanStatus.REQUIRED, PlanStatus.IDLE}:
            raise RuntimeError("A task plan is already active or finalized.")

        self._plan_id = uuid4().hex
        self._goal = goal
        self._steps = [
            PlanStep(number=index, instruction=instruction)
            for index, instruction in enumerate(normalized_steps, start=1)
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
        error: str | None = None,
    ) -> dict[str, Any] | None:
        if self._status not in {PlanStatus.ACTIVE, PlanStatus.REPAIRING}:
            return self.snapshot() if self._required else None
        if self._status is PlanStatus.REPAIRING:
            raise RuntimeError(
                "The current plan step requires repair before another action tool."
            )

        step = self.current_step
        if step is None:
            raise RuntimeError("Active plan does not have a current step.")

        step.attempts += 1
        if tool_name not in step.tried_tools:
            step.tried_tools.append(tool_name)
        evidence = {
            "tool": tool_name,
            "verified": bool(verified),
            "verification": verification,
        }
        if error:
            evidence["error"] = error
        step.evidence.append(evidence)

        if verified:
            step.status = StepStatus.COMPLETED
            step.failure_reason = None
            step.last_failure = None
            self._advance()
            return self.snapshot()

        assessment = assess_failure(
            tool_name=tool_name,
            verification=verification,
            error=error,
            tool_switching_enabled=self._tool_switching_enabled,
        )
        repeat_count = step.failure_counts.get(assessment.signature, 0) + 1
        step.failure_counts[assessment.signature] = repeat_count
        failure = assessment.as_dict()
        failure.update(
            {
                "tool": tool_name,
                "repeat_count": repeat_count,
                "same_failure_limit": self._max_same_failure_repeats,
                "attempt": step.attempts,
                "attempt_budget": self.attempt_budget,
                "repeated_failure": repeat_count >= self._max_same_failure_repeats,
            }
        )
        step.last_failure = failure
        step.failure_reason = assessment.summary

        exhausted = step.attempts >= self.attempt_budget
        revisions_exhausted = self._revision_count >= self._max_plan_revisions
        if (
            not assessment.recoverable
            or exhausted
            or revisions_exhausted
        ):
            step.status = StepStatus.FAILED
            self._status = PlanStatus.FAILED
            if exhausted:
                step.failure_reason = (
                    f"Step attempt budget exhausted after {step.attempts} attempts."
                )
            elif revisions_exhausted:
                step.failure_reason = (
                    "Plan revision budget is exhausted."
                )
            return self.snapshot()

        step.status = StepStatus.NEEDS_REPAIR
        self._status = PlanStatus.REPAIRING
        return self.snapshot()

    def recovery_report(self) -> dict[str, Any]:
        if self._status is not PlanStatus.REPAIRING:
            return {
                "repair_required": False,
                "status": self._status.value,
                "message": "현재 부분 재계획이 필요한 단계가 없습니다.",
            }
        step = self.current_step
        if step is None or step.last_failure is None:
            raise RuntimeError("Repairing plan has no failure report.")
        failure = dict(step.last_failure)
        recommended_tools = list(failure.get("recommended_tools") or [])
        blocked_tools: list[str] = []
        if failure.get("repeated_failure"):
            blocked_tools.append(str(failure.get("tool") or ""))
        return {
            "repair_required": True,
            "plan_id": self._plan_id,
            "current_step": step.as_dict(attempt_budget=self.attempt_budget),
            "failure": failure,
            "recommended_strategy": failure.get("recommended_strategy"),
            "recommended_tools": recommended_tools,
            "blocked_tools": [tool for tool in blocked_tools if tool],
            "revision_count": self._revision_count,
            "remaining_revisions": max(
                0,
                self._max_plan_revisions - self._revision_count,
            ),
            "message": (
                "같은 행동을 그대로 반복하지 말고 repair_task_plan으로 "
                "현재 단계만 재개하거나 교체하세요."
            ),
        }

    def repair_current_step(
        self,
        reason: str,
        strategy: str,
        replacement_steps: list[str] | None,
        preferred_tool: str | None,
        expected_evidence: str | None,
    ) -> dict[str, Any]:
        if self._status is not PlanStatus.REPAIRING:
            raise RuntimeError("The task plan is not waiting for repair.")
        if self._revision_count >= self._max_plan_revisions:
            raise RuntimeError("Plan revision budget is exhausted.")
        reason = reason.strip()
        strategy = strategy.strip().casefold()
        preferred_tool = (preferred_tool or "").strip() or None
        expected_evidence = (expected_evidence or "").strip() or None
        normalized_steps = [
            step.strip()
            for step in (replacement_steps or [])
            if isinstance(step, str) and step.strip()
        ]
        if not reason:
            raise ValueError("Repair reason must not be empty.")
        if strategy not in self._REPAIR_STRATEGIES:
            raise ValueError(
                "strategy must be retry, switch_tool, replace_current, or replace_remaining."
            )

        current = self.current_step
        if current is None or current.last_failure is None:
            raise RuntimeError("Repairing plan has no current failure.")
        failure = current.last_failure
        last_tool = str(failure.get("tool") or "")
        repeated = bool(failure.get("repeated_failure"))

        if strategy == "retry":
            if normalized_steps:
                raise ValueError("replacement_steps must be null for retry.")
            if repeated and (preferred_tool is None or preferred_tool == last_tool):
                raise ValueError(
                    "The same failure repeated. Choose switch_tool or provide a different preferred_tool."
                )
        elif strategy == "switch_tool":
            if normalized_steps:
                raise ValueError("replacement_steps must be null for switch_tool.")
            if not preferred_tool:
                raise ValueError("preferred_tool is required for switch_tool.")
            if preferred_tool == last_tool:
                raise ValueError("switch_tool must choose a different tool.")
        else:
            if not normalized_steps:
                raise ValueError("replacement_steps are required for replacement strategies.")

        revision = {
            "revision": self._revision_count + 1,
            "reason": reason,
            "strategy": strategy,
            "failed_step": current.as_dict(attempt_budget=self.attempt_budget),
            "preferred_tool": preferred_tool,
            "expected_evidence": expected_evidence,
            "replacement_steps": list(normalized_steps),
        }

        if strategy in {"retry", "switch_tool"}:
            current.status = StepStatus.ACTIVE
            current.repair_count += 1
            current.repair_strategy = strategy
            current.preferred_tool = preferred_tool
            current.expected_evidence = expected_evidence
        else:
            prefix = self._steps[: self._current_index]
            suffix = (
                self._steps[self._current_index + 1 :]
                if strategy == "replace_current"
                else []
            )
            new_steps = [
                PlanStep(
                    number=0,
                    instruction=instruction,
                    preferred_tool=preferred_tool,
                    expected_evidence=expected_evidence,
                    repair_strategy=strategy,
                    repair_count=1,
                )
                for instruction in normalized_steps
            ]
            combined = prefix + new_steps + suffix
            if len(combined) > self._max_steps:
                raise ValueError(
                    f"Repaired plan exceeds the {self._max_steps}-step limit."
                )
            archived = current.as_dict(attempt_budget=self.attempt_budget)
            archived["status"] = StepStatus.REPLACED.value
            revision["archived_step"] = archived
            self._steps = combined
            for index, step in enumerate(self._steps, start=1):
                step.number = index
                if index <= len(prefix):
                    continue
                if step.status is not StepStatus.COMPLETED:
                    step.status = StepStatus.PENDING
            self._current_index = len(prefix)
            self._steps[self._current_index].status = StepStatus.ACTIVE

        self._revision_count += 1
        self._revisions.append(revision)
        self._status = PlanStatus.ACTIVE
        return self.snapshot()

    def complete_current_step(self, evidence: str) -> dict[str, Any]:
        if self._status is not PlanStatus.ACTIVE:
            raise RuntimeError("There is no active task plan step.")
        step = self.current_step
        if step is None:
            raise RuntimeError("Active plan does not have a current step.")
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

    def fail_current_step(self, reason: str) -> dict[str, Any]:
        if self._status not in {PlanStatus.ACTIVE, PlanStatus.REPAIRING}:
            raise RuntimeError("There is no active task plan.")
        reason = reason.strip()
        if not reason:
            raise ValueError("Failure reason must not be empty.")
        step = self.current_step
        if step is None:
            raise RuntimeError("Active plan does not have a current step.")
        step.status = StepStatus.FAILED
        step.failure_reason = reason
        self._status = PlanStatus.FAILED
        return self.snapshot()

    def _audit(self) -> dict[str, Any]:
        unresolved = [
            step.number
            for step in self._steps
            if step.status is not StepStatus.COMPLETED
        ]
        missing_verified_evidence = [
            step.number
            for step in self._steps
            if not any(item.get("verified") is True for item in step.evidence)
        ]
        passed = not unresolved and not missing_verified_evidence and bool(self._steps)
        return {
            "passed": passed,
            "unresolved_steps": unresolved,
            "steps_without_verified_evidence": missing_verified_evidence,
            "revision_count": self._revision_count,
        }

    def finish_plan(self, summary: str) -> dict[str, Any]:
        summary = summary.strip()
        if not summary:
            raise ValueError("Plan summary must not be empty.")
        if self._status is not PlanStatus.COMPLETED:
            raise RuntimeError("The plan cannot finish until every step is completed.")
        audit = self._audit()
        if not audit["passed"]:
            raise RuntimeError("Plan audit failed; verified evidence is incomplete.")
        self._summary = summary
        snapshot = self.snapshot()
        snapshot["audit"] = audit
        return snapshot

    def abandon_plan(self, reason: str) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ValueError("Abandon reason must not be empty.")
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
        self._status = PlanStatus.ACTIVE

    def snapshot(self) -> dict[str, Any]:
        current = self.current_step
        completed = sum(step.status is StepStatus.COMPLETED for step in self._steps)
        recovery = None
        if self._status is PlanStatus.REPAIRING and current is not None:
            recovery = {
                "failure": current.last_failure,
                "recommended_strategy": (
                    (current.last_failure or {}).get("recommended_strategy")
                ),
                "recommended_tools": list(
                    (current.last_failure or {}).get("recommended_tools") or []
                ),
            }
        return {
            "required": self._required,
            "plan_id": self._plan_id,
            "goal": self._goal,
            "status": self._status.value,
            "recovery_required": self._status is PlanStatus.REPAIRING,
            "current_step": current.number if current is not None else None,
            "completed_steps": completed,
            "total_steps": len(self._steps),
            "attempt_budget_per_step": self.attempt_budget,
            "max_repair_attempts": self._max_repair_attempts,
            "max_plan_revisions": self._max_plan_revisions,
            "max_same_failure_repeats": self._max_same_failure_repeats,
            "tool_switching_enabled": self._tool_switching_enabled,
            "revision_count": self._revision_count,
            "remaining_revisions": max(0, self._max_plan_revisions - self._revision_count),
            "summary": self._summary,
            "recovery": recovery,
            "revisions": list(self._revisions),
            "steps": [
                step.as_dict(attempt_budget=self.attempt_budget)
                for step in self._steps
            ],
        }
