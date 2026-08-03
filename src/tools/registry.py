from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Callable, Mapping

from src.confirmation import (
    ConfirmationBusyError,
    ConfirmationCodeError,
    ConfirmationConfig,
    ConfirmationError,
    ConfirmationManager,
    ConfirmationRequirement,
)
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


def _validate_strict_schema(
    schema: Any,
    *,
    path: str = "parameters",
) -> None:
    """Validate the JSON-schema subset required by strict tools.

    OpenAI strict function schemas require every object property to be
    present in that object's ``required`` array. Optional values are
    represented by a nullable type, not by omitting the key from
    ``required``. Validate locally so a bad tool cannot make every model
    request fail later with an HTTP 400.
    """

    if not isinstance(schema, dict):
        raise ValueError(
            f"Strict tool schema node must be an object: {path}"
        )

    schema_type = schema.get("type")
    is_object = (
        schema_type == "object"
        or (
            isinstance(schema_type, list)
            and "object" in schema_type
        )
    )
    if is_object:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(
                f"Strict object schema must define properties: {path}"
            )
        required = schema.get("required")
        if not isinstance(required, list):
            raise ValueError(
                f"Strict object schema must define required: {path}"
            )

        property_names = set(properties)
        required_names = {
            str(name)
            for name in required
        }
        missing = sorted(
            property_names
            - required_names
        )
        extra = sorted(
            required_names
            - property_names
        )
        if missing or extra:
            details: list[str] = []
            if missing:
                details.append(
                    "missing required keys: "
                    + ", ".join(missing)
                )
            if extra:
                details.append(
                    "unknown required keys: "
                    + ", ".join(extra)
                )
            raise ValueError(
                f"Invalid strict object schema at {path}: "
                + "; ".join(details)
            )
        if schema.get("additionalProperties") is not False:
            raise ValueError(
                "Strict object schema must set "
                f"additionalProperties=false: {path}"
            )

        for name, child in properties.items():
            _validate_strict_schema(
                child,
                path=f"{path}.properties.{name}",
            )

    items = schema.get("items")
    if items is not None:
        _validate_strict_schema(
            items,
            path=f"{path}.items",
        )

    for keyword in (
        "anyOf",
        "oneOf",
        "allOf",
    ):
        branches = schema.get(keyword)
        if branches is None:
            continue
        if not isinstance(branches, list):
            raise ValueError(
                f"{keyword} must be an array: {path}"
            )
        for index, branch in enumerate(branches):
            _validate_strict_schema(
                branch,
                path=(
                    f"{path}.{keyword}[{index}]"
                ),
            )


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    confirmation: (
        ConfirmationRequirement | None
    ) = None

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
    confirmation_required: bool = False
    confirmation_id: str | None = None


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
    confirmation_required: bool = False
    confirmation_id: str | None = None


class ToolRegistry:
    def __init__(
        self,
        memory_store: LocalMemoryStore | None = None,
        scheduler_store: SchedulerStore | None = None,
        confirmation_config: (
            ConfirmationConfig | None
        ) = None,
    ) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._closers: list[Callable[[], Any]] = []
        self._closed = False
        self.plan_tracker = TaskPlanTracker()
        self._memory_store = memory_store
        self._scheduler_store = scheduler_store
        self.confirmations = ConfirmationManager(
            confirmation_config
            or ConfirmationConfig()
        )

    @property
    def memory_store(
        self,
    ) -> LocalMemoryStore | None:
        return self._memory_store

    @property
    def scheduler_store(
        self,
    ) -> SchedulerStore | None:
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

    def confirmation_required_for(
        self,
        name: str,
    ) -> bool:
        tool = self._tools.get(name)
        return bool(
            tool is not None
            and tool.confirmation is not None
            and self.confirmations.enabled
        )

    def pending_confirmation(
        self,
    ) -> dict[str, Any] | None:
        pending = self.confirmations.peek()
        return (
            pending.as_public_dict()
            if pending is not None
            else None
        )

    def has_pending_confirmation(
        self,
    ) -> bool:
        return self.confirmations.has_pending()

    def begin_request(
        self,
        *,
        planning_required: bool,
        max_steps: int,
        max_repair_attempts: int,
        max_plan_revisions: int = 3,
        max_same_failure_repeats: int = 2,
        tool_switching_enabled: bool = True,
    ) -> None:
        self.plan_tracker.begin_request(
            required=planning_required,
            max_steps=max_steps,
            max_repair_attempts=max_repair_attempts,
            max_plan_revisions=max_plan_revisions,
            max_same_failure_repeats=(
                max_same_failure_repeats
            ),
            tool_switching_enabled=(
                tool_switching_enabled
            ),
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
        self.confirmations.close()
        for closer in reversed(
            self._closers
        ):
            try:
                closer()
            except Exception:
                pass
        self._closers.clear()

    def register(
        self,
        tool: ToolSpec,
    ) -> None:
        name = tool.name.strip()
        if not name:
            raise ValueError(
                "Tool name must not be empty."
            )
        if name in self._tools:
            raise ValueError(
                f"Tool is already registered: {name}"
            )

        if (
            tool.parameters.get("type")
            != "object"
        ):
            raise ValueError(
                "Tool parameters must be an "
                f"object schema: {name}"
            )
        if (
            tool.parameters.get(
                "additionalProperties"
            )
            is not False
        ):
            raise ValueError(
                "Tool schema must disable "
                f"additional properties: {name}"
            )

        try:
            _validate_strict_schema(
                tool.parameters
            )
        except ValueError as exc:
            raise ValueError(
                f"Invalid strict tool schema for {name}: {exc}"
            ) from exc

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
            payload["plan_progress"] = (
                plan_progress
            )

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

    @staticmethod
    def _json_result(
        *,
        name: str,
        arguments: dict[str, Any],
        payload: Mapping[str, Any],
        success: bool,
        elapsed_seconds: float = 0.0,
        confirmation_required: bool = False,
        confirmation_id: str | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            name=name,
            arguments=arguments,
            success=success,
            output=json.dumps(
                dict(payload),
                ensure_ascii=False,
                default=str,
            ),
            elapsed_seconds=elapsed_seconds,
            confirmation_required=(
                confirmation_required
            ),
            confirmation_id=(
                confirmation_id
            ),
        )

    def _validate_plan_precondition(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult | None:
        if not is_action_tool(name) or not self.plan_tracker.required:
            return None

        snapshot = self.plan_tracker.snapshot()
        status = snapshot["status"]
        if status == "required":
            return self._failure(
                name=name,
                arguments=arguments,
                error=(
                    "This multi-step request requires begin_task_plan "
                    "before action tools."
                ),
                verified=False,
                verification={
                    "verified": False,
                    "strength": "precondition",
                    "tool": name,
                    "evidence": {"required_tool": "begin_task_plan"},
                },
                plan_progress=snapshot,
            )

        if status == "repairing":
            return self._failure(
                name=name,
                arguments=arguments,
                error=(
                    "The current plan step is waiting for repair. Call "
                    "get_plan_recovery and repair_task_plan before another "
                    "action tool."
                ),
                verified=False,
                verification={
                    "verified": False,
                    "strength": "precondition",
                    "tool": name,
                    "evidence": {
                        "required_tools": [
                            "get_plan_recovery",
                            "repair_task_plan",
                        ]
                    },
                },
                plan_progress=snapshot,
            )

        if status in {"failed", "abandoned", "completed"}:
            return self._failure(
                name=name,
                arguments=arguments,
                error=(
                    "No more action tools are allowed because the task "
                    f"plan is {status}."
                ),
                verified=False,
                plan_progress=snapshot,
            )
        return None

    def _request_confirmation(
        self,
        *,
        tool: ToolSpec,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        requirement = tool.confirmation
        if requirement is None:
            raise RuntimeError(
                "Tool has no confirmation requirement."
            )

        try:
            summary = requirement.summary(
                arguments
            )
        except Exception:
            summary = (
                f"{tool.name} 작업 실행"
            )

        try:
            pending = (
                self.confirmations.request(
                    tool_name=tool.name,
                    arguments=arguments,
                    summary=summary,
                    risk=requirement.risk,
                    timeout_seconds=(
                        requirement
                        .timeout_seconds
                    ),
                )
            )
        except ConfirmationBusyError as exc:
            public = (
                exc.pending
                .as_public_dict()
            )
            return self._json_result(
                name=tool.name,
                arguments=arguments,
                success=True,
                confirmation_required=True,
                confirmation_id=(
                    exc.pending.action_id
                ),
                payload={
                    "success": True,
                    "confirmation_required": (
                        True
                    ),
                    "pending_action": public,
                    "message": (
                        "다른 작업이 이미 승인 "
                        "대기 중입니다. 먼저 "
                        f"'{public['required_phrase']}' "
                        "또는 '취소'라고 말해주세요."
                    ),
                },
            )

        public = pending.as_public_dict()
        return self._json_result(
            name=tool.name,
            arguments=arguments,
            success=True,
            confirmation_required=True,
            confirmation_id=(
                pending.action_id
            ),
            payload={
                "success": True,
                "executed": False,
                "confirmation_required": True,
                "pending_action": public,
                "message": (
                    "실행 전 확인이 필요합니다. "
                    f"{pending.summary}. "
                    "진행하려면 정확히 "
                    f"'{pending.required_phrase}', "
                    "취소하려면 '취소'라고 "
                    "말하거나 입력하세요."
                ),
            },
        )

    def _execute_handler(
        self,
        *,
        tool: ToolSpec,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        name = tool.name
        action = is_action_tool(name)
        planning_tool = is_planning_tool(
            name
        )

        started_at = perf_counter()
        try:
            result = tool.handler(**arguments)
            elapsed_seconds = (
                perf_counter() - started_at
            )
            payload = (
                dict(result)
                if isinstance(
                    result,
                    Mapping,
                )
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
                    self.plan_tracker
                    .record_action(
                        tool_name=name,
                        verified=False,
                        verification=verification,
                        error=(
                            str(exc)
                            or type(exc).__name__
                        ),
                    )
                )

            return self._failure(
                name=name,
                arguments=arguments,
                error=(
                    str(exc)
                    or type(exc).__name__
                ),
                elapsed_seconds=(
                    elapsed_seconds
                ),
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
            verification = (
                verify_action_result(
                    name,
                    arguments,
                    payload,
                )
            )
            verified = bool(
                verification.get(
                    "verified"
                )
            )
            progress = (
                self.plan_tracker
                .record_action(
                    tool_name=name,
                    verified=verified,
                    verification=verification,
                    error=(
                        str(payload.get("error") or "")
                        or (
                            "Postcondition verification failed."
                            if not verified
                            else None
                        )
                    ),
                )
            )
            payload["verification"] = (
                verification
            )
            if progress is not None:
                payload["plan_progress"] = (
                    progress
                )

        elif planning_tool:
            if isinstance(
                payload.get("result"),
                dict,
            ):
                progress = payload["result"]
            elif "status" in payload:
                progress = dict(payload)

        payload = {
            "success": True,
            **payload,
        }
        success = True
        if action and verified is False:
            success = False
            payload["success"] = False
            payload["error"] = (
                "The action ran, but its "
                "postcondition could not "
                "be verified."
            )

        return ToolExecutionResult(
            name=name,
            arguments=arguments,
            success=success,
            output=json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ),
            elapsed_seconds=(
                elapsed_seconds
            ),
            verified=verified,
            verification=verification,
            plan_progress=progress,
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
                    "Tool arguments must be "
                    "a JSON object."
                ),
            )

        precondition = (
            self._validate_plan_precondition(
                name=name,
                arguments=loaded,
            )
        )
        if precondition is not None:
            return precondition

        if (
            tool.confirmation is not None
            and self.confirmations.enabled
        ):
            return self._request_confirmation(
                tool=tool,
                arguments=loaded,
            )

        return self._execute_handler(
            tool=tool,
            arguments=loaded,
        )

    def confirmation_status_result(
        self,
    ) -> ToolExecutionResult:
        pending = self.confirmations.peek()
        if pending is None:
            return self._json_result(
                name=(
                    "confirmation_status"
                ),
                arguments={},
                success=True,
                payload={
                    "success": True,
                    "pending": False,
                    "message": (
                        "승인 대기 중인 작업이 "
                        "없습니다."
                    ),
                },
            )

        public = pending.as_public_dict()
        return self._json_result(
            name="confirmation_status",
            arguments={},
            success=True,
            confirmation_required=True,
            confirmation_id=(
                pending.action_id
            ),
            payload={
                "success": True,
                "pending": True,
                "pending_action": public,
                "message": (
                    f"승인 대기 작업: "
                    f"{pending.summary}. "
                    "진행하려면 "
                    f"'{pending.required_phrase}', "
                    "취소하려면 '취소'라고 "
                    "말해주세요."
                ),
            },
        )

    def cancel_pending_confirmation(
        self,
    ) -> ToolExecutionResult:
        pending = self.confirmations.cancel()
        if pending is None:
            return self._failure(
                name=(
                    "cancel_pending_confirmation"
                ),
                arguments={},
                error=(
                    "승인 대기 중인 작업이 "
                    "없습니다."
                ),
            )

        return self._json_result(
            name=(
                "cancel_pending_confirmation"
            ),
            arguments={},
            success=True,
            payload={
                "success": True,
                "cancelled": True,
                "action_id": (
                    pending.action_id
                ),
                "tool_name": (
                    pending.tool_name
                ),
                "message": (
                    "승인 대기 작업을 "
                    "취소했습니다."
                ),
            },
        )

    def approve_pending_confirmation(
        self,
        *,
        code: str | None = None,
    ) -> ToolExecutionResult:
        try:
            pending = (
                self.confirmations.approve(
                    code=code
                )
            )
        except ConfirmationCodeError as exc:
            return self._failure(
                name=(
                    "approve_pending_confirmation"
                ),
                arguments={
                    "code": code,
                },
                error=(
                    f"{exc} "
                    f"남은 시도 횟수: "
                    f"{exc.remaining_attempts}."
                ),
            )
        except ConfirmationError as exc:
            return self._failure(
                name=(
                    "approve_pending_confirmation"
                ),
                arguments={
                    "code": code,
                },
                error=str(exc),
            )

        tool = self._tools.get(
            pending.tool_name
        )
        if tool is None:
            return self._failure(
                name=pending.tool_name,
                arguments=(
                    pending.arguments
                ),
                error=(
                    "The approved tool is no "
                    "longer registered."
                ),
            )

        result = self._execute_handler(
            tool=tool,
            arguments=pending.arguments,
        )
        try:
            payload = json.loads(
                result.output
            )
        except json.JSONDecodeError:
            payload = {}
        if (
            result.success
            and isinstance(payload, dict)
            and not payload.get("message")
        ):
            payload["message"] = (
                "승인된 작업을 실행했습니다."
            )
            result = ToolExecutionResult(
                name=result.name,
                arguments=result.arguments,
                success=result.success,
                output=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                elapsed_seconds=(
                    result.elapsed_seconds
                ),
                verified=result.verified,
                verification=(
                    result.verification
                ),
                plan_progress=(
                    result.plan_progress
                ),
            )
        return result
