from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping


ToolHandler = Callable[..., Mapping[str, Any] | str | int | float | bool | None]


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


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    success: bool
    output: str


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self._tools.values()]

    def register(self, tool: ToolSpec) -> None:
        name = tool.name.strip()
        if not name:
            raise ValueError("Tool name must not be empty.")
        if name in self._tools:
            raise ValueError(f"Tool is already registered: {name}")

        parameter_type = tool.parameters.get("type")
        if parameter_type != "object":
            raise ValueError(
                f"Tool parameters must be an object schema: {name}"
            )
        if tool.parameters.get("additionalProperties") is not False:
            raise ValueError(
                f"Tool schema must disable additional properties: {name}"
            )

        self._tools[name] = tool

    def execute(
        self,
        name: str,
        arguments_json: str,
    ) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            output = json.dumps(
                {
                    "success": False,
                    "error": f"Unknown tool: {name}",
                },
                ensure_ascii=False,
            )
            return ToolExecutionResult(
                name=name,
                arguments={},
                success=False,
                output=output,
            )

        try:
            loaded = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            output = json.dumps(
                {
                    "success": False,
                    "error": f"Invalid tool arguments: {exc.msg}",
                },
                ensure_ascii=False,
            )
            return ToolExecutionResult(
                name=name,
                arguments={},
                success=False,
                output=output,
            )

        if not isinstance(loaded, dict):
            output = json.dumps(
                {
                    "success": False,
                    "error": "Tool arguments must be a JSON object.",
                },
                ensure_ascii=False,
            )
            return ToolExecutionResult(
                name=name,
                arguments={},
                success=False,
                output=output,
            )

        try:
            result = tool.handler(**loaded)
            payload = (
                dict(result)
                if isinstance(result, Mapping)
                else {"result": result}
            )
            payload = {"success": True, **payload}
            output = json.dumps(payload, ensure_ascii=False, default=str)
            return ToolExecutionResult(
                name=name,
                arguments=loaded,
                success=True,
                output=output,
            )
        except Exception as exc:
            output = json.dumps(
                {
                    "success": False,
                    "error": str(exc) or type(exc).__name__,
                },
                ensure_ascii=False,
            )
            return ToolExecutionResult(
                name=name,
                arguments=loaded,
                success=False,
                output=output,
            )
