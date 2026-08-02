from __future__ import annotations
from typing import Any
from src.google_calendar import GoogleCalendarClient
from .registry import ToolRegistry, ToolSpec


def register_google_calendar_tools(
    registry: ToolRegistry,
    client: GoogleCalendarClient,
) -> None:
    registry.register(ToolSpec(
        name="google_calendar_status",
        description=(
            "Google Calendar 읽기 전용 OAuth 연결 상태를 확인한다."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=client.status,
    ))

    registry.register(ToolSpec(
        name="google_calendar_list_calendars",
        description=(
            "접근 가능한 Google Calendar 목록과 calendar_id를 읽기 전용으로 조회한다."
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
            "calendars": list(client.list_calendars(max_results)),
        },
    ))

    registry.register(ToolSpec(
        name="google_calendar_list_events",
        description=(
            "기간 내 Google Calendar 일정을 읽기 전용으로 조회한다. "
            "오늘·내일 등 상대 날짜는 먼저 get_current_datetime을 호출한다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "calendar_id": {"type": ["string", "null"]},
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 2500,
                },
                "query": {"type": ["string", "null"]},
            },
            "required": [
                "time_min", "time_max", "calendar_id",
                "max_results", "query",
            ],
            "additionalProperties": False,
        },
        handler=lambda time_min, time_max, calendar_id, max_results, query: {
            "read_only": True,
            "events": list(client.list_events(
                time_min=time_min,
                time_max=time_max,
                calendar_id=calendar_id,
                max_results=max_results,
                query=query,
            )),
        },
    ))

    registry.register(ToolSpec(
        name="google_calendar_find_free_time",
        description=(
            "여러 캘린더의 busy 시간을 합쳐 빈 시간 후보를 읽기 전용으로 계산한다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "duration_minutes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1440,
                },
                "calendar_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 20,
                },
                "working_hours_start": {"type": "string"},
                "working_hours_end": {"type": "string"},
                "max_slots": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [
                "time_min", "time_max", "duration_minutes",
                "calendar_ids", "working_hours_start",
                "working_hours_end", "max_slots",
            ],
            "additionalProperties": False,
        },
        handler=lambda **kwargs: {
            "read_only": True,
            "slots": list(client.find_free_slots(**kwargs)),
        },
    ))
