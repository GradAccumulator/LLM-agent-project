from __future__ import annotations

from dataclasses import dataclass
import base64
import importlib
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from dotenv import load_dotenv

from src.tools import (
    ToolCallRecord,
    ToolRegistry,
    build_default_tool_registry,
)


DEFAULT_INSTRUCTIONS = """\
너는 Windows 데스크톱에서 동작하는 음성 비서 '자비스'다.

응답 원칙:
- 사용자가 다른 언어를 요구하지 않는 한 한국어로 답한다.
- 음성으로 읽기 좋도록 자연스럽고 간결하게 답한다.
- 답변은 음성으로 출력되므로 표, 긴 목록, 긴 코드 블록과 불필요한 마크다운을 피한다.
- 보통 1~3문장으로 답하고, 필요한 경우에만 더 자세히 설명한다.
- 사용자의 요청을 수행하는 데 등록된 도구가 필요하면 도구를 사용한다.
- 현재 화면의 내용, 오류, 코드, 앱 상태를 묻는 질문에는 추측하지 말고 inspect_screen 도구를 사용한다.
- inspect_screen 결과에 첨부된 이미지를 실제로 분석한 뒤 사용자의 원래 질문에 답한다.
- 화면에 보이지 않는 정보는 보인다고 단정하지 않는다.
- 도구를 사용하지 않고 실제 작업을 수행했다고 거짓말하지 않는다.
- 도구 결과가 실패라면 성공했다고 말하지 말고 실패 이유를 짧게 설명한다.
- 사용자가 요청하지 않은 앱 실행, 웹 검색, 사이트 열기, 메모 생성을 하지 않는다.
- 창 전환, 창 상태 변경, 미디어 키와 클립보드 변경은 사용자가 명시적으로 요청했을 때만 수행한다.
- 클립보드 읽기는 민감한 내용이 있을 수 있으므로 사용자가 내용을 읽어 달라고 직접 요청한 경우에만 수행한다.
- 임의 키 입력, 임의 좌표 클릭, 셸 명령 실행은 지원하지 않는다.
- 등록되지 않은 컴퓨터 작업은 아직 지원하지 않는다고 솔직하게 말한다.
- 확실하지 않은 내용은 추측해서 단정하지 않는다.
"""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    max_output_tokens: int = 512
    timeout_seconds: float = 60.0
    max_retries: int = 2
    use_memory: bool = True
    max_tool_rounds: int = 4
    tools_enabled: bool = True
    vision_detail: str = "original"
    max_vision_image_bytes: int = 25 * 1024 * 1024
    instructions: str = DEFAULT_INSTRUCTIONS


@dataclass(frozen=True, slots=True)
class AgentReply:
    text: str
    response_id: str
    model: str
    elapsed_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    tool_calls: tuple[ToolCallRecord, ...]


@dataclass(frozen=True, slots=True)
class ToolLifecycleEvent:
    phase: str
    name: str
    success: bool | None = None
    elapsed_seconds: float | None = None


ToolLifecycleCallback = Callable[[ToolLifecycleEvent], None]


class JarvisAgent:
    """OpenAI Responses API wrapper with local function tools."""

    _ALLOWED_REASONING_EFFORTS = {
        "none",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }

    def __init__(
        self,
        config: AgentConfig,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        if not config.model.strip():
            raise ValueError("LLM model must not be empty.")
        if (
            config.reasoning_effort
            not in self._ALLOWED_REASONING_EFFORTS
        ):
            allowed = ", ".join(sorted(self._ALLOWED_REASONING_EFFORTS))
            raise ValueError(
                f"Invalid reasoning effort. Choose one of: {allowed}."
            )
        if config.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive.")
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if config.max_retries < 0:
            raise ValueError("max_retries must not be negative.")
        if config.max_tool_rounds <= 0:
            raise ValueError("max_tool_rounds must be positive.")
        if config.vision_detail not in {"low", "high", "original", "auto"}:
            raise ValueError(
                "vision_detail must be low, high, original, or auto."
            )
        if config.max_vision_image_bytes <= 0:
            raise ValueError("max_vision_image_bytes must be positive.")

        load_dotenv()
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Copy .env.example to "
                ".env and put your API key in it, or set the Windows "
                "OPENAI_API_KEY environment variable."
            )

        try:
            openai_module = importlib.import_module("openai")
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI Python SDK is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        self.config = config
        self._client = openai_module.OpenAI(
            api_key=api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        self._tool_registry = (
            tool_registry
            if tool_registry is not None
            else build_default_tool_registry()
        )
        self._previous_response_id: str | None = None

    @property
    def previous_response_id(self) -> str | None:
        return self._previous_response_id

    @property
    def tool_names(self) -> tuple[str, ...]:
        if not self.config.tools_enabled:
            return ()
        return self._tool_registry.names

    def reset_conversation(self) -> None:
        self._previous_response_id = None

    @staticmethod
    def _usage_value(usage: Any, name: str) -> int | None:
        if usage is None:
            return None

        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)

        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _add_optional(
        current: int | None,
        value: int | None,
    ) -> int | None:
        if current is None and value is None:
            return None
        return (current or 0) + (value or 0)

    @staticmethod
    def _friendly_api_error(error: BaseException) -> RuntimeError:
        error_name = type(error).__name__
        message = str(error).strip()

        if error_name == "AuthenticationError":
            return RuntimeError(
                "OpenAI API authentication failed. Check OPENAI_API_KEY."
            )
        if error_name == "RateLimitError":
            return RuntimeError(
                "OpenAI API rate limit or billing limit was reached. "
                "Check the API usage and billing settings."
            )
        if error_name in {"APITimeoutError", "TimeoutException"}:
            return RuntimeError(
                "The OpenAI API request timed out. Try again or increase "
                "--llm-timeout."
            )
        if error_name == "APIConnectionError":
            return RuntimeError(
                "Could not connect to the OpenAI API. Check the internet "
                "connection."
            )
        if error_name == "APIStatusError":
            return RuntimeError(
                f"OpenAI API returned an error: {message or error_name}"
            )

        return RuntimeError(
            f"OpenAI response generation failed: {message or error_name}"
        )

    @staticmethod
    def _image_mime_type(path: Path, declared: str | None) -> str:
        allowed = {
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif",
        }
        if declared in allowed:
            return declared

        suffix_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = suffix_map.get(path.suffix.casefold())
        if mime_type is None:
            raise RuntimeError(
                f"Unsupported screenshot format: {path.suffix or '<none>'}"
            )
        return mime_type

    def _tool_output_content(
        self,
        *,
        tool_name: str,
        success: bool,
        output: str,
    ) -> str | list[dict[str, Any]]:
        """Convert a local tool result into Responses API tool output."""

        if tool_name != "inspect_screen" or not success:
            return output

        try:
            payload = json.loads(output)
            image_path_value = payload.get("image_path")
            if not isinstance(image_path_value, str) or not image_path_value:
                raise RuntimeError(
                    "inspect_screen did not return an image path."
                )

            image_path = Path(image_path_value)
            if not image_path.is_file():
                raise RuntimeError(
                    f"Captured screenshot does not exist: {image_path}"
                )

            image_size = image_path.stat().st_size
            if image_size > self.config.max_vision_image_bytes:
                raise RuntimeError(
                    "Captured screenshot is too large to attach "
                    f"({image_size} bytes)."
                )

            declared_mime = payload.get("mime_type")
            mime_type = self._image_mime_type(
                image_path,
                declared_mime if isinstance(declared_mime, str) else None,
            )
            encoded = base64.b64encode(
                image_path.read_bytes()
            ).decode("ascii")

            metadata = {
                key: value
                for key, value in payload.items()
                if key != "image_path"
            }
            metadata["image_attached"] = True

            return [
                {
                    "type": "input_text",
                    "text": json.dumps(
                        metadata,
                        ensure_ascii=False,
                        default=str,
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{mime_type};base64,{encoded}"
                    ),
                    "detail": self.config.vision_detail,
                },
            ]
        except Exception as exc:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        "The screenshot was captured but could not be "
                        f"attached for visual analysis: {exc}"
                    ),
                },
                ensure_ascii=False,
            )

    def _create_response(
        self,
        *,
        input_items: list[Any],
        previous_response_id: str | None,
    ) -> Any:
        request: dict[str, Any] = {
            "model": self.config.model,
            "instructions": self.config.instructions,
            "input": input_items,
            "reasoning": {"effort": self.config.reasoning_effort},
            "max_output_tokens": self.config.max_output_tokens,
            "store": self.config.use_memory,
        }

        if self.config.tools_enabled and self._tool_registry.names:
            request["tools"] = self._tool_registry.schemas
            request["tool_choice"] = "auto"

        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        try:
            return self._client.responses.create(**request)
        except Exception as exc:
            raise self._friendly_api_error(exc) from exc

    def ask(
        self,
        user_text: str,
        *,
        on_tool_event: ToolLifecycleCallback | None = None,
    ) -> AgentReply:
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("LLM input text must not be empty.")

        conversation_parent = (
            self._previous_response_id
            if self.config.use_memory
            else None
        )
        input_items: list[Any] = [
            {"role": "user", "content": user_text}
        ]

        tool_records: list[ToolCallRecord] = []
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None

        started_at = perf_counter()
        response = self._create_response(
            input_items=input_items,
            previous_response_id=conversation_parent,
        )

        for round_index in range(self.config.max_tool_rounds + 1):
            usage = getattr(response, "usage", None)
            input_tokens = self._add_optional(
                input_tokens,
                self._usage_value(usage, "input_tokens"),
            )
            output_tokens = self._add_optional(
                output_tokens,
                self._usage_value(usage, "output_tokens"),
            )
            total_tokens = self._add_optional(
                total_tokens,
                self._usage_value(usage, "total_tokens"),
            )

            function_calls = [
                item
                for item in getattr(response, "output", ())
                if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                break

            if round_index >= self.config.max_tool_rounds:
                raise RuntimeError(
                    "The model exceeded the maximum number of tool rounds."
                )

            # Preserve all model output, including reasoning items. Reasoning
            # models require these items to be returned with tool outputs.
            input_items.extend(getattr(response, "output", ()))

            for call in function_calls:
                tool_name = str(getattr(call, "name", ""))
                if on_tool_event is not None:
                    on_tool_event(
                        ToolLifecycleEvent(
                            phase="started",
                            name=tool_name,
                        )
                    )

                result = self._tool_registry.execute(
                    tool_name,
                    str(getattr(call, "arguments", "{}")),
                )

                if on_tool_event is not None:
                    on_tool_event(
                        ToolLifecycleEvent(
                            phase="finished",
                            name=result.name,
                            success=result.success,
                            elapsed_seconds=result.elapsed_seconds,
                        )
                    )

                tool_records.append(
                    ToolCallRecord(
                        name=result.name,
                        arguments=result.arguments,
                        success=result.success,
                        output=result.output,
                        elapsed_seconds=result.elapsed_seconds,
                    )
                )
                output_content = self._tool_output_content(
                    tool_name=result.name,
                    success=result.success,
                    output=result.output,
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(getattr(call, "call_id", "")),
                        "output": output_content,
                    }
                )

            response = self._create_response(
                input_items=input_items,
                previous_response_id=conversation_parent,
            )

        elapsed_seconds = perf_counter() - started_at
        text = str(getattr(response, "output_text", "") or "").strip()
        if not text:
            text = "응답을 생성하지 못했습니다."

        response_id = str(getattr(response, "id", "") or "")
        if self.config.use_memory and response_id:
            self._previous_response_id = response_id

        return AgentReply(
            text=text,
            response_id=response_id,
            model=str(getattr(response, "model", self.config.model)),
            elapsed_seconds=elapsed_seconds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            tool_calls=tuple(tool_records),
        )
