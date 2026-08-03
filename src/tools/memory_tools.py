from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, Callable

from src.memory import LocalMemoryStore

from .registry import ToolRegistry, ToolSpec


OpenUrlHandler = Callable[[str], dict[str, Any]]

_STRUCTURED_KINDS = [
    "project",
    "decision",
    "todo",
    "relation",
    "summary",
]
_ALL_STATUSES = [
    "active",
    "pending",
    "in_progress",
    "completed",
    "cancelled",
    "superseded",
    "archived",
]


def _open_path(value: str) -> dict[str, Any]:
    if sys.platform != "win32":
        raise RuntimeError(
            "Saved path aliases can currently be opened on Windows only."
        )
    path = Path(value).expanduser()
    if not path.exists():
        raise RuntimeError(f"The saved path does not exist: {path}")
    os.startfile(str(path.resolve()))  # type: ignore[attr-defined]
    return {
        "opened": True,
        "path": str(path.resolve()),
        "message": "Saved path was opened.",
    }


def register_memory_tools(
    registry: ToolRegistry,
    store: LocalMemoryStore,
    *,
    open_url: OpenUrlHandler,
) -> None:
    def remember_alias(
        alias: str,
        target: str,
        target_type: str,
    ) -> dict[str, Any]:
        record = store.remember_alias(alias, target, target_type)
        return {
            "stored": True,
            "memory": record.as_dict(),
            "message": f"별칭 '{record.name}'을 기억했습니다.",
        }

    def remember_preference(name: str, value: str) -> dict[str, Any]:
        record = store.remember_preference(name, value)
        return {
            "stored": True,
            "memory": record.as_dict(),
            "message": f"선호 설정 '{record.name}'을 기억했습니다.",
        }

    def remember_memory_item(
        kind: str,
        scope: str,
        name: str,
        value: str,
        notes: str,
        status: str,
        importance: int,
        confidence: float,
        replace_existing: bool,
    ) -> dict[str, Any]:
        result = store.remember_item(
            kind=kind,
            scope=scope,
            name=name,
            value=value,
            notes=notes,
            status=status,
            importance=importance,
            confidence=confidence,
            replace_existing=replace_existing,
        )
        payload = {
            "stored": result.stored,
            "unchanged": result.unchanged,
            "memory": (
                store.public_structured_record(result.record)
                if result.record is not None
                else None
            ),
            "conflict": (
                result.conflict.as_dict()
                if result.conflict is not None
                else None
            ),
        }
        if result.conflict is not None:
            payload["message"] = (
                "기존 기억과 충돌해 새 값을 저장하지 않았습니다. "
                "사용자의 최신 의도를 확인한 뒤 충돌을 해결하세요."
            )
        elif result.unchanged:
            payload["message"] = "같은 내용이 이미 저장되어 있습니다."
        else:
            payload["message"] = "구조화된 장기 기억을 저장했습니다."
        return payload

    def search_saved_memory(
        query: str,
        scope: str,
        kind: str,
        status: str,
        limit: int,
    ) -> dict[str, Any]:
        items = store.search_items(
            query=query,
            scope=scope,
            kind=kind,
            status=status,
            limit=limit,
        )
        return {
            "query": query,
            "scope": scope,
            "kind": kind,
            "status": status,
            "count": len(items),
            "memories": list(items),
        }

    def get_project_memory(
        scope: str,
        include_completed: bool,
        limit: int,
    ) -> dict[str, Any]:
        return store.project_snapshot(
            scope=scope,
            include_completed=include_completed,
            limit=limit,
        )

    def set_saved_memory_status(
        kind: str,
        scope: str,
        name: str,
        status: str,
    ) -> dict[str, Any]:
        record = store.set_item_status(
            kind=kind,
            scope=scope,
            name=name,
            status=status,
        )
        return {
            "updated": True,
            "memory": store.public_structured_record(record),
            "message": f"기억 상태를 {record.status}(으)로 변경했습니다.",
        }

    def list_memory_conflicts(
        scope: str,
        status: str,
        limit: int,
    ) -> dict[str, Any]:
        conflicts = store.list_conflicts(
            scope=scope,
            status=status,
            limit=limit,
        )
        return {
            "scope": scope,
            "status": status,
            "count": len(conflicts),
            "conflicts": [item.as_dict() for item in conflicts],
        }

    def resolve_memory_conflict(
        conflict_id: int,
        resolution: str,
        merged_value: str,
        merged_notes: str,
        merged_status: str,
        merged_importance: int,
        merged_confidence: float,
    ) -> dict[str, Any]:
        return store.resolve_conflict(
            conflict_id=conflict_id,
            resolution=resolution,
            merged_value=merged_value,
            merged_notes=merged_notes,
            merged_status=merged_status,
            merged_importance=merged_importance,
            merged_confidence=merged_confidence,
        )

    def review_memory_health(scope: str, limit: int) -> dict[str, Any]:
        return store.memory_health(scope=scope, limit=limit)

    def get_memory_history(
        kind: str,
        scope: str,
        name: str,
        limit: int,
    ) -> dict[str, Any]:
        history = store.history(
            kind=kind,
            scope=scope,
            name=name,
            limit=limit,
        )
        return {
            "kind": kind,
            "scope": scope,
            "name": name,
            "count": len(history),
            "history": list(history),
        }

    def list_saved_memories(kind: str, limit: int) -> dict[str, Any]:
        records = store.list_memories(kind, limit)
        return {
            "kind": kind,
            "count": len(records),
            "memories": [record.as_dict() for record in records],
        }

    def resolve_saved_alias(alias: str) -> dict[str, Any]:
        record = store.resolve_alias(alias)
        if record is None:
            raise ValueError(f"저장된 별칭을 찾지 못했습니다: {alias}")
        return {"found": True, "memory": record.as_dict()}

    def open_saved_alias(alias: str) -> dict[str, Any]:
        record = store.resolve_alias(alias)
        if record is None:
            raise ValueError(f"저장된 별칭을 찾지 못했습니다: {alias}")
        if record.value_type == "url":
            result = open_url(record.value)
            return {
                "opened": True,
                "alias": record.name,
                "target_type": "url",
                "target": record.value,
                **result,
            }
        if record.value_type == "path":
            result = _open_path(record.value)
            return {
                "alias": record.name,
                "target_type": "path",
                "target": record.value,
                **result,
            }
        raise ValueError(
            f"별칭 '{record.name}'은 텍스트 메모라서 열 수 없습니다. "
            "resolve_saved_alias로 내용을 조회하세요."
        )

    def forget_saved_memory(kind: str, name: str) -> dict[str, Any]:
        deleted = store.forget(kind, name)
        return {
            "deleted": deleted,
            "kind": kind,
            "name": name,
            "message": (
                "저장된 메모리를 삭제했습니다."
                if deleted
                else "일치하는 저장 메모리가 없습니다."
            ),
        }

    registry.register(
        ToolSpec(
            name="remember_alias",
            description=(
                "사용자가 기억하라고 명시적으로 요청한 경우에만 URL, 경로 "
                "또는 짧은 텍스트 별칭을 저장한다. 추측해서 자동 저장하지 않는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "maxLength": 80},
                    "target": {"type": "string", "maxLength": 2048},
                    "target_type": {
                        "type": "string",
                        "enum": ["auto", "url", "path", "text"],
                    },
                },
                "required": ["alias", "target", "target_type"],
                "additionalProperties": False,
            },
            handler=remember_alias,
        )
    )
    registry.register(
        ToolSpec(
            name="remember_preference",
            description=(
                "사용자가 앞으로의 기본 선호를 명시적으로 기억해 달라고 한 "
                "경우에만 비민감 선호를 저장한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 80},
                    "value": {"type": "string", "maxLength": 2048},
                },
                "required": ["name", "value"],
                "additionalProperties": False,
            },
            handler=remember_preference,
        )
    )
    registry.register(
        ToolSpec(
            name="remember_memory_item",
            description=(
                "사용자가 명시적으로 기억·저장·갱신하라고 한 프로젝트 상태, "
                "결정, TODO, 관계 또는 요약을 구조화해 저장한다. "
                "replace_existing=false에서 기존 값과 다르면 덮어쓰지 않고 "
                "conflict를 반환한다. 사용자가 최신 값으로 교체한다고 명확히 "
                "말한 경우에만 replace_existing=true를 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": _STRUCTURED_KINDS},
                    "scope": {"type": "string", "maxLength": 120},
                    "name": {"type": "string", "maxLength": 160},
                    "value": {"type": "string", "maxLength": 2048},
                    "notes": {"type": "string", "maxLength": 4096},
                    "status": {"type": "string", "enum": _ALL_STATUSES},
                    "importance": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "replace_existing": {"type": "boolean"},
                },
                "required": [
                    "kind",
                    "scope",
                    "name",
                    "value",
                    "notes",
                    "status",
                    "importance",
                    "confidence",
                    "replace_existing",
                ],
                "additionalProperties": False,
            },
            handler=remember_memory_item,
        )
    )
    registry.register(
        ToolSpec(
            name="search_saved_memory",
            description=(
                "현재 질문과 관련된 프로젝트·결정·TODO·관계·요약을 범위, "
                "종류, 상태와 관련도 점수로 검색한다. query가 없으면 빈 문자열, "
                "전체 범위·종류·상태는 all을 전달한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                    "scope": {"type": "string", "maxLength": 120},
                    "kind": {
                        "type": "string",
                        "enum": ["all", *_STRUCTURED_KINDS],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["all", "current", *_ALL_STATUSES],
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["query", "scope", "kind", "status", "limit"],
                "additionalProperties": False,
            },
            handler=search_saved_memory,
        )
    )
    registry.register(
        ToolSpec(
            name="get_project_memory",
            description=(
                "특정 프로젝트나 작업 범위의 현재 상태, 결정, TODO, 관계, "
                "요약과 충돌 수를 한 번에 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "maxLength": 120},
                    "include_completed": {"type": "boolean"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["scope", "include_completed", "limit"],
                "additionalProperties": False,
            },
            handler=get_project_memory,
        )
    )
    registry.register(
        ToolSpec(
            name="set_saved_memory_status",
            description=(
                "사용자가 TODO 완료·진행·취소, 프로젝트 완료, 결정 폐기, "
                "기억 보관을 명시적으로 요청할 때 상태만 변경하고 이력을 남긴다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": _STRUCTURED_KINDS},
                    "scope": {"type": "string", "maxLength": 120},
                    "name": {"type": "string", "maxLength": 160},
                    "status": {"type": "string", "enum": _ALL_STATUSES},
                },
                "required": ["kind", "scope", "name", "status"],
                "additionalProperties": False,
            },
            handler=set_saved_memory_status,
        )
    )
    registry.register(
        ToolSpec(
            name="list_memory_conflicts",
            description=(
                "기존 구조화 기억과 새 후보가 충돌해 저장되지 않은 항목을 "
                "조회한다. 전체 범위는 scope=all을 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "maxLength": 120},
                    "status": {
                        "type": "string",
                        "enum": ["all", "pending", "resolved", "ignored"],
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["scope", "status", "limit"],
                "additionalProperties": False,
            },
            handler=list_memory_conflicts,
        )
    )
    registry.register(
        ToolSpec(
            name="resolve_memory_conflict",
            description=(
                "사용자가 충돌한 기억 중 어느 값이 최신인지 명확히 결정한 "
                "경우에만 해결한다. keep_existing은 기존 값 유지, "
                "use_candidate는 새 후보 채택, merge는 확정한 병합 값을 저장한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "conflict_id": {"type": "integer", "minimum": 1},
                    "resolution": {
                        "type": "string",
                        "enum": ["keep_existing", "use_candidate", "merge"],
                    },
                    "merged_value": {"type": "string", "maxLength": 2048},
                    "merged_notes": {"type": "string", "maxLength": 4096},
                    "merged_status": {
                        "type": "string",
                        "enum": _ALL_STATUSES,
                    },
                    "merged_importance": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "merged_confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
                "required": [
                    "conflict_id",
                    "resolution",
                    "merged_value",
                    "merged_notes",
                    "merged_status",
                    "merged_importance",
                    "merged_confidence",
                ],
                "additionalProperties": False,
            },
            handler=resolve_memory_conflict,
        )
    )
    registry.register(
        ToolSpec(
            name="review_memory_health",
            description=(
                "특정 범위 또는 전체 기억에서 오래된 현재 항목, 완료된 TODO, "
                "미해결 충돌을 검토한다. 자동 삭제하거나 자동 갱신하지 않는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "maxLength": 120},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["scope", "limit"],
                "additionalProperties": False,
            },
            handler=review_memory_health,
        )
    )
    registry.register(
        ToolSpec(
            name="get_memory_history",
            description=(
                "특정 구조화 기억이 언제 어떤 값에서 어떤 값으로 변경됐는지 "
                "감사 이력을 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": _STRUCTURED_KINDS},
                    "scope": {"type": "string", "maxLength": 120},
                    "name": {"type": "string", "maxLength": 160},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["kind", "scope", "name", "limit"],
                "additionalProperties": False,
            },
            handler=get_memory_history,
        )
    )
    registry.register(
        ToolSpec(
            name="list_saved_memories",
            description=(
                "기존 URL·경로 별칭과 단순 선호 목록을 조회한다. 구조화 "
                "기억은 search_saved_memory를 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "alias", "preference"],
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["kind", "limit"],
                "additionalProperties": False,
            },
            handler=list_saved_memories,
        )
    )
    registry.register(
        ToolSpec(
            name="resolve_saved_alias",
            description="저장된 별칭의 대상과 종류를 조회한다.",
            parameters={
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "maxLength": 80},
                },
                "required": ["alias"],
                "additionalProperties": False,
            },
            handler=resolve_saved_alias,
        )
    )
    registry.register(
        ToolSpec(
            name="open_saved_alias",
            description=(
                "사용자가 저장된 URL 또는 경로 별칭을 열어 달라고 "
                "명시적으로 요청했을 때만 연다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "maxLength": 80},
                },
                "required": ["alias"],
                "additionalProperties": False,
            },
            handler=open_saved_alias,
        )
    )
    registry.register(
        ToolSpec(
            name="forget_saved_memory",
            description=(
                "사용자가 특정 기존 별칭 또는 선호를 잊으라고 명시적으로 "
                "요청할 때만 영구 삭제한다. 구조화 기억은 archived 상태를 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["alias", "preference"],
                    },
                    "name": {"type": "string", "maxLength": 80},
                },
                "required": ["kind", "name"],
                "additionalProperties": False,
            },
            handler=forget_saved_memory,
        )
    )
