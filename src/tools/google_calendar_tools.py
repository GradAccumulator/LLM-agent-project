from __future__ import annotations

from typing import Any

from src.confirmation import (
    ConfirmationRequirement,
    ConfirmationRisk,
)
from src.google_calendar import (
    GoogleCalendarClient,
)

from .registry import ToolRegistry, ToolSpec


def _calendar_id(
    client: GoogleCalendarClient,
    arguments: dict[str, Any],
) -> str:
    return str(
        arguments.get("calendar_id")
        or client.config.default_calendar_id
    )


def _create_summary(
    client: GoogleCalendarClient,
    arguments: dict[str, Any],
) -> str:
    title = str(
        arguments.get("summary")
        or "(제목 없음)"
    )
    start = str(
        arguments.get("start")
        or ""
    )
    end = str(
        arguments.get("end")
        or ""
    )
    return (
        f"Google Calendar "
        f"'{_calendar_id(client, arguments)}'에 "
        f"'{title[:100]}' 일정 생성 "
        f"({start} ~ {end})"
    )


def _update_summary(
    client: GoogleCalendarClient,
    arguments: dict[str, Any],
) -> str:
    title = str(
        arguments.get("event_summary")
        or "(제목 없음)"
    )
    event_id = str(
        arguments.get("event_id")
        or ""
    )
    changed: list[str] = []
    for field, label in (
        ("summary", "제목"),
        ("start", "시작"),
        ("end", "종료"),
        ("description", "설명"),
        ("location", "장소"),
    ):
        if arguments.get(field) is not None:
            changed.append(label)
    fields = ", ".join(changed) or "일정 정보"
    return (
        f"Google Calendar "
        f"'{_calendar_id(client, arguments)}'의 "
        f"'{title[:100]}' 일정 수정 "
        f"(ID {event_id}, 변경: {fields})"
    )


def _delete_summary(
    client: GoogleCalendarClient,
    arguments: dict[str, Any],
) -> str:
    title = str(
        arguments.get("event_summary")
        or "(제목 없음)"
    )
    start = str(
        arguments.get("event_start")
        or "시간 미상"
    )
    event_id = str(
        arguments.get("event_id")
        or ""
    )
    return (
        f"Google Calendar "
        f"'{_calendar_id(client, arguments)}'의 "
        f"'{title[:100]}' 일정 영구 삭제 "
        f"({start}, ID {event_id})"
    )


def register_google_calendar_tools(
    registry: ToolRegistry,
    client: GoogleCalendarClient,
) -> None:
    registry.register(
        ToolSpec(
            name="google_calendar_status",
            description=(
                "Google Calendar OAuth 상태, 필요한 scope, "
                "쓰기 가능 여부를 확인한다."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=client.status,
        )
    )

    registry.register(
        ToolSpec(
            name="google_calendar_list_calendars",
            description=(
                "접근 가능한 Google Calendar 목록과 ID를 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 250,
                    }
                },
                "required": ["max_results"],
                "additionalProperties": False,
            },
            handler=lambda max_results: {
                "read_only": True,
                "calendars": list(
                    client.list_calendars(
                        max_results
                    )
                ),
            },
        )
    )

    registry.register(
        ToolSpec(
            name="google_calendar_get_event",
            description=(
                "정확한 calendar_id와 event_id로 일정 하나를 조회한다. "
                "수정·삭제 전에 대상 확인에 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "event_id": {
                        "type": "string",
                    },
                },
                "required": [
                    "calendar_id",
                    "event_id",
                ],
                "additionalProperties": False,
            },
            handler=lambda calendar_id, event_id: {
                "read_only": True,
                "event": client.get_event(
                    calendar_id=calendar_id,
                    event_id=event_id,
                ),
            },
        )
    )

    registry.register(
        ToolSpec(
            name="google_calendar_list_events",
            description=(
                "기간 내 Google Calendar 일정을 조회한다. "
                "오늘·내일 등 상대 날짜는 먼저 "
                "get_current_datetime을 호출한다. "
                "수정·삭제할 일정의 정확한 event_id를 찾을 때도 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                    },
                    "time_max": {
                        "type": "string",
                    },
                    "calendar_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 2500,
                    },
                    "query": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
                "required": [
                    "time_min",
                    "time_max",
                    "calendar_id",
                    "max_results",
                    "query",
                ],
                "additionalProperties": False,
            },
            handler=lambda **kwargs: {
                "read_only": True,
                "events": list(
                    client.list_events(**kwargs)
                ),
            },
        )
    )

    registry.register(
        ToolSpec(
            name="google_calendar_find_free_time",
            description=(
                "여러 캘린더의 busy 시간을 합쳐 "
                "빈 시간 후보를 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                    },
                    "time_max": {
                        "type": "string",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1440,
                    },
                    "calendar_ids": {
                        "type": "array",
                        "items": {
                            "type": "string",
                        },
                        "minItems": 1,
                        "maxItems": 20,
                    },
                    "working_hours_start": {
                        "type": "string",
                    },
                    "working_hours_end": {
                        "type": "string",
                    },
                    "max_slots": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": [
                    "time_min",
                    "time_max",
                    "duration_minutes",
                    "calendar_ids",
                    "working_hours_start",
                    "working_hours_end",
                    "max_slots",
                ],
                "additionalProperties": False,
            },
            handler=lambda **kwargs: {
                "read_only": True,
                "slots": list(
                    client.find_free_slots(
                        **kwargs
                    )
                ),
            },
        )
    )

    allow_writes = bool(
        getattr(
            getattr(client, "config", None),
            "allow_writes",
            False,
        )
    )
    if not allow_writes:
        return

    registry.register(
        ToolSpec(
            name="google_calendar_create_event",
            description=(
                "Google Calendar 일정을 생성한다. "
                "실행 전 별도 승인이 필요하다. "
                "초대 참석자는 지원하지 않고 알림 메일도 보내지 않는다. "
                "종일 일정의 end는 Google 규칙에 따라 exclusive 날짜다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "summary": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                    },
                    "start": {
                        "type": "string",
                    },
                    "end": {
                        "type": "string",
                    },
                    "all_day": {
                        "type": "boolean",
                    },
                    "timezone_name": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "description": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "location": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
                "required": [
                    "calendar_id",
                    "summary",
                    "start",
                    "end",
                    "all_day",
                    "timezone_name",
                    "description",
                    "location",
                ],
                "additionalProperties": False,
            },
            handler=lambda **kwargs: (
                client.create_event(**kwargs)
            ),
            confirmation=(
                ConfirmationRequirement(
                    summary=lambda arguments: (
                        _create_summary(
                            client,
                            arguments,
                        )
                    ),
                    risk=(
                        ConfirmationRisk.STANDARD
                    ),
                )
            ),
        )
    )

    registry.register(
        ToolSpec(
            name="google_calendar_update_event",
            description=(
                "정확한 event_id의 Google Calendar 일정을 부분 수정한다. "
                "먼저 일정을 조회해 대상이 하나로 확정된 경우에만 호출한다. "
                "null은 변경하지 않음을 뜻하고 빈 문자열은 설명·장소를 지운다. "
                "실행 전 별도 승인이 필요하다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "event_id": {
                        "type": "string",
                    },
                    "event_summary": {
                        "type": "string",
                    },
                    "existing_start": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "summary": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "start": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "end": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "all_day": {
                        "type": [
                            "boolean",
                            "null",
                        ],
                    },
                    "timezone_name": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "description": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "location": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
                "required": [
                    "calendar_id",
                    "event_id",
                    "event_summary",
                    "existing_start",
                    "summary",
                    "start",
                    "end",
                    "all_day",
                    "timezone_name",
                    "description",
                    "location",
                ],
                "additionalProperties": False,
            },
            handler=lambda calendar_id, event_id, event_summary, existing_start, summary, start, end, all_day, timezone_name, description, location: client.update_event(
                calendar_id=calendar_id,
                event_id=event_id,
                summary=summary,
                start=start,
                end=end,
                all_day=all_day,
                timezone_name=timezone_name,
                description=description,
                location=location,
            ),
            confirmation=(
                ConfirmationRequirement(
                    summary=lambda arguments: (
                        _update_summary(
                            client,
                            arguments,
                        )
                    ),
                    risk=(
                        ConfirmationRisk.STANDARD
                    ),
                )
            ),
        )
    )

    registry.register(
        ToolSpec(
            name="google_calendar_delete_event",
            description=(
                "정확한 event_id의 Google Calendar 일정을 영구 삭제한다. "
                "먼저 일정을 조회해 대상이 하나로 확정된 경우에만 호출한다. "
                "고위험 작업이라 표시된 숫자 코드가 포함된 별도 승인이 필요하다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "event_id": {
                        "type": "string",
                    },
                    "event_summary": {
                        "type": "string",
                    },
                    "event_start": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
                "required": [
                    "calendar_id",
                    "event_id",
                    "event_summary",
                    "event_start",
                ],
                "additionalProperties": False,
            },
            handler=lambda calendar_id, event_id, event_summary, event_start: client.delete_event(
                calendar_id=calendar_id,
                event_id=event_id,
            ),
            confirmation=(
                ConfirmationRequirement(
                    summary=lambda arguments: (
                        _delete_summary(
                            client,
                            arguments,
                        )
                    ),
                    risk=(
                        ConfirmationRisk.HIGH
                    ),
                )
            ),
        )
    )
