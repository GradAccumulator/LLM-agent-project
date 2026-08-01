from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Callable, Mapping


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


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    success: bool
    output: str
    elapsed_seconds: float


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [
            tool.as_openai_tool()
            for tool in self._tools.values()
        ]

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

    @staticmethod
    def _failure(
        *,
        name: str,
        arguments: dict[str, Any],
        error: str,
        elapsed_seconds: float = 0.0,
    ) -> ToolExecutionResult:
        output = json.dumps(
            {
                "success": False,
                "error": error,
            },
            ensure_ascii=False,
        )
        return ToolExecutionResult(
            name=name,
            arguments=arguments,
            success=False,
            output=output,
            elapsed_seconds=elapsed_seconds,
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
            loaded = json.loads(arguments_json or "{}")
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

        started_at = perf_counter()
        try:
            result = tool.handler(**loaded)
            elapsed_seconds = perf_counter() - started_at
            payload = (
                dict(result)
                if isinstance(result, Mapping)
                else {"result": result}
            )
            payload = {"success": True, **payload}
            output = json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
            return ToolExecutionResult(
                name=name,
                arguments=loaded,
                success=True,
                output=output,
                elapsed_seconds=elapsed_seconds,
            )
        except Exception as exc:
            return self._failure(
                name=name,
                arguments=loaded,
                error=str(exc) or type(exc).__name__,
                elapsed_seconds=(
                    perf_counter() - started_at
                ),
            )
