from __future__ import annotations

from typing import Any

from src.gmail import GmailClient

from .registry import ToolRegistry, ToolSpec


def register_gmail_tools(
    registry: ToolRegistry,
    client: GmailClient,
) -> None:
    registry.register(
        ToolSpec(
            name="gmail_status",
            description=(
                "Gmail 읽기 전용 OAuth 연결 상태를 확인한다."
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
            name="gmail_profile",
            description=(
                "연결된 Gmail 계정 주소와 전체 메시지·스레드 "
                "개수를 읽기 전용으로 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=client.profile,
        )
    )

    registry.register(
        ToolSpec(
            name="gmail_list_messages",
            description=(
                "Gmail 검색 문법을 사용해 메일을 읽기 전용으로 "
                "조회한다. 최근 메일, 학교 메일, 특정 발신자, "
                "읽지 않은 메일 등을 검색할 수 있다. 여러 메일을 "
                "요약할 때는 include_body=true를 사용하되 "
                "max_results를 작게 유지한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Gmail 검색식. 예: "
                            "is:unread newer_than:7d"
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "include_spam_trash": {
                        "type": "boolean",
                    },
                    "include_body": {
                        "type": "boolean",
                    },
                    "max_body_characters": {
                        "type": "integer",
                        "minimum": 500,
                        "maximum": 20000,
                    },
                },
                "required": [
                    "query",
                    "max_results",
                    "include_spam_trash",
                    "include_body",
                    "max_body_characters",
                ],
                "additionalProperties": False,
            },
            handler=lambda **kwargs: {
                **client.list_messages(**kwargs),
                "read_only": True,
            },
        )
    )

    registry.register(
        ToolSpec(
            name="gmail_get_message",
            description=(
                "메시지 ID로 특정 Gmail 메일의 헤더, 본문, "
                "라벨을 읽기 전용으로 가져온다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                    },
                    "include_body": {
                        "type": "boolean",
                    },
                    "max_body_characters": {
                        "type": "integer",
                        "minimum": 500,
                        "maximum": 50000,
                    },
                },
                "required": [
                    "message_id",
                    "include_body",
                    "max_body_characters",
                ],
                "additionalProperties": False,
            },
            handler=lambda **kwargs: {
                "message": client.get_message(
                    **kwargs
                ),
                "read_only": True,
            },
        )
    )

    registry.register(
        ToolSpec(
            name="gmail_unread_count",
            description=(
                "읽지 않은 Gmail 메일 개수를 추정한다. "
                "선택적으로 추가 Gmail 검색 조건을 적용할 수 있다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=lambda query: {
                **client.unread_count(
                    query=query
                ),
                "read_only": True,
            },
        )
    )

    registry.register(
        ToolSpec(
            name="gmail_list_labels",
            description=(
                "Gmail 라벨 목록과 ID를 읽기 전용으로 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda: {
                "labels": list(
                    client.list_labels()
                ),
                "read_only": True,
            },
        )
    )
