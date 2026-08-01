from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, Callable

from src.memory import LocalMemoryStore

from .registry import ToolRegistry, ToolSpec


OpenUrlHandler = Callable[[str], dict[str, Any]]


def _open_path(value: str) -> dict[str, Any]:
    if sys.platform != 'win32':
        raise RuntimeError(
            'Saved path aliases can currently be opened on Windows only.'
        )
    path = Path(value).expanduser()
    if not path.exists():
        raise RuntimeError(
            f'The saved path does not exist: {path}'
        )
    os.startfile(str(path.resolve()))  # type: ignore[attr-defined]
    return {
        'opened': True,
        'path': str(path.resolve()),
        'message': 'Saved path was opened.',
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
        record = store.remember_alias(
            alias,
            target,
            target_type,
        )
        return {
            'stored': True,
            'memory': record.as_dict(),
            'message': f"별칭 '{record.name}'을 기억했습니다.",
        }

    def remember_preference(
        name: str,
        value: str,
    ) -> dict[str, Any]:
        record = store.remember_preference(
            name,
            value,
        )
        return {
            'stored': True,
            'memory': record.as_dict(),
            'message': f"선호 설정 '{record.name}'을 기억했습니다.",
        }

    def list_saved_memories(
        kind: str,
        limit: int,
    ) -> dict[str, Any]:
        records = store.list_memories(
            kind,
            limit,
        )
        return {
            'kind': kind,
            'count': len(records),
            'memories': [
                record.as_dict()
                for record in records
            ],
        }

    def resolve_saved_alias(alias: str) -> dict[str, Any]:
        record = store.resolve_alias(alias)
        if record is None:
            raise ValueError(
                f"저장된 별칭을 찾지 못했습니다: {alias}"
            )
        return {
            'found': True,
            'memory': record.as_dict(),
        }

    def open_saved_alias(alias: str) -> dict[str, Any]:
        record = store.resolve_alias(alias)
        if record is None:
            raise ValueError(
                f"저장된 별칭을 찾지 못했습니다: {alias}"
            )

        if record.value_type == 'url':
            result = open_url(record.value)
            return {
                'opened': True,
                'alias': record.name,
                'target_type': 'url',
                'target': record.value,
                **result,
            }
        if record.value_type == 'path':
            result = _open_path(record.value)
            return {
                'alias': record.name,
                'target_type': 'path',
                'target': record.value,
                **result,
            }

        raise ValueError(
            f"별칭 '{record.name}'은 텍스트 메모라서 열 수 없습니다. "
            'resolve_saved_alias로 내용을 조회하세요.'
        )

    def forget_saved_memory(
        kind: str,
        name: str,
    ) -> dict[str, Any]:
        deleted = store.forget(kind, name)
        return {
            'deleted': deleted,
            'kind': kind,
            'name': name,
            'message': (
                '저장된 메모리를 삭제했습니다.'
                if deleted
                else '일치하는 저장 메모리가 없습니다.'
            ),
        }

    registry.register(
        ToolSpec(
            name='remember_alias',
            description=(
                "사용자가 '기억해', '별칭으로 저장해'처럼 명시적으로 "
                '요청한 경우에만 URL, 폴더·파일 경로 또는 짧은 텍스트에 '
                '사용자 별칭을 저장한다. 추측해서 자동 저장하지 않는다.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'alias': {
                        'type': 'string',
                        'maxLength': 80,
                    },
                    'target': {
                        'type': 'string',
                        'maxLength': 2048,
                    },
                    'target_type': {
                        'type': 'string',
                        'enum': ['auto', 'url', 'path', 'text'],
                    },
                },
                'required': [
                    'alias',
                    'target',
                    'target_type',
                ],
                'additionalProperties': False,
            },
            handler=remember_alias,
        )
    )
    registry.register(
        ToolSpec(
            name='remember_preference',
            description=(
                "사용자가 '앞으로', '기억해', '기본으로 써'라고 "
                '명시적으로 요청한 비민감 선호만 저장한다. search_engine '
                '키에는 google, naver, youtube 중 하나를 저장할 수 있다.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'name': {
                        'type': 'string',
                        'maxLength': 80,
                    },
                    'value': {
                        'type': 'string',
                        'maxLength': 2048,
                    },
                },
                'required': ['name', 'value'],
                'additionalProperties': False,
            },
            handler=remember_preference,
        )
    )
    registry.register(
        ToolSpec(
            name='list_saved_memories',
            description=(
                '사용자가 저장된 별칭이나 선호를 보여 달라고 요청할 때 '
                '로컬 장기 메모리 목록을 조회한다.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'kind': {
                        'type': 'string',
                        'enum': ['all', 'alias', 'preference'],
                    },
                    'limit': {
                        'type': 'integer',
                        'minimum': 1,
                        'maximum': 100,
                    },
                },
                'required': ['kind', 'limit'],
                'additionalProperties': False,
            },
            handler=list_saved_memories,
        )
    )
    registry.register(
        ToolSpec(
            name='resolve_saved_alias',
            description=(
                '저장된 별칭의 대상과 종류를 조회한다. 별칭 내용을 '
                '확인해야 할 때 사용한다.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'alias': {'type': 'string', 'maxLength': 80},
                },
                'required': ['alias'],
                'additionalProperties': False,
            },
            handler=resolve_saved_alias,
        )
    )
    registry.register(
        ToolSpec(
            name='open_saved_alias',
            description=(
                '사용자가 저장된 URL 또는 경로 별칭을 열어 달라고 '
                '명시적으로 요청했을 때 해당 대상을 연다.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'alias': {'type': 'string', 'maxLength': 80},
                },
                'required': ['alias'],
                'additionalProperties': False,
            },
            handler=open_saved_alias,
        )
    )
    registry.register(
        ToolSpec(
            name='forget_saved_memory',
            description=(
                '사용자가 특정 별칭 또는 선호를 잊거나 삭제하라고 '
                '명시적으로 요청할 때만 해당 로컬 메모리를 삭제한다.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'kind': {
                        'type': 'string',
                        'enum': ['alias', 'preference'],
                    },
                    'name': {'type': 'string', 'maxLength': 80},
                },
                'required': ['kind', 'name'],
                'additionalProperties': False,
            },
            handler=forget_saved_memory,
        )
    )
