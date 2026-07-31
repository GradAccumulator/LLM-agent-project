from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from time import perf_counter
from typing import Any

from dotenv import load_dotenv


DEFAULT_INSTRUCTIONS = """\
너는 Windows 데스크톱에서 동작하는 음성 비서 '자비스'다.

응답 원칙:
- 사용자가 다른 언어를 요구하지 않는 한 한국어로 답한다.
- 음성으로 읽기 좋도록 자연스럽고 간결하게 답한다.
- 보통 1~3문장으로 답하고, 필요한 경우에만 더 자세히 설명한다.
- 현재 단계에서는 컴퓨터 제어 도구가 연결되어 있지 않다.
- 실제로 수행하지 않은 컴퓨터 작업을 수행했다고 말하지 않는다.
- 컴퓨터 조작 요청을 받으면 아직 제어 기능이 연결되지 않았다고 짧게 알린다.
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


class JarvisAgent:
    """Small wrapper around the OpenAI Responses API."""

    _ALLOWED_REASONING_EFFORTS = {
        "none",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }

    def __init__(self, config: AgentConfig) -> None:
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
        self._openai = openai_module
        self._client = openai_module.OpenAI(
            api_key=api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        self._previous_response_id: str | None = None

    @property
    def previous_response_id(self) -> str | None:
        return self._previous_response_id

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

    def ask(self, user_text: str) -> AgentReply:
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("LLM input text must not be empty.")

        request: dict[str, Any] = {
            "model": self.config.model,
            "instructions": self.config.instructions,
            "input": [{"role": "user", "content": user_text}],
            "reasoning": {"effort": self.config.reasoning_effort},
            "max_output_tokens": self.config.max_output_tokens,
            "store": self.config.use_memory,
        }

        if self.config.use_memory and self._previous_response_id:
            request["previous_response_id"] = self._previous_response_id

        started_at = perf_counter()
        try:
            response = self._client.responses.create(**request)
        except Exception as exc:
            # Keep OpenAI SDK-specific exception imports out of module import
            # time so users get a clean dependency/setup error.
            raise self._friendly_api_error(exc) from exc
        elapsed_seconds = perf_counter() - started_at

        text = str(getattr(response, "output_text", "") or "").strip()
        if not text:
            text = "응답을 생성하지 못했습니다."

        response_id = str(getattr(response, "id", "") or "")
        if self.config.use_memory and response_id:
            self._previous_response_id = response_id

        usage = getattr(response, "usage", None)
        return AgentReply(
            text=text,
            response_id=response_id,
            model=str(getattr(response, "model", self.config.model)),
            elapsed_seconds=elapsed_seconds,
            input_tokens=self._usage_value(usage, "input_tokens"),
            output_tokens=self._usage_value(usage, "output_tokens"),
            total_tokens=self._usage_value(usage, "total_tokens"),
        )
