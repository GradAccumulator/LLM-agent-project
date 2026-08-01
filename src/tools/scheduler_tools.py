from __future__ import annotations

from typing import Any

from src.scheduler import SchedulerStore
from .registry import ToolRegistry, ToolSpec


def register_scheduler_tools(registry: ToolRegistry, store: SchedulerStore) -> None:
    def schedule_relative_reminder(message: str, delay_seconds: float) -> dict[str, Any]:
        task = store.schedule_after(message=message, delay_seconds=delay_seconds)
        return {
            'scheduled': True,
            'task': task.as_dict(),
            'message': f'알림 {task.id}번을 {task.next_run_local}에 예약했습니다.',
        }

    def schedule_reminder(message: str, run_at: str) -> dict[str, Any]:
        task = store.schedule_at(message=message, run_at=run_at)
        return {'scheduled': True, 'task': task.as_dict(), 'message': f'알림 {task.id}번을 예약했습니다.'}

    def schedule_recurring_reminder(
        message: str,
        first_run_at: str,
        recurrence: str,
        interval: int,
    ) -> dict[str, Any]:
        task = store.schedule_at(
            message=message,
            run_at=first_run_at,
            recurrence=recurrence,
            interval=interval,
        )
        return {'scheduled': True, 'task': task.as_dict(), 'message': f'반복 알림 {task.id}번을 예약했습니다.'}

    def list_scheduled_reminders(status: str, limit: int) -> dict[str, Any]:
        tasks = store.list_tasks(status=status, limit=limit)
        return {'status_filter': status, 'count': len(tasks), 'tasks': [task.as_dict() for task in tasks]}

    def cancel_scheduled_reminder(task_id: int) -> dict[str, Any]:
        task = store.cancel(task_id)
        return {'cancelled': True, 'task': task.as_dict(), 'message': f'알림 {task.id}번을 취소했습니다.'}

    def snooze_scheduled_reminder(task_id: int, delay_minutes: float) -> dict[str, Any]:
        task = store.snooze(task_id=task_id, delay_minutes=delay_minutes)
        return {'snoozed': True, 'task': task.as_dict(), 'message': f'알림 {task.id}번을 {delay_minutes:g}분 미뤘습니다.'}

    registry.register(ToolSpec(
        name='schedule_relative_reminder',
        description='몇 초·몇 분·몇 시간 뒤의 일회성 알림을 예약한다.',
        parameters={
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'maxLength': 500},
                'delay_seconds': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 31622400},
            },
            'required': ['message', 'delay_seconds'],
            'additionalProperties': False,
        },
        handler=schedule_relative_reminder,
    ))
    registry.register(ToolSpec(
        name='schedule_reminder',
        description='특정 날짜와 시각의 일회성 알림을 예약한다. run_at은 시간대가 포함된 ISO 8601이다.',
        parameters={
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'maxLength': 500},
                'run_at': {'type': 'string'},
            },
            'required': ['message', 'run_at'],
            'additionalProperties': False,
        },
        handler=schedule_reminder,
    ))
    registry.register(ToolSpec(
        name='schedule_recurring_reminder',
        description='매일 또는 매주 반복되는 알림을 예약한다.',
        parameters={
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'maxLength': 500},
                'first_run_at': {'type': 'string'},
                'recurrence': {'type': 'string', 'enum': ['daily', 'weekly']},
                'interval': {'type': 'integer', 'minimum': 1, 'maximum': 365},
            },
            'required': ['message', 'first_run_at', 'recurrence', 'interval'],
            'additionalProperties': False,
        },
        handler=schedule_recurring_reminder,
    ))
    registry.register(ToolSpec(
        name='list_scheduled_reminders',
        description='저장된 알림 목록과 다음 실행 시각을 조회한다.',
        parameters={
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['active', 'completed', 'cancelled', 'all']},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 500},
            },
            'required': ['status', 'limit'],
            'additionalProperties': False,
        },
        handler=list_scheduled_reminders,
    ))
    registry.register(ToolSpec(
        name='cancel_scheduled_reminder',
        description='번호를 지정해 활성 알림을 취소한다.',
        parameters={
            'type': 'object',
            'properties': {'task_id': {'type': 'integer', 'minimum': 1}},
            'required': ['task_id'],
            'additionalProperties': False,
        },
        handler=cancel_scheduled_reminder,
    ))
    registry.register(ToolSpec(
        name='snooze_scheduled_reminder',
        description='기존 알림을 지정한 분만큼 미룬다.',
        parameters={
            'type': 'object',
            'properties': {
                'task_id': {'type': 'integer', 'minimum': 1},
                'delay_minutes': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 525600},
            },
            'required': ['task_id', 'delay_minutes'],
            'additionalProperties': False,
        },
        handler=snooze_scheduled_reminder,
    ))
