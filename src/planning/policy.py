from __future__ import annotations

from pathlib import Path
import re
from typing import Any


PLANNING_TOOLS = {
    "begin_task_plan",
    "get_task_plan",
    "complete_plan_step",
    "fail_plan_step",
    "finish_task_plan",
    "abandon_task_plan",
}

ACTION_TOOLS = {
    "open_application",
    "open_website",
    "search_browser",
    "create_note",
    "focus_window",
    "set_window_state",
    "media_control",
    "set_clipboard_text",
    "browser_open_page",
    "browser_click_text",
    "browser_fill_field",
    "browser_press_key",
    "browser_go_back",
    "browser_close",
    "schedule_relative_reminder",
    "schedule_reminder",
    "schedule_recurring_reminder",
    "cancel_scheduled_reminder",
    "snooze_scheduled_reminder",
    "google_calendar_create_event",
    "google_calendar_update_event",
    "google_calendar_delete_event",
    "uia_focus_element",
    "uia_invoke_element",
    "uia_set_value",
    "uia_toggle_element",
    "uia_select_element",
}

_SEQUENCE_MARKERS = (
    "그리고",
    "그다음",
    "그 다음",
    "다음에",
    "한 다음",
    "한 뒤",
    "후에",
    "열고",
    "켜고",
    "찾아서",
    "검색해서",
    "입력하고",
    "클릭하고",
    "눌러서",
    "재생해",
    "요약해서",
    "저장하고",
)

_ACTION_PATTERNS = (
    r"열어|켜줘|실행",
    r"검색|찾아",
    r"클릭|눌러",
    r"입력|채워",
    r"재생|일시정지|다음\s*곡",
    r"복사|저장|메모",
    r"전환|최소화|최대화|복원",
    r"뒤로\s*가",
)


def should_plan_request(
    text: str,
    *,
    enabled: bool,
) -> bool:
    if not enabled:
        return False

    normalized = " ".join(text.strip().split())
    if not normalized:
        return False

    if any(
        marker in normalized
        for marker in _SEQUENCE_MARKERS
    ):
        return True

    action_groups = sum(
        bool(re.search(pattern, normalized))
        for pattern in _ACTION_PATTERNS
    )
    if action_groups >= 2:
        return True

    clauses = [
        clause.strip()
        for clause in re.split(
            r"(?:,|그리고|그다음|그 다음|후에|한 뒤)",
            normalized,
        )
        if clause.strip()
    ]
    actionable_clauses = sum(
        any(
            re.search(pattern, clause)
            for pattern in _ACTION_PATTERNS
        )
        for clause in clauses
    )
    return actionable_clauses >= 2


def is_action_tool(name: str) -> bool:
    return name in ACTION_TOOLS


def is_planning_tool(name: str) -> bool:
    return name in PLANNING_TOOLS


def verify_action_result(
    tool_name: str,
    arguments: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Return compact postcondition evidence for a successful action."""

    verified = True
    strength = "acknowledged"
    evidence: dict[str, Any] = {}

    if tool_name == "browser_open_page":
        status = payload.get("status")
        url = str(payload.get("url") or "")
        verified = bool(url) and (
            status is None
            or (
                isinstance(status, int)
                and 200 <= status < 400
            )
        )
        strength = "strong"
        evidence = {
            "url": url,
            "title": payload.get("title"),
            "status": status,
        }

    elif tool_name == "browser_click_text":
        verified = bool(
            payload.get("clicked_text")
            and payload.get("url")
        )
        strength = "moderate"
        evidence = {
            "clicked_text": payload.get("clicked_text"),
            "url": payload.get("url"),
            "title": payload.get("title"),
        }

    elif tool_name == "browser_fill_field":
        expected = len(str(arguments.get("value") or ""))
        verified = payload.get("characters") == expected
        strength = "moderate"
        evidence = {
            "field": payload.get("field"),
            "characters": payload.get("characters"),
            "expected_characters": expected,
            "url": payload.get("url"),
        }

    elif tool_name == "browser_press_key":
        verified = payload.get("key") == arguments.get("key")
        strength = "moderate"
        evidence = {
            "key": payload.get("key"),
            "url": payload.get("url"),
        }

    elif tool_name == "browser_go_back":
        verified = payload.get("navigated") is True
        strength = "strong"
        evidence = {
            "navigated": payload.get("navigated"),
            "url": payload.get("url"),
            "title": payload.get("title"),
        }

    elif tool_name in {
        "schedule_relative_reminder",
        "schedule_reminder",
        "schedule_recurring_reminder",
    }:
        task = payload.get("task") or {}
        verified = (
            payload.get("scheduled") is True
            and isinstance(task, dict)
            and task.get("status") == "active"
            and bool(task.get("next_run_at"))
        )
        strength = "strong"
        evidence = {
            "scheduled": payload.get("scheduled"),
            "task_id": task.get("id") if isinstance(task, dict) else None,
            "next_run_at": task.get("next_run_at") if isinstance(task, dict) else None,
        }

    elif tool_name == "cancel_scheduled_reminder":
        verified = payload.get("cancelled") is True
        strength = "strong"
        evidence = {"cancelled": payload.get("cancelled"), "task": payload.get("task")}

    elif tool_name == "snooze_scheduled_reminder":
        verified = payload.get("snoozed") is True
        strength = "strong"
        evidence = {"snoozed": payload.get("snoozed"), "task": payload.get("task")}

    elif tool_name == "google_calendar_create_event":
        event = payload.get("event") or {}
        verified = (
            payload.get("created") is True
            and payload.get("verified") is True
            and isinstance(event, dict)
            and bool(event.get("id"))
        )
        strength = "strong"
        evidence = {
            "created": payload.get("created"),
            "api_verified": payload.get("verified"),
            "event_id": (
                event.get("id")
                if isinstance(event, dict)
                else None
            ),
            "summary": (
                event.get("summary")
                if isinstance(event, dict)
                else None
            ),
        }

    elif tool_name == "google_calendar_update_event":
        event = payload.get("event") or {}
        verified = (
            payload.get("updated") is True
            and payload.get("verified") is True
            and isinstance(event, dict)
            and event.get("id")
            == arguments.get("event_id")
        )
        strength = "strong"
        evidence = {
            "updated": payload.get("updated"),
            "api_verified": payload.get("verified"),
            "event_id": (
                event.get("id")
                if isinstance(event, dict)
                else None
            ),
            "changed_fields": payload.get(
                "changed_fields"
            ),
        }

    elif tool_name == "google_calendar_delete_event":
        verified = (
            payload.get("deleted") is True
            and payload.get(
                "deletion_verified"
            ) is True
        )
        strength = "strong"
        evidence = {
            "deleted": payload.get("deleted"),
            "deletion_verified": payload.get(
                "deletion_verified"
            ),
            "event_id": arguments.get(
                "event_id"
            ),
        }

    elif tool_name == "uia_focus_element":
        verified = payload.get("focused") is True
        strength = "moderate"
        evidence = {
            "focused": payload.get("focused"),
            "element_ref": payload.get("element_ref"),
            "name": payload.get("name"),
        }

    elif tool_name == "uia_invoke_element":
        verified = payload.get("invoked") is True
        strength = "acknowledged"
        evidence = {
            "invoked": payload.get("invoked"),
            "element_ref": payload.get("element_ref"),
            "name": payload.get("name"),
        }

    elif tool_name == "uia_set_value":
        verified = (
            payload.get("value_set") is True
            and payload.get("verified") is True
        )
        strength = "strong"
        evidence = {
            "value_set": payload.get("value_set"),
            "verified": payload.get("verified"),
            "characters": payload.get("characters"),
            "element_ref": payload.get("element_ref"),
        }

    elif tool_name == "uia_toggle_element":
        verified = (
            payload.get("toggled") is True
            and payload.get("verified") is True
        )
        strength = "strong"
        evidence = {
            "toggled": payload.get("toggled"),
            "state_before": payload.get("state_before"),
            "state_after": payload.get("state_after"),
        }

    elif tool_name == "uia_select_element":
        verified = payload.get("selected") is True
        strength = "strong"
        evidence = {
            "selected": payload.get("selected"),
            "element_ref": payload.get("element_ref"),
        }

    elif tool_name == "browser_close":
        # Closing an already-closed browser is an idempotent success.
        verified = "message" in payload
        strength = "moderate"
        evidence = {
            "closed": payload.get("closed"),
            "message": payload.get("message"),
        }

    elif tool_name == "create_note":
        path_value = payload.get("path")
        path = (
            Path(path_value)
            if isinstance(path_value, str)
            else None
        )
        verified = bool(path and path.is_file())
        strength = "strong"
        evidence = {
            "path": path_value,
            "exists": verified,
        }

    elif tool_name == "focus_window":
        verified = payload.get("focused") is True
        strength = "strong"
        evidence = {
            "focused": payload.get("focused"),
            "window": payload.get("window"),
        }

    elif tool_name == "set_window_state":
        requested = arguments.get("state")
        expected = {
            "minimize": "minimized",
            "maximize": "maximized",
            "restore": "normal",
        }.get(str(requested))
        window = payload.get("window") or {}
        actual = (
            window.get("state")
            if isinstance(window, dict)
            else None
        )
        verified = actual == expected
        strength = "strong"
        evidence = {
            "requested": requested,
            "expected": expected,
            "actual": actual,
            "window_id": (
                window.get("window_id")
                if isinstance(window, dict)
                else None
            ),
        }

    elif tool_name == "set_clipboard_text":
        expected = len(str(arguments.get("text") or ""))
        verified = payload.get("characters") == expected
        strength = "moderate"
        evidence = {
            "characters": payload.get("characters"),
            "expected_characters": expected,
        }

    elif tool_name in {
        "open_application",
        "open_website",
        "search_browser",
        "media_control",
    }:
        verified = bool(payload.get("message"))
        evidence = {
            key: payload.get(key)
            for key in (
                "message",
                "application",
                "site",
                "url",
                "query",
                "action",
            )
            if key in payload
        }

    else:
        verified = bool(payload)
        evidence = {
            "payload_keys": sorted(payload),
        }

    return {
        "verified": bool(verified),
        "strength": strength,
        "tool": tool_name,
        "evidence": evidence,
    }
