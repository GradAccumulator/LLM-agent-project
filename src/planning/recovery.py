from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any


class FailureCategory(str, Enum):
    STALE_REFERENCE = "stale_reference"
    AMBIGUOUS_TARGET = "ambiguous_target"
    VERIFICATION_FAILED = "verification_failed"
    INVALID_ARGUMENTS = "invalid_arguments"
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    PERMISSION_DENIED = "permission_denied"
    SAFETY_BLOCK = "safety_block"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    TRANSIENT = "transient"
    INVALID_STATE = "invalid_state"
    UNKNOWN = "unknown"


class ToolChannel(str, Enum):
    EDGE_DOM = "edge_dom"
    BROWSER_DOM = "browser_dom"
    WINDOWS_UIA = "windows_uia"
    VISION = "vision"
    CALENDAR = "calendar"
    GMAIL = "gmail"
    SCHEDULER = "scheduler"
    DESKTOP = "desktop"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class FailureAssessment:
    category: FailureCategory
    summary: str
    recoverable: bool
    user_intervention_required: bool
    recommended_strategy: str
    current_channel: ToolChannel
    recommended_tools: tuple[str, ...]
    signature: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["current_channel"] = self.current_channel.value
        data["recommended_tools"] = list(
            self.recommended_tools
        )
        return data


def tool_channel(tool_name: str) -> ToolChannel:
    name = tool_name.strip().casefold()
    if name.startswith("edge_cdp_"):
        return ToolChannel.EDGE_DOM
    if name.startswith("browser_"):
        return ToolChannel.BROWSER_DOM
    if name.startswith("uia_"):
        return ToolChannel.WINDOWS_UIA
    if name in {
        "inspect_screen",
        "uia_capture_window_context",
        "edge_cdp_capture_tab",
    }:
        return ToolChannel.VISION
    if name.startswith("google_calendar_"):
        return ToolChannel.CALENDAR
    if name.startswith("gmail_"):
        return ToolChannel.GMAIL
    if (
        name.startswith("schedule_")
        or "scheduled_reminder" in name
    ):
        return ToolChannel.SCHEDULER
    if name in {
        "open_application",
        "open_website",
        "search_browser",
        "focus_window",
        "set_window_state",
        "media_control",
        "set_clipboard_text",
        "create_note",
    }:
        return ToolChannel.DESKTOP
    return ToolChannel.OTHER


def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _compact_text(
    verification: dict[str, Any] | None,
    error: str | None,
) -> str:
    parts = [str(error or "")]
    if verification:
        try:
            parts.append(
                json.dumps(
                    verification,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
        except Exception:
            parts.append(str(verification))
    return " ".join(" ".join(parts).split())[:8_000]


def _category(text: str, verification: dict[str, Any] | None) -> FailureCategory:
    strength = str(
        (verification or {}).get("strength") or ""
    ).casefold()
    if strength == "precondition":
        return FailureCategory.INVALID_STATE
    if _search(r"stale|expired|detached|reference.+(?:missing|invalid)|element.+not.+attached", text):
        return FailureCategory.STALE_REFERENCE
    if _search(r"ambiguous|multiple matches|more than one|여러 개|모호", text):
        return FailureCategory.AMBIGUOUS_TARGET
    if _search(r"429|rate.?limit|too many requests", text):
        return FailureCategory.RATE_LIMITED
    if _search(r"401|oauth|token.+expired|credentials|scope.+required|re.?auth|인증.+필요", text):
        return FailureCategory.AUTH_REQUIRED
    if _search(r"403|permission denied|access denied|권한.+없|not allowed by policy", text):
        return FailureCategory.PERMISSION_DENIED
    if _search(r"safety|blocked|password|otp|payment|card|계좌|결제|송금|위험", text):
        return FailureCategory.SAFETY_BLOCK
    if _search(r"invalid.+(?:argument|parameter|schema|type)|missing required|unexpected keyword|잘못된.+인자", text):
        return FailureCategory.INVALID_ARGUMENTS
    if _search(r"timeout|timed out|network|connection|dns|unreachable|temporarily unavailable|socket", text):
        return FailureCategory.NETWORK
    if _search(r"busy|loading|not ready|try again|temporar", text):
        return FailureCategory.TRANSIENT
    if _search(r"not found|no usable|missing|disabled|unavailable|could not find", text):
        return FailureCategory.UNAVAILABLE
    if _search(r"unsupported|not supported|cannot be used|지원하지", text):
        return FailureCategory.UNSUPPORTED
    if (
        (verification or {}).get("verified") is False
        or _search(r"postcondition|could not be verified|no observed change|verification", text)
    ):
        return FailureCategory.VERIFICATION_FAILED
    return FailureCategory.UNKNOWN


def _recommendations(
    channel: ToolChannel,
    category: FailureCategory,
    *,
    tool_switching_enabled: bool,
) -> tuple[str, tuple[str, ...]]:
    if category in {
        FailureCategory.SAFETY_BLOCK,
        FailureCategory.PERMISSION_DENIED,
        FailureCategory.AUTH_REQUIRED,
    }:
        return "ask_user", ()

    if category is FailureCategory.INVALID_ARGUMENTS:
        return "repair_arguments", ()

    if category in {
        FailureCategory.NETWORK,
        FailureCategory.RATE_LIMITED,
        FailureCategory.TRANSIENT,
    }:
        return "retry_once_with_fresh_state", ()

    if channel is ToolChannel.EDGE_DOM:
        if category in {
            FailureCategory.STALE_REFERENCE,
            FailureCategory.AMBIGUOUS_TARGET,
        }:
            return (
                "requery_exact_target",
                (
                    "edge_cdp_find_element",
                    "edge_cdp_list_elements",
                    "edge_cdp_get_page_info",
                ),
            )
        if tool_switching_enabled:
            return (
                "switch_tool_channel",
                (
                    "uia_capture_window_context",
                    "uia_find_elements",
                    "inspect_screen",
                ),
            )
        return "requery_exact_target", ("edge_cdp_get_page_info",)

    if channel is ToolChannel.BROWSER_DOM:
        if tool_switching_enabled:
            return (
                "switch_tool_channel",
                (
                    "edge_cdp_find_tabs",
                    "edge_cdp_get_page_info",
                    "edge_cdp_find_element",
                    "uia_capture_window_context",
                ),
            )
        return "retry_with_fresh_page", ("browser_get_page_info",)

    if channel is ToolChannel.WINDOWS_UIA:
        return (
            "refresh_window_context",
            (
                "uia_find_windows",
                "uia_inspect_window",
                "uia_capture_window_context",
                "inspect_screen",
            ),
        )

    if channel is ToolChannel.VISION:
        return (
            "switch_to_structured_ui",
            (
                "uia_find_windows",
                "uia_find_elements",
                "edge_cdp_list_tabs",
            ),
        )

    if channel in {
        ToolChannel.CALENDAR,
        ToolChannel.GMAIL,
        ToolChannel.SCHEDULER,
    }:
        if category in {
            FailureCategory.UNAVAILABLE,
            FailureCategory.UNSUPPORTED,
        }:
            return "inspect_service_status", ()
        return "retry_with_refreshed_data", ()

    if tool_switching_enabled:
        return (
            "inspect_then_switch_tool",
            (
                "get_active_window",
                "uia_find_windows",
                "inspect_screen",
            ),
        )
    return "retry_with_fresh_state", ()


def assess_failure(
    *,
    tool_name: str,
    verification: dict[str, Any] | None,
    error: str | None,
    tool_switching_enabled: bool = True,
) -> FailureAssessment:
    text = _compact_text(verification, error)
    category = _category(text, verification)
    channel = tool_channel(tool_name)
    strategy, tools = _recommendations(
        channel,
        category,
        tool_switching_enabled=tool_switching_enabled,
    )
    recoverable = category not in {
        FailureCategory.SAFETY_BLOCK,
        FailureCategory.PERMISSION_DENIED,
        FailureCategory.AUTH_REQUIRED,
        FailureCategory.UNSUPPORTED,
    }
    needs_user = category in {
        FailureCategory.SAFETY_BLOCK,
        FailureCategory.PERMISSION_DENIED,
        FailureCategory.AUTH_REQUIRED,
    }
    summary_map = {
        FailureCategory.STALE_REFERENCE: "참조가 만료되거나 대상이 페이지에서 분리되었습니다.",
        FailureCategory.AMBIGUOUS_TARGET: "대상 후보가 여러 개라 안전하게 하나를 고를 수 없습니다.",
        FailureCategory.VERIFICATION_FAILED: "도구 실행 후 기대한 상태 변화를 확인하지 못했습니다.",
        FailureCategory.INVALID_ARGUMENTS: "도구 인자나 스키마가 현재 호출과 맞지 않습니다.",
        FailureCategory.NETWORK: "네트워크 또는 연결 단계에서 일시적 오류가 발생했습니다.",
        FailureCategory.RATE_LIMITED: "서비스 호출 한도에 걸렸습니다.",
        FailureCategory.AUTH_REQUIRED: "인증 또는 OAuth 재승인이 필요합니다.",
        FailureCategory.PERMISSION_DENIED: "현재 권한으로 작업을 실행할 수 없습니다.",
        FailureCategory.SAFETY_BLOCK: "안전 정책상 자동 실행할 수 없는 작업입니다.",
        FailureCategory.UNAVAILABLE: "필요한 대상이나 서비스가 현재 사용 불가능합니다.",
        FailureCategory.UNSUPPORTED: "현재 도구가 이 작업을 지원하지 않습니다.",
        FailureCategory.TRANSIENT: "대상이 아직 준비되지 않은 일시적 상태입니다.",
        FailureCategory.INVALID_STATE: "계획 또는 도구의 선행 상태가 충족되지 않았습니다.",
        FailureCategory.UNKNOWN: "실패 원인을 특정 범주로 확정하지 못했습니다.",
    }
    normalized_error = " ".join(str(error or "").split())[:500]
    digest_source = json.dumps(
        {
            "tool": tool_name,
            "category": category.value,
            "error": normalized_error.casefold(),
            "strength": str((verification or {}).get("strength") or ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    signature = hashlib.sha256(
        digest_source.encode("utf-8")
    ).hexdigest()[:16]
    return FailureAssessment(
        category=category,
        summary=summary_map[category],
        recoverable=recoverable,
        user_intervention_required=needs_user,
        recommended_strategy=strategy,
        current_channel=channel,
        recommended_tools=tools,
        signature=signature,
    )
