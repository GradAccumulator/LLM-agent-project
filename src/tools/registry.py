from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Callable, Mapping

from src.memory import LocalMemoryStore
from src.scheduler import SchedulerStore

from src.planning import (
    TaskPlanTracker,
    is_action_tool,
    is_planning_tool,
    verify_action_result,
)


ToolHandler = Callable[
    ...,
    Mapping[str, Any] | str | int | float | bool | None,
]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    name: str
    arguments: dict[str, Any]
    success: bool
    output: str
    elapsed_seconds: float
    verified: bool | None = None
    verification: dict[str, Any] | None = None
    plan_progress: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    success: bool
    output: str
    elapsed_seconds: float
    verified: bool | None = None
    verification: dict[str, Any] | None = None
    plan_progress: dict[str, Any] | None = None


class ToolRegistry:
    def __init__(
        self,
        memory_store: LocalMemoryStore | None = None,
        scheduler_store: SchedulerStore | None = None,
    ) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._closers: list[Callable[[], Any]] = []
        self._closed = False
        self.plan_tracker = TaskPlanTracker()
        self._memory_store = memory_store
        self._scheduler_store = scheduler_store

    @property
    def memory_store(self) -> LocalMemoryStore | None:
        return self._memory_store

    @property
    def scheduler_store(self) -> SchedulerStore | None:
        return self._scheduler_store

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [
            tool.as_openai_tool()
            for tool in self._tools.values()
        ]

    def begin_request(
        self,
        *,
        planning_required: bool,
        max_steps: int,
        max_repair_attempts: int,
    ) -> None:
        self.plan_tracker.begin_request(
            required=planning_required,
            max_steps=max_steps,
            max_repair_attempts=max_repair_attempts,
        )

    def plan_snapshot(self) -> dict[str, Any]:
        return self.plan_tracker.snapshot()

    def register_closer(
        self,
        closer: Callable[[], Any],
    ) -> None:
        if self._closed:
            raise RuntimeError(
                "Tool registry is already closed."
            )
        self._closers.append(closer)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for closer in reversed(self._closers):
            try:
                closer()
            except Exception:
                pass
        self._closers.clear()

    def register(self, tool: ToolSpec) -> None:
        name = tool.name.strip()
        if not name:
            raise ValueError(
                "Tool name must not be empty."
            )
        if name in self._tools:
            raise ValueError(
                f"Tool is already registered: {name}"
            )

        if tool.parameters.get("type") != "object":
            raise ValueError(
                f"Tool parameters must be an object "
                f"schema: {name}"
            )
        if (
            tool.parameters.get("additionalProperties")
            is not False
        ):
            raise ValueError(
                "Tool schema must disable additional "
                f"properties: {name}"
            )

        self._tools[name] = tool

    def _failure(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        error: str,
        elapsed_seconds: float = 0.0,
        verified: bool | None = None,
        verification: dict[str, Any] | None = None,
        plan_progress: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        payload: dict[str, Any] = {
            "success": False,
            "error": error,
        }
        if verification is not None:
            payload["verification"] = verification
        if plan_progress is not None:
            payload["plan_progress"] = plan_progress

        return ToolExecutionResult(
            name=name,
            arguments=arguments,
            success=False,
            output=json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ),
            elapsed_seconds=elapsed_seconds,
            verified=verified,
            verification=verification,
            plan_progress=plan_progress,
        )

    def execute(
        self,
        name: str,
        arguments_json: str,
    ) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            return self._failure(
                name=name,
                arguments={},
                error=f"Unknown tool: {name}",
            )

        try:
            loaded = json.loads(
                arguments_json or "{}"
            )
        except json.JSONDecodeError as exc:
            return self._failure(
                name=name,
                arguments={},
                error=(
                    "Invalid tool arguments: "
                    f"{exc.msg}"
                ),
            )

        if not isinstance(loaded, dict):
            return self._failure(
                name=name,
                arguments={},
                error=(
                    "Tool arguments must be a JSON object."
                ),
            )

        action = is_action_tool(name)
        planning_tool = is_planning_tool(name)
        if (
            action
            and self.plan_tracker.required
            and not self.plan_tracker.active
        ):
            snapshot = self.plan_tracker.snapshot()
            return self._failure(
                name=name,
                arguments=loaded,
                error=(
                    "This multi-step request requires "
                    "begin_task_plan before action tools."
                ),
                verified=False,
                verification={
                    "verified": False,
                    "strength": "precondition",
                    "tool": name,
                    "evidence": {
                        "required_tool": (
                            "begin_task_plan"
                        )
                    },
                },
                plan_progress=snapshot,
            )

        if (
            action
            and self.plan_tracker.status.value
            in {"failed", "abandoned", "completed"}
            and self.plan_tracker.required
        ):
            snapshot = self.plan_tracker.snapshot()
            return self._failure(
                name=name,
                arguments=loaded,
                error=(
                    "No more action tools are allowed because "
                    f"the task plan is {snapshot['status']}."
                ),
                verified=False,
                plan_progress=snapshot,
            )

        started_at = perf_counter()
        try:
            result = tool.handler(**loaded)
            elapsed_seconds = (
                perf_counter() - started_at
            )
            payload = (
                dict(result)
                if isinstance(result, Mapping)
                else {"result": result}
            )
        except Exception as exc:
            elapsed_seconds = (
                perf_counter() - started_at
            )
            verification = None
            progress = None
            if action:
                verification = {
                    "verified": False,
                    "strength": "execution",
                    "tool": name,
                    "evidence": {
                        "error": (
                            str(exc)
                            or type(exc).__name__
                        )
                    },
                }
                progress = (
                    self.plan_tracker.record_action(
                        tool_name=name,
                        verified=False,
                        verification=verification,
                    )
                )

            return self._failure(
                name=name,
                arguments=loaded,
                error=(
                    str(exc)
                    or type(exc).__name__
                ),
                elapsed_seconds=elapsed_seconds,
                verified=(
                    False if action else None
                ),
                verification=verification,
                plan_progress=progress,
            )

        verification = None
        progress = None
        verified: bool | None = None

        if action:
            verification = verify_action_result(
                name,
                loaded,
                payload,
            )
            verified = bool(
                verification.get("verified")
            )
            progress = (
                self.plan_tracker.record_action(
                    tool_name=name,
                    verified=verified,
                    verification=verification,
                )
            )
            payload["verification"] = verification
            if progress is not None:
                payload["plan_progress"] = progress

        elif planning_tool:
            # Planning tool handlers return the current snapshot.
            if isinstance(payload.get("result"), dict):
                progress = payload["result"]
            elif "status" in payload:
                progress = dict(payload)

        payload = {"success": True, **payload}
        success = True
        if action and verified is False:
            success = False
            payload["success"] = False
            payload["error"] = (
                "The action ran, but its postcondition "
                "could not be verified."
            )

        return ToolExecutionResult(
            name=name,
            arguments=loaded,
            success=success,
            output=json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ),
            elapsed_seconds=elapsed_seconds,
            verified=verified,
            verification=verification,
            plan_progress=progress,
        )
