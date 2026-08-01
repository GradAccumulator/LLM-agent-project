from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Literal
from urllib.parse import urlparse


MemoryKind = Literal['alias', 'preference']
AliasTargetType = Literal['url', 'path', 'text']

_KINDS = {'alias', 'preference'}
_TARGET_TYPES = {'url', 'path', 'text'}

_SENSITIVE_WORDS = (
    'password',
    'passcode',
    '비밀번호',
    'api key',
    'apikey',
    'api키',
    'access token',
    'refresh token',
    '토큰',
    'otp',
    '인증번호',
    'recovery code',
    '복구코드',
    '카드번호',
    'cvv',
    'cvc',
    '계좌번호',
    '주민번호',
    '주민등록번호',
    'private key',
    '개인키',
)

_SECRET_PATTERNS = (
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b'),
    re.compile(r'\bAIza[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    re.compile(r'\b\d{6}\b'),
)

_SENSITIVE_FILENAMES = {
    '.env',
    'credentials.json',
    'service-account.json',
    'id_rsa',
    'id_ed25519',
    'private_key.pem',
}


class MemoryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryStoreConfig:
    enabled: bool = True
    database: Path = Path('data/jarvis_memory.db')
    context_limit: int = 20
    max_context_characters: int = 4_000
    max_entries: int = 200
    max_value_characters: int = 2_048

    def __post_init__(self) -> None:
        if self.context_limit <= 0:
            raise ValueError('context_limit must be positive.')
        if self.max_context_characters <= 0:
            raise ValueError(
                'max_context_characters must be positive.'
            )
        if self.max_entries <= 0:
            raise ValueError('max_entries must be positive.')
        if self.max_value_characters <= 0:
            raise ValueError(
                'max_value_characters must be positive.'
            )


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: int
    kind: MemoryKind
    name: str
    normalized_name: str
    value: str
    value_type: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'kind': self.kind,
            'name': self.name,
            'value': self.value,
            'value_type': self.value_type,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


def normalize_memory_name(value: str) -> str:
    return re.sub(
        r'[\W_]+',
        '',
        value,
        flags=re.UNICODE,
    ).casefold()


def infer_alias_target_type(value: str) -> AliasTargetType:
    stripped = value.strip()
    parsed = urlparse(stripped)
    if parsed.scheme.casefold() in {'http', 'https'} and parsed.netloc:
        return 'url'
    if (
        re.match(r'^[A-Za-z]:[\\/]', stripped)
        or stripped.startswith('\\\\')
        or stripped.startswith('/')
        or stripped.startswith('~/')
        or stripped.startswith('~\\')
    ):
        return 'path'
    return 'text'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec='seconds'
    )


class LocalMemoryStore:
    def __init__(self, config: MemoryStoreConfig) -> None:
        self.config = config
        self._lock = RLock()
        self._closed = False
        self._connection: sqlite3.Connection | None = None

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
            raise RuntimeError(
                f'Could not open memory database {path}: {exc}'
            ) from exc

        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
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

    @property
    def database_path(self) -> Path:
        return self.config.database.expanduser()

    def _require_connection(self) -> sqlite3.Connection:
        if not self.config.enabled:
            raise RuntimeError('Long-term memory is disabled.')
        if self._closed or self._connection is None:
            raise RuntimeError('Memory store is closed.')
        return self._connection

    def _initialize_schema(self) -> None:
        connection = self._require_connection()
        with self._lock, connection:
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (
                        kind IN ('alias', 'preference')
                    ),
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(kind, normalized_name)
                );
                CREATE INDEX IF NOT EXISTS idx_memories_updated
                ON memories(updated_at DESC, id DESC);
                '''
            )

    @staticmethod
    def _validate_kind(kind: str) -> MemoryKind:
        normalized = kind.strip().casefold()
        if normalized not in _KINDS:
            raise MemoryError(
                'kind must be alias or preference.'
            )
        return normalized  # type: ignore[return-value]

    def _validate_name(self, name: str) -> tuple[str, str]:
        display = ' '.join(name.strip().split())
        if not display:
            raise MemoryError('Memory name must not be empty.')
        if len(display) > 80:
            raise MemoryError(
                'Memory name must not exceed 80 characters.'
            )
        normalized = normalize_memory_name(display)
        if not normalized:
            raise MemoryError(
                'Memory name must contain letters or numbers.'
            )
        return display, normalized

    def _validate_value(self, name: str, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise MemoryError('Memory value must not be empty.')
        if len(cleaned) > self.config.max_value_characters:
            raise MemoryError(
                'Memory value exceeds the configured character limit.'
            )

        combined = f'{name} {cleaned}'.casefold()
        if any(word in combined for word in _SENSITIVE_WORDS):
            raise MemoryError(
                'Passwords, authentication codes, API keys, payment '
                'details, and other secrets cannot be stored.'
            )
        if any(pattern.search(cleaned) for pattern in _SECRET_PATTERNS):
            raise MemoryError(
                'The value looks like a secret or authentication code '
                'and cannot be stored.'
            )
        return cleaned

    @staticmethod
    def _validate_url(value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme.casefold() not in {'http', 'https'}
            or not parsed.netloc
        ):
            raise MemoryError(
                'URL aliases must use http or https.'
            )
        return value

    @staticmethod
    def _validate_path(value: str) -> str:
        stripped = value.strip()
        filename = stripped.replace('\\', '/').rstrip('/').split('/')[-1]
        if filename.casefold() in _SENSITIVE_FILENAMES:
            raise MemoryError(
                'Aliases cannot point directly to credential or private '
                'key files.'
            )
        return stripped

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row['id']),
            kind=str(row['kind']),  # type: ignore[arg-type]
            name=str(row['name']),
            normalized_name=str(row['normalized_name']),
            value=str(row['value']),
            value_type=str(row['value_type']),
            created_at=str(row['created_at']),
            updated_at=str(row['updated_at']),
        )

    def _upsert(
        self,
        *,
        kind: MemoryKind,
        name: str,
        value: str,
        value_type: str,
    ) -> MemoryRecord:
        connection = self._require_connection()
        display, normalized = self._validate_name(name)
        cleaned = self._validate_value(display, value)
        timestamp = _now()

        with self._lock, connection:
            existing = connection.execute(
                'SELECT id FROM memories '
                'WHERE kind = ? AND normalized_name = ?',
                (kind, normalized),
            ).fetchone()
            if existing is None:
                count = int(
                    connection.execute(
                        'SELECT COUNT(*) FROM memories'
                    ).fetchone()[0]
                )
                if count >= self.config.max_entries:
                    raise MemoryError(
                        'The long-term memory entry limit was reached. '
                        'Forget an old item before saving another.'
                    )

            connection.execute(
                '''
                INSERT INTO memories (
                    kind,
                    name,
                    normalized_name,
                    value,
                    value_type,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind, normalized_name) DO UPDATE SET
                    name = excluded.name,
                    value = excluded.value,
                    value_type = excluded.value_type,
                    updated_at = excluded.updated_at
                ''',
                (
                    kind,
                    display,
                    normalized,
                    cleaned,
                    value_type,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                'SELECT * FROM memories '
                'WHERE kind = ? AND normalized_name = ?',
                (kind, normalized),
            ).fetchone()

        if row is None:
            raise RuntimeError('Saved memory could not be read back.')
        return self._row_to_record(row)

    def remember_alias(
        self,
        alias: str,
        target: str,
        target_type: str = 'auto',
    ) -> MemoryRecord:
        normalized_type = target_type.strip().casefold()
        if normalized_type == 'auto':
            normalized_type = infer_alias_target_type(target)
        if normalized_type not in _TARGET_TYPES:
            raise MemoryError(
                'target_type must be auto, url, path, or text.'
            )

        cleaned_target = target.strip()
        if normalized_type == 'url':
            cleaned_target = self._validate_url(cleaned_target)
        elif normalized_type == 'path':
            cleaned_target = self._validate_path(cleaned_target)

        return self._upsert(
            kind='alias',
            name=alias,
            value=cleaned_target,
            value_type=normalized_type,
        )

    def remember_preference(
        self,
        name: str,
        value: str,
    ) -> MemoryRecord:
        return self._upsert(
            kind='preference',
            name=name,
            value=value,
            value_type='text',
        )

    def get(
        self,
        kind: str,
        name: str,
    ) -> MemoryRecord | None:
        if not self.config.enabled:
            return None
        valid_kind = self._validate_kind(kind)
        _, normalized = self._validate_name(name)
        connection = self._require_connection()
        with self._lock:
            row = connection.execute(
                'SELECT * FROM memories '
                'WHERE kind = ? AND normalized_name = ?',
                (valid_kind, normalized),
            ).fetchone()
        return (
            self._row_to_record(row)
            if row is not None
            else None
        )

    def resolve_alias(self, alias: str) -> MemoryRecord | None:
        return self.get('alias', alias)

    def get_preference(self, name: str) -> str | None:
        record = self.get('preference', name)
        return record.value if record is not None else None

    def list_memories(
        self,
        kind: str = 'all',
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        if not self.config.enabled:
            return ()
        if not 1 <= limit <= 500:
            raise MemoryError('limit must be between 1 and 500.')

        connection = self._require_connection()
        normalized_kind = kind.strip().casefold()
        if normalized_kind == 'all':
            query = (
                'SELECT * FROM memories '
                'ORDER BY updated_at DESC, id DESC LIMIT ?'
            )
            parameters: tuple[Any, ...] = (limit,)
        else:
            valid_kind = self._validate_kind(normalized_kind)
            query = (
                'SELECT * FROM memories WHERE kind = ? '
                'ORDER BY updated_at DESC, id DESC LIMIT ?'
            )
            parameters = (valid_kind, limit)

        with self._lock:
            rows = connection.execute(
                query,
                parameters,
            ).fetchall()
        return tuple(
            self._row_to_record(row)
            for row in rows
        )

    def forget(self, kind: str, name: str) -> bool:
        valid_kind = self._validate_kind(kind)
        _, normalized = self._validate_name(name)
        connection = self._require_connection()
        with self._lock, connection:
            cursor = connection.execute(
                'DELETE FROM memories '
                'WHERE kind = ? AND normalized_name = ?',
                (valid_kind, normalized),
            )
        return cursor.rowcount > 0

    def count(self) -> int:
        if not self.config.enabled:
            return 0
        connection = self._require_connection()
        with self._lock:
            row = connection.execute(
                'SELECT COUNT(*) FROM memories'
            ).fetchone()
        return int(row[0])

    def prompt_context(self) -> str:
        if not self.config.enabled:
            return ''
        records = self.list_memories(
            'all',
            limit=self.config.context_limit,
        )
        if not records:
            return ''

        payload = [
            {
                'kind': record.kind,
                'name': record.name,
                'value': record.value,
                'value_type': record.value_type,
            }
            for record in records
        ]
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(',', ':'),
        )
        limit = self.config.max_context_characters
        if len(encoded) > limit:
            encoded = encoded[:limit]
        return encoded

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> LocalMemoryStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
