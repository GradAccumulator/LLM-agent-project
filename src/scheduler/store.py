from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any


class SchedulerError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SchedulerStoreConfig:
    enabled: bool = True
    database: Path = Path('data/jarvis_tasks.db')
    max_tasks: int = 200
    max_message_characters: int = 500

    def __post_init__(self) -> None:
        if self.max_tasks <= 0:
            raise ValueError('max_tasks must be positive.')
        if self.max_message_characters <= 0:
            raise ValueError('max_message_characters must be positive.')


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    id: int
    message: str
    next_run_at: str
    recurrence: str
    interval: int
    status: str
    created_at: str
    updated_at: str
    last_run_at: str | None

    @property
    def next_run_datetime(self) -> datetime:
        return parse_datetime(self.next_run_at)

    @property
    def next_run_local(self) -> str:
        return self.next_run_datetime.astimezone().isoformat(timespec='seconds')

    def as_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'message': self.message,
            'next_run_at': self.next_run_at,
            'next_run_local': self.next_run_local,
            'recurrence': self.recurrence,
            'interval': self.interval,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_run_at': self.last_run_at,
        }


@dataclass(frozen=True, slots=True)
class DueReminder:
    task: ScheduledTask
    due_at: str
    claimed_at: str
    late_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            'task': self.task.as_dict(),
            'due_at': self.due_at,
            'claimed_at': self.claimed_at,
            'late_seconds': self.late_seconds,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        raise SchedulerError('Date and time must not be empty.')
    if cleaned.endswith('Z'):
        cleaned = cleaned[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise SchedulerError(
            'Use ISO 8601, for example 2026-08-02T15:00:00+09:00.'
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(timezone.utc)


class SchedulerStore:
    def __init__(self, config: SchedulerStoreConfig) -> None:
        self.config = config
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._closed = False
        if not config.enabled:
            return

        path = config.database.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(
                path,
                timeout=5.0,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:
            raise RuntimeError(f'Could not open scheduler database {path}: {exc}') from exc
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout = 5000')
        try:
            connection.execute('PRAGMA journal_mode = WAL')
        except sqlite3.DatabaseError:
            pass
        self._connection = connection
        self._initialize_schema()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def _conn(self) -> sqlite3.Connection:
        if not self.config.enabled:
            raise RuntimeError('Reminder scheduler is disabled.')
        if self._closed or self._connection is None:
            raise RuntimeError('Scheduler store is closed.')
        return self._connection

    def _initialize_schema(self) -> None:
        connection = self._conn()
        with self._lock, connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    next_run_at TEXT NOT NULL,
                    recurrence TEXT NOT NULL CHECK (
                        recurrence IN ('once', 'daily', 'weekly')
                    ),
                    interval_value INTEGER NOT NULL CHECK (interval_value > 0),
                    status TEXT NOT NULL CHECK (
                        status IN ('active', 'completed', 'cancelled')
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_scheduled_due
                ON scheduled_tasks(status, next_run_at, id);
            ''')

    def _message(self, value: str) -> str:
        cleaned = ' '.join(value.strip().split())
        if not cleaned:
            raise SchedulerError('Reminder message must not be empty.')
        if len(cleaned) > self.config.max_message_characters:
            raise SchedulerError('Reminder message exceeds the character limit.')
        return cleaned

    @staticmethod
    def _recurrence(value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {'once', 'daily', 'weekly'}:
            raise SchedulerError('recurrence must be once, daily, or weekly.')
        return normalized

    @staticmethod
    def _row(row: sqlite3.Row) -> ScheduledTask:
        return ScheduledTask(
            id=int(row['id']),
            message=str(row['message']),
            next_run_at=str(row['next_run_at']),
            recurrence=str(row['recurrence']),
            interval=int(row['interval_value']),
            status=str(row['status']),
            created_at=str(row['created_at']),
            updated_at=str(row['updated_at']),
            last_run_at=(str(row['last_run_at']) if row['last_run_at'] is not None else None),
        )

    def count_active(self) -> int:
        if not self.enabled:
            return 0
        with self._lock:
            row = self._conn().execute(
                "SELECT COUNT(*) FROM scheduled_tasks WHERE status = 'active'"
            ).fetchone()
        return int(row[0])

    def schedule_at(
        self,
        *,
        message: str,
        run_at: str,
        recurrence: str = 'once',
        interval: int = 1,
    ) -> ScheduledTask:
        message = self._message(message)
        recurrence = self._recurrence(recurrence)
        if interval <= 0:
            raise SchedulerError('interval must be positive.')
        run_datetime = parse_datetime(run_at)
        now = utc_now()
        if run_datetime <= now:
            raise SchedulerError('The reminder time must be in the future.')
        connection = self._conn()
        timestamp = utc_iso(now)
        with self._lock, connection:
            if self.count_active() >= self.config.max_tasks:
                raise SchedulerError('The active reminder limit was reached.')
            cursor = connection.execute(
                '''INSERT INTO scheduled_tasks (
                    message, next_run_at, recurrence, interval_value,
                    status, created_at, updated_at, last_run_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, NULL)''',
                (message, utc_iso(run_datetime), recurrence, interval, timestamp, timestamp),
            )
            row = connection.execute(
                'SELECT * FROM scheduled_tasks WHERE id = ?',
                (cursor.lastrowid,),
            ).fetchone()
        if row is None:
            raise RuntimeError('Could not read the scheduled reminder back.')
        return self._row(row)

    def schedule_after(self, *, message: str, delay_seconds: float) -> ScheduledTask:
        if delay_seconds <= 0:
            raise SchedulerError('delay_seconds must be positive.')
        if delay_seconds > 366 * 24 * 3600:
            raise SchedulerError('Relative reminders cannot exceed 366 days.')
        return self.schedule_at(
            message=message,
            run_at=utc_iso(utc_now() + timedelta(seconds=float(delay_seconds))),
        )

    def get(self, task_id: int) -> ScheduledTask | None:
        if task_id <= 0:
            raise SchedulerError('task_id must be positive.')
        if not self.enabled:
            return None
        with self._lock:
            row = self._conn().execute(
                'SELECT * FROM scheduled_tasks WHERE id = ?',
                (task_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def list_tasks(self, *, status: str = 'active', limit: int = 100) -> tuple[ScheduledTask, ...]:
        if not self.enabled:
            return ()
        normalized = status.strip().casefold()
        if normalized not in {'active', 'completed', 'cancelled', 'all'}:
            raise SchedulerError('Invalid reminder status filter.')
        if not 1 <= limit <= 500:
            raise SchedulerError('limit must be between 1 and 500.')
        connection = self._conn()
        if normalized == 'all':
            query = 'SELECT * FROM scheduled_tasks ORDER BY next_run_at, id LIMIT ?'
            params: tuple[Any, ...] = (limit,)
        else:
            query = 'SELECT * FROM scheduled_tasks WHERE status = ? ORDER BY next_run_at, id LIMIT ?'
            params = (normalized, limit)
        with self._lock:
            rows = connection.execute(query, params).fetchall()
        return tuple(self._row(row) for row in rows)

    def cancel(self, task_id: int) -> ScheduledTask:
        task = self.get(task_id)
        if task is None:
            raise SchedulerError(f'Reminder does not exist: {task_id}')
        if task.status != 'active':
            raise SchedulerError('Only active reminders can be cancelled.')
        now = utc_iso(utc_now())
        connection = self._conn()
        with self._lock, connection:
            connection.execute(
                "UPDATE scheduled_tasks SET status='cancelled', updated_at=? WHERE id=?",
                (now, task_id),
            )
            row = connection.execute(
                'SELECT * FROM scheduled_tasks WHERE id=?',
                (task_id,),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def snooze(self, *, task_id: int, delay_minutes: float) -> ScheduledTask:
        if delay_minutes <= 0:
            raise SchedulerError('delay_minutes must be positive.')
        if self.get(task_id) is None:
            raise SchedulerError(f'Reminder does not exist: {task_id}')
        now = utc_now()
        connection = self._conn()
        with self._lock, connection:
            connection.execute(
                '''UPDATE scheduled_tasks
                   SET next_run_at=?, status='active', updated_at=?
                   WHERE id=?''',
                (
                    utc_iso(now + timedelta(minutes=float(delay_minutes))),
                    utc_iso(now),
                    task_id,
                ),
            )
            row = connection.execute(
                'SELECT * FROM scheduled_tasks WHERE id=?',
                (task_id,),
            ).fetchone()
        assert row is not None
        return self._row(row)

    @staticmethod
    def _next_time(task: ScheduledTask, now: datetime) -> datetime:
        current = task.next_run_datetime
        if task.recurrence == 'daily':
            delta = timedelta(days=task.interval)
        elif task.recurrence == 'weekly':
            delta = timedelta(weeks=task.interval)
        else:
            raise SchedulerError('One-time reminder has no recurrence.')
        while current <= now:
            current += delta
        return current

    def claim_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
    ) -> tuple[DueReminder, ...]:
        if not self.enabled:
            return ()
        if not 1 <= limit <= 100:
            raise SchedulerError('limit must be between 1 and 100.')
        current = (now or utc_now()).astimezone(timezone.utc)
        current_iso = utc_iso(current)
        connection = self._conn()
        with self._lock:
            connection.execute('BEGIN IMMEDIATE')
            try:
                rows = connection.execute(
                    '''SELECT * FROM scheduled_tasks
                       WHERE status='active' AND next_run_at <= ?
                       ORDER BY next_run_at, id LIMIT ?''',
                    (current_iso, limit),
                ).fetchall()
                due: list[DueReminder] = []
                for row in rows:
                    task = self._row(row)
                    due.append(
                        DueReminder(
                            task=task,
                            due_at=task.next_run_at,
                            claimed_at=current_iso,
                            late_seconds=max(
                                0.0,
                                (current - task.next_run_datetime).total_seconds(),
                            ),
                        )
                    )
                    if task.recurrence == 'once':
                        connection.execute(
                            '''UPDATE scheduled_tasks
                               SET status='completed', last_run_at=?, updated_at=?
                               WHERE id=?''',
                            (current_iso, current_iso, task.id),
                        )
                    else:
                        connection.execute(
                            '''UPDATE scheduled_tasks
                               SET next_run_at=?, last_run_at=?, updated_at=?
                               WHERE id=?''',
                            (
                                utc_iso(self._next_time(task, current)),
                                current_iso,
                                current_iso,
                                task.id,
                            ),
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return tuple(due)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> 'SchedulerStore':
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
