from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Callable, Literal


StructuredMemoryKind = Literal[
    "project",
    "decision",
    "todo",
    "relation",
    "summary",
]

_STRUCTURED_KINDS = {
    "project",
    "decision",
    "todo",
    "relation",
    "summary",
}
_STATUSES = {
    "active",
    "pending",
    "in_progress",
    "completed",
    "cancelled",
    "superseded",
    "archived",
}
_CURRENT_STATUSES = {
    "active",
    "pending",
    "in_progress",
}
_STATUS_BY_KIND = {
    "project": {"active", "completed", "archived"},
    "decision": {"active", "superseded", "archived"},
    "todo": {
        "pending",
        "in_progress",
        "completed",
        "cancelled",
        "archived",
    },
    "relation": {"active", "archived"},
    "summary": {"active", "superseded", "archived"},
}
_TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9가-힣]{2,}",
    flags=re.UNICODE,
)
_SEARCH_STOPWORDS = {
    "상태",
    "현재",
    "정보",
    "내용",
    "프로젝트",
    "단계",
    "알려줘",
    "확인",
}


class StructuredMemoryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StructuredMemoryRecord:
    id: int
    kind: StructuredMemoryKind
    scope: str
    normalized_scope: str
    name: str
    normalized_name: str
    value: str
    notes: str
    status: str
    importance: int
    confidence: float
    source: str
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    access_count: int

    def as_dict(
        self,
        *,
        stale: bool = False,
        age_days: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "scope": self.scope,
            "name": self.name,
            "value": self.value,
            "notes": self.notes,
            "status": self.status,
            "importance": self.importance,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "stale": stale,
            "age_days": round(age_days, 2),
        }


@dataclass(frozen=True, slots=True)
class MemoryConflictRecord:
    id: int
    kind: StructuredMemoryKind
    scope: str
    name: str
    current_record_id: int
    current_payload: dict[str, Any]
    candidate_payload: dict[str, Any]
    status: str
    resolution: str
    created_at: str
    resolved_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "scope": self.scope,
            "name": self.name,
            "current_record_id": self.current_record_id,
            "current": self.current_payload,
            "candidate": self.candidate_payload,
            "status": self.status,
            "resolution": self.resolution,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    stored: bool
    unchanged: bool
    record: StructuredMemoryRecord | None
    conflict: MemoryConflictRecord | None


@dataclass(frozen=True, slots=True)
class StructuredMemoryConfig:
    database: Path
    max_entries: int
    max_value_characters: int
    context_limit: int
    relevance_search_enabled: bool
    stale_after_days: int
    max_history_entries: int
    max_conflicts: int
    include_completed_todos_in_context: bool


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_datetime().isoformat(timespec="seconds")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return _now_datetime()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize(value: str) -> str:
    return re.sub(
        r"[\W_]+",
        "",
        value,
        flags=re.UNICODE,
    ).casefold()


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_PATTERN.findall(value)
        if token.casefold() not in _SEARCH_STOPWORDS
    }


class StructuredMemoryStore:
    def __init__(
        self,
        config: StructuredMemoryConfig,
        *,
        total_count: Callable[[], int],
        validate_safe_text: Callable[..., None],
    ) -> None:
        self.config = config
        self._total_count = total_count
        self._validate_safe_text = validate_safe_text
        self._lock = RLock()
        self._closed = False

        path = config.database.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            path,
            timeout=5.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        self._connection = connection
        self._initialize_schema()

    def _require_connection(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("Structured memory store is closed.")
        return self._connection

    def _initialize_schema(self) -> None:
        connection = self._require_connection()
        with self._lock, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS structured_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    normalized_scope TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    status TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(kind, normalized_scope, normalized_name)
                );

                CREATE INDEX IF NOT EXISTS idx_structured_memory_scope
                ON structured_memories(
                    normalized_scope,
                    kind,
                    status,
                    updated_at DESC
                );

                CREATE INDEX IF NOT EXISTS idx_structured_memory_updated
                ON structured_memories(updated_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    structured_memory_id INTEGER,
                    action TEXT NOT NULL,
                    old_payload TEXT NOT NULL,
                    new_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_history_record
                ON memory_history(
                    structured_memory_id,
                    created_at DESC,
                    id DESC
                );

                CREATE TABLE IF NOT EXISTS memory_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    normalized_scope TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    current_record_id INTEGER NOT NULL,
                    current_payload TEXT NOT NULL,
                    candidate_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_memory_conflicts_status
                ON memory_conflicts(status, created_at DESC, id DESC);
                """
            )

    @staticmethod
    def _validate_kind(kind: str) -> StructuredMemoryKind:
        normalized = kind.strip().casefold()
        if normalized not in _STRUCTURED_KINDS:
            raise StructuredMemoryError(
                "kind must be project, decision, todo, relation, or summary."
            )
        return normalized  # type: ignore[return-value]

    @staticmethod
    def _validate_named_value(
        value: str,
        *,
        label: str,
        maximum: int,
    ) -> tuple[str, str]:
        display = " ".join(value.strip().split())
        if not display:
            raise StructuredMemoryError(f"{label} must not be empty.")
        if len(display) > maximum:
            raise StructuredMemoryError(
                f"{label} must not exceed {maximum} characters."
            )
        normalized = _normalize(display)
        if not normalized:
            raise StructuredMemoryError(
                f"{label} must contain letters or numbers."
            )
        return display, normalized

    def _validate_text(
        self,
        value: str,
        *,
        label: str,
        allow_empty: bool,
        maximum: int | None = None,
    ) -> str:
        cleaned = value.strip()
        if not cleaned and not allow_empty:
            raise StructuredMemoryError(f"{label} must not be empty.")
        limit = maximum or self.config.max_value_characters
        if len(cleaned) > limit:
            raise StructuredMemoryError(
                f"{label} exceeds the configured character limit."
            )
        return cleaned

    @staticmethod
    def _validate_status(
        kind: StructuredMemoryKind,
        status: str,
    ) -> str:
        normalized = status.strip().casefold()
        allowed = _STATUS_BY_KIND[kind]
        if normalized not in allowed:
            raise StructuredMemoryError(
                f"Invalid status for {kind}: " + ", ".join(sorted(allowed))
            )
        return normalized

    @staticmethod
    def _validate_importance(value: int) -> int:
        if not 1 <= value <= 5:
            raise StructuredMemoryError(
                "importance must be between 1 and 5."
            )
        return value

    @staticmethod
    def _validate_confidence(value: float) -> float:
        numeric = float(value)
        if not 0.0 <= numeric <= 1.0:
            raise StructuredMemoryError(
                "confidence must be between 0 and 1."
            )
        return numeric

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> StructuredMemoryRecord:
        return StructuredMemoryRecord(
            id=int(row["id"]),
            kind=str(row["kind"]),  # type: ignore[arg-type]
            scope=str(row["scope"]),
            normalized_scope=str(row["normalized_scope"]),
            name=str(row["name"]),
            normalized_name=str(row["normalized_name"]),
            value=str(row["value"]),
            notes=str(row["notes"]),
            status=str(row["status"]),
            importance=int(row["importance"]),
            confidence=float(row["confidence"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_accessed_at=(
                str(row["last_accessed_at"])
                if row["last_accessed_at"] is not None
                else None
            ),
            access_count=int(row["access_count"]),
        )

    @staticmethod
    def _row_to_conflict(row: sqlite3.Row) -> MemoryConflictRecord:
        return MemoryConflictRecord(
            id=int(row["id"]),
            kind=str(row["kind"]),  # type: ignore[arg-type]
            scope=str(row["scope"]),
            name=str(row["name"]),
            current_record_id=int(row["current_record_id"]),
            current_payload=json.loads(str(row["current_payload"])),
            candidate_payload=json.loads(str(row["candidate_payload"])),
            status=str(row["status"]),
            resolution=str(row["resolution"]),
            created_at=str(row["created_at"]),
            resolved_at=(
                str(row["resolved_at"])
                if row["resolved_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _payload(record: StructuredMemoryRecord) -> dict[str, Any]:
        return {
            "kind": record.kind,
            "scope": record.scope,
            "name": record.name,
            "value": record.value,
            "notes": record.notes,
            "status": record.status,
            "importance": record.importance,
            "confidence": record.confidence,
            "source": record.source,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _material(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: payload.get(key)
            for key in (
                "kind",
                "scope",
                "name",
                "value",
                "notes",
                "status",
                "importance",
                "confidence",
                "source",
            )
        }

    def _public(self, record: StructuredMemoryRecord) -> dict[str, Any]:
        age = (
            _now_datetime() - _parse_timestamp(record.updated_at)
        ).total_seconds() / 86_400
        stale = (
            record.status in _CURRENT_STATUSES
            and age >= self.config.stale_after_days
        )
        return record.as_dict(
            stale=stale,
            age_days=max(0.0, age),
        )

    def public_record(self, record: StructuredMemoryRecord) -> dict[str, Any]:
        return self._public(record)

    def count(self) -> int:
        connection = self._require_connection()
        with self._lock:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM structured_memories"
                ).fetchone()[0]
            )

    def get(
        self,
        kind: str,
        scope: str,
        name: str,
    ) -> StructuredMemoryRecord | None:
        valid_kind = self._validate_kind(kind)
        _, normalized_scope = self._validate_named_value(
            scope,
            label="Memory scope",
            maximum=120,
        )
        _, normalized_name = self._validate_named_value(
            name,
            label="Memory name",
            maximum=160,
        )
        connection = self._require_connection()
        with self._lock:
            row = connection.execute(
                """
                SELECT * FROM structured_memories
                WHERE kind = ?
                AND normalized_scope = ?
                AND normalized_name = ?
                """,
                (valid_kind, normalized_scope, normalized_name),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def _append_history(
        self,
        *,
        record_id: int,
        action: str,
        old_payload: dict[str, Any],
        new_payload: dict[str, Any],
    ) -> None:
        connection = self._require_connection()
        connection.execute(
            """
            INSERT INTO memory_history (
                structured_memory_id,
                action,
                old_payload,
                new_payload,
                created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                record_id,
                action,
                json.dumps(
                    old_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    new_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                _now(),
            ),
        )
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM memory_history"
            ).fetchone()[0]
        )
        excess = count - self.config.max_history_entries
        if excess > 0:
            connection.execute(
                """
                DELETE FROM memory_history
                WHERE id IN (
                    SELECT id FROM memory_history
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (excess,),
            )

    def _create_conflict(
        self,
        current: StructuredMemoryRecord,
        candidate: dict[str, Any],
    ) -> MemoryConflictRecord:
        connection = self._require_connection()
        current_json = json.dumps(
            self._payload(current),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        candidate_json = json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        existing = connection.execute(
            """
            SELECT * FROM memory_conflicts
            WHERE status = 'pending'
            AND current_record_id = ?
            AND candidate_payload = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (current.id, candidate_json),
        ).fetchone()
        if existing is not None:
            return self._row_to_conflict(existing)

        pending = int(
            connection.execute(
                "SELECT COUNT(*) FROM memory_conflicts WHERE status = 'pending'"
            ).fetchone()[0]
        )
        if pending >= self.config.max_conflicts:
            raise StructuredMemoryError(
                "The pending memory conflict limit was reached."
            )
        cursor = connection.execute(
            """
            INSERT INTO memory_conflicts (
                kind,
                scope,
                normalized_scope,
                name,
                normalized_name,
                current_record_id,
                current_payload,
                candidate_payload,
                status,
                resolution,
                created_at,
                resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, NULL)
            """,
            (
                current.kind,
                current.scope,
                current.normalized_scope,
                current.name,
                current.normalized_name,
                current.id,
                current_json,
                candidate_json,
                _now(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM memory_conflicts WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Memory conflict could not be read back.")
        return self._row_to_conflict(row)

    def remember(
        self,
        *,
        kind: str,
        scope: str,
        name: str,
        value: str,
        notes: str,
        status: str,
        importance: int,
        confidence: float,
        replace_existing: bool,
    ) -> MemoryWriteResult:
        valid_kind = self._validate_kind(kind)
        display_scope, normalized_scope = self._validate_named_value(
            scope,
            label="Memory scope",
            maximum=120,
        )
        display_name, normalized_name = self._validate_named_value(
            name,
            label="Memory name",
            maximum=160,
        )
        cleaned_value = self._validate_text(
            value,
            label="Memory value",
            allow_empty=False,
        )
        cleaned_notes = self._validate_text(
            notes,
            label="Memory notes",
            allow_empty=True,
            maximum=min(4096, self.config.max_value_characters * 2),
        )
        valid_status = self._validate_status(valid_kind, status)
        valid_importance = self._validate_importance(importance)
        valid_confidence = self._validate_confidence(confidence)
        self._validate_safe_text(
            display_scope,
            display_name,
            cleaned_value,
            cleaned_notes,
        )
        source = "explicit_user"
        candidate = {
            "kind": valid_kind,
            "scope": display_scope,
            "name": display_name,
            "value": cleaned_value,
            "notes": cleaned_notes,
            "status": valid_status,
            "importance": valid_importance,
            "confidence": valid_confidence,
            "source": source,
        }
        connection = self._require_connection()
        timestamp = _now()

        with self._lock, connection:
            row = connection.execute(
                """
                SELECT * FROM structured_memories
                WHERE kind = ?
                AND normalized_scope = ?
                AND normalized_name = ?
                """,
                (valid_kind, normalized_scope, normalized_name),
            ).fetchone()
            current = self._row_to_record(row) if row is not None else None

            if current is not None:
                current_payload = self._payload(current)
                if self._material(current_payload) == self._material(candidate):
                    connection.execute(
                        "UPDATE structured_memories SET updated_at = ? WHERE id = ?",
                        (timestamp, current.id),
                    )
                    refreshed = connection.execute(
                        "SELECT * FROM structured_memories WHERE id = ?",
                        (current.id,),
                    ).fetchone()
                    return MemoryWriteResult(
                        stored=True,
                        unchanged=True,
                        record=(
                            self._row_to_record(refreshed)
                            if refreshed is not None
                            else current
                        ),
                        conflict=None,
                    )

                if not replace_existing:
                    return MemoryWriteResult(
                        stored=False,
                        unchanged=False,
                        record=current,
                        conflict=self._create_conflict(current, candidate),
                    )

                self._append_history(
                    record_id=current.id,
                    action="replace",
                    old_payload=current_payload,
                    new_payload=candidate,
                )
                connection.execute(
                    """
                    UPDATE structured_memories
                    SET
                        scope = ?,
                        normalized_scope = ?,
                        name = ?,
                        normalized_name = ?,
                        value = ?,
                        notes = ?,
                        status = ?,
                        importance = ?,
                        confidence = ?,
                        source = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        display_scope,
                        normalized_scope,
                        display_name,
                        normalized_name,
                        cleaned_value,
                        cleaned_notes,
                        valid_status,
                        valid_importance,
                        valid_confidence,
                        source,
                        timestamp,
                        current.id,
                    ),
                )
                updated = connection.execute(
                    "SELECT * FROM structured_memories WHERE id = ?",
                    (current.id,),
                ).fetchone()
                if updated is None:
                    raise RuntimeError("Updated memory could not be read back.")
                return MemoryWriteResult(
                    stored=True,
                    unchanged=False,
                    record=self._row_to_record(updated),
                    conflict=None,
                )

            if self._total_count() >= self.config.max_entries:
                raise StructuredMemoryError(
                    "The long-term memory entry limit was reached."
                )
            cursor = connection.execute(
                """
                INSERT INTO structured_memories (
                    kind,
                    scope,
                    normalized_scope,
                    name,
                    normalized_name,
                    value,
                    notes,
                    status,
                    importance,
                    confidence,
                    source,
                    created_at,
                    updated_at,
                    last_accessed_at,
                    access_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)
                """,
                (
                    valid_kind,
                    display_scope,
                    normalized_scope,
                    display_name,
                    normalized_name,
                    cleaned_value,
                    cleaned_notes,
                    valid_status,
                    valid_importance,
                    valid_confidence,
                    source,
                    timestamp,
                    timestamp,
                ),
            )
            created = connection.execute(
                "SELECT * FROM structured_memories WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        if created is None:
            raise RuntimeError("Structured memory could not be read back.")
        return MemoryWriteResult(
            stored=True,
            unchanged=False,
            record=self._row_to_record(created),
            conflict=None,
        )

    def _mark_accessed(self, record_ids: list[int]) -> None:
        if not record_ids:
            return
        connection = self._require_connection()
        placeholders = ",".join("?" for _ in record_ids)
        with self._lock, connection:
            connection.execute(
                f"""
                UPDATE structured_memories
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE id IN ({placeholders})
                """,
                (_now(), *record_ids),
            )

    @staticmethod
    def _score(
        query: str,
        query_tokens: set[str],
        record: StructuredMemoryRecord,
    ) -> float:
        base = record.importance * 8 + record.confidence * 5
        if not query:
            return base
        scope_name = f"{record.scope} {record.name}".casefold()
        value = record.value.casefold()
        notes = record.notes.casefold()
        score = base
        if query == record.name.casefold():
            score += 130
        if query in scope_name:
            score += 90
        if query in value:
            score += 55
        if query in notes:
            score += 25
        record_tokens = _tokens(
            " ".join(
                (record.scope, record.name, record.value, record.notes)
            )
        )
        overlap = len(query_tokens & record_tokens)
        score += overlap * 24
        if query_tokens:
            score += overlap / len(query_tokens) * 30
        return score

    def search(
        self,
        *,
        query: str,
        scope: str,
        kind: str,
        status: str,
        limit: int,
        mark_accessed: bool = True,
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 100:
            raise StructuredMemoryError("limit must be between 1 and 100.")
        normalized_kind = kind.strip().casefold()
        if normalized_kind != "all" and normalized_kind not in _STRUCTURED_KINDS:
            raise StructuredMemoryError("Invalid structured memory kind filter.")
        normalized_status = status.strip().casefold()
        if normalized_status not in (_STATUSES | {"all", "current"}):
            raise StructuredMemoryError("Invalid memory status filter.")

        clauses: list[str] = []
        parameters: list[Any] = []
        if normalized_kind != "all":
            clauses.append("kind = ?")
            parameters.append(normalized_kind)
        if scope.strip().casefold() != "all":
            _, scope_key = self._validate_named_value(
                scope,
                label="Memory scope",
                maximum=120,
            )
            clauses.append("normalized_scope = ?")
            parameters.append(scope_key)
        if normalized_status == "current":
            placeholders = ",".join("?" for _ in _CURRENT_STATUSES)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(sorted(_CURRENT_STATUSES))
        elif normalized_status != "all":
            clauses.append("status = ?")
            parameters.append(normalized_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""

        connection = self._require_connection()
        with self._lock:
            rows = connection.execute(
                "SELECT * FROM structured_memories"
                + where
                + " ORDER BY importance DESC, updated_at DESC, id DESC LIMIT 500",
                tuple(parameters),
            ).fetchall()
        records = [self._row_to_record(row) for row in rows]
        cleaned_query = " ".join(query.strip().split()).casefold()
        query_tokens = _tokens(cleaned_query)
        ranked: list[tuple[float, StructuredMemoryRecord]] = []
        for record in records:
            score = self._score(cleaned_query, query_tokens, record)
            base = record.importance * 8 + record.confidence * 5
            if (
                cleaned_query
                and self.config.relevance_search_enabled
                and (score - base) < 20
            ):
                continue
            ranked.append((score, record))
        ranked.sort(
            key=lambda item: (
                -item[0],
                -item[1].importance,
                item[1].updated_at,
                item[1].id,
            )
        )
        chosen = ranked[:limit]
        if mark_accessed:
            self._mark_accessed([record.id for _, record in chosen])
        return tuple(
            {
                **self._public(record),
                "relevance_score": round(score, 2),
            }
            for score, record in chosen
        )

    def set_status(
        self,
        *,
        kind: str,
        scope: str,
        name: str,
        status: str,
    ) -> StructuredMemoryRecord:
        record = self.get(kind, scope, name)
        if record is None:
            raise StructuredMemoryError("The structured memory was not found.")
        valid_status = self._validate_status(record.kind, status)
        if valid_status == record.status:
            return record
        old_payload = self._payload(record)
        new_payload = dict(old_payload)
        new_payload["status"] = valid_status
        new_payload["updated_at"] = _now()
        connection = self._require_connection()
        with self._lock, connection:
            self._append_history(
                record_id=record.id,
                action="status",
                old_payload=old_payload,
                new_payload=new_payload,
            )
            connection.execute(
                "UPDATE structured_memories SET status = ?, updated_at = ? WHERE id = ?",
                (valid_status, new_payload["updated_at"], record.id),
            )
            row = connection.execute(
                "SELECT * FROM structured_memories WHERE id = ?",
                (record.id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Updated memory could not be read back.")
        return self._row_to_record(row)

    def project_snapshot(
        self,
        *,
        scope: str,
        include_completed: bool,
        limit: int,
    ) -> dict[str, Any]:
        items = self.search(
            query="",
            scope=scope,
            kind="all",
            status="all",
            limit=min(limit, 100),
        )
        visible: list[dict[str, Any]] = []
        for item in items:
            if item["status"] in {"archived", "superseded", "cancelled"}:
                continue
            if (
                item["kind"] == "todo"
                and item["status"] == "completed"
                and not include_completed
            ):
                continue
            visible.append(item)
        grouped = {
            memory_kind: [
                item for item in visible if item["kind"] == memory_kind
            ]
            for memory_kind in _STRUCTURED_KINDS
        }
        conflicts = self.list_conflicts(
            scope=scope,
            status="pending",
            limit=20,
        )
        return {
            "scope": scope,
            "count": len(visible),
            "project": grouped["project"],
            "decisions": grouped["decision"],
            "todos": grouped["todo"],
            "relations": grouped["relation"],
            "summaries": grouped["summary"],
            "pending_conflict_count": len(conflicts),
            "has_stale_items": any(bool(item.get("stale")) for item in visible),
        }

    def list_conflicts(
        self,
        *,
        scope: str,
        status: str,
        limit: int,
    ) -> tuple[MemoryConflictRecord, ...]:
        if not 1 <= limit <= 100:
            raise StructuredMemoryError("limit must be between 1 and 100.")
        normalized_status = status.strip().casefold()
        if normalized_status not in {"all", "pending", "resolved", "ignored"}:
            raise StructuredMemoryError("Invalid conflict status filter.")
        clauses: list[str] = []
        parameters: list[Any] = []
        if scope.strip().casefold() != "all":
            _, scope_key = self._validate_named_value(
                scope,
                label="Memory scope",
                maximum=120,
            )
            clauses.append("normalized_scope = ?")
            parameters.append(scope_key)
        if normalized_status != "all":
            clauses.append("status = ?")
            parameters.append(normalized_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        connection = self._require_connection()
        with self._lock:
            rows = connection.execute(
                "SELECT * FROM memory_conflicts"
                + where
                + " ORDER BY created_at DESC, id DESC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
        return tuple(self._row_to_conflict(row) for row in rows)

    def resolve_conflict(
        self,
        *,
        conflict_id: int,
        resolution: str,
        merged_value: str,
        merged_notes: str,
        merged_status: str,
        merged_importance: int,
        merged_confidence: float,
    ) -> dict[str, Any]:
        normalized_resolution = resolution.strip().casefold()
        if normalized_resolution not in {
            "keep_existing",
            "use_candidate",
            "merge",
        }:
            raise StructuredMemoryError("Invalid conflict resolution.")
        connection = self._require_connection()
        with self._lock, connection:
            row = connection.execute(
                "SELECT * FROM memory_conflicts WHERE id = ?",
                (conflict_id,),
            ).fetchone()
            if row is None:
                raise StructuredMemoryError("The memory conflict was not found.")
            conflict = self._row_to_conflict(row)
            if conflict.status != "pending":
                raise StructuredMemoryError("The memory conflict is already resolved.")
            current_row = connection.execute(
                "SELECT * FROM structured_memories WHERE id = ?",
                (conflict.current_record_id,),
            ).fetchone()
            if current_row is None:
                raise StructuredMemoryError("The current memory no longer exists.")
            current = self._row_to_record(current_row)
            if self._material(self._payload(current)) != self._material(
                conflict.current_payload
            ):
                raise StructuredMemoryError(
                    "The current memory changed after this conflict was created."
                )

            updated: StructuredMemoryRecord | None = None
            if normalized_resolution == "keep_existing":
                final_resolution = "keep_existing"
            else:
                candidate = dict(conflict.candidate_payload)
                if normalized_resolution == "merge":
                    candidate.update(
                        {
                            "value": self._validate_text(
                                merged_value,
                                label="Merged value",
                                allow_empty=False,
                            ),
                            "notes": self._validate_text(
                                merged_notes,
                                label="Merged notes",
                                allow_empty=True,
                                maximum=min(
                                    4096,
                                    self.config.max_value_characters * 2,
                                ),
                            ),
                            "status": self._validate_status(
                                current.kind,
                                merged_status,
                            ),
                            "importance": self._validate_importance(
                                merged_importance
                            ),
                            "confidence": self._validate_confidence(
                                merged_confidence
                            ),
                        }
                    )
                    self._validate_safe_text(
                        str(candidate["value"]),
                        str(candidate["notes"]),
                    )
                candidate["updated_at"] = _now()
                self._append_history(
                    record_id=current.id,
                    action="resolve_conflict",
                    old_payload=self._payload(current),
                    new_payload=candidate,
                )
                connection.execute(
                    """
                    UPDATE structured_memories
                    SET
                        scope = ?,
                        normalized_scope = ?,
                        name = ?,
                        normalized_name = ?,
                        value = ?,
                        notes = ?,
                        status = ?,
                        importance = ?,
                        confidence = ?,
                        source = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        str(candidate["scope"]),
                        _normalize(str(candidate["scope"])),
                        str(candidate["name"]),
                        _normalize(str(candidate["name"])),
                        str(candidate["value"]),
                        str(candidate["notes"]),
                        str(candidate["status"]),
                        int(candidate["importance"]),
                        float(candidate["confidence"]),
                        str(candidate["source"]),
                        str(candidate["updated_at"]),
                        current.id,
                    ),
                )
                updated_row = connection.execute(
                    "SELECT * FROM structured_memories WHERE id = ?",
                    (current.id,),
                ).fetchone()
                if updated_row is None:
                    raise RuntimeError("Resolved memory could not be read back.")
                updated = self._row_to_record(updated_row)
                final_resolution = normalized_resolution

            connection.execute(
                """
                UPDATE memory_conflicts
                SET status = 'resolved', resolution = ?, resolved_at = ?
                WHERE id = ?
                """,
                (final_resolution, _now(), conflict.id),
            )
        return {
            "resolved": True,
            "conflict_id": conflict.id,
            "resolution": final_resolution,
            "memory": self._public(updated or current),
        }

    def history(
        self,
        *,
        kind: str,
        scope: str,
        name: str,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 100:
            raise StructuredMemoryError("limit must be between 1 and 100.")
        record = self.get(kind, scope, name)
        if record is None:
            raise StructuredMemoryError("The structured memory was not found.")
        connection = self._require_connection()
        with self._lock:
            rows = connection.execute(
                """
                SELECT * FROM memory_history
                WHERE structured_memory_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (record.id, limit),
            ).fetchall()
        return tuple(
            {
                "id": int(row["id"]),
                "action": str(row["action"]),
                "old": json.loads(str(row["old_payload"])),
                "new": json.loads(str(row["new_payload"])),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        )

    def health(self, *, scope: str, limit: int) -> dict[str, Any]:
        items = self.search(
            query="",
            scope=scope,
            kind="all",
            status="all",
            limit=min(limit, 100),
            mark_accessed=False,
        )
        stale = [item for item in items if item.get("stale")]
        completed_todos = [
            item
            for item in items
            if item["kind"] == "todo"
            and item["status"] in {"completed", "cancelled"}
        ]
        conflicts = self.list_conflicts(
            scope=scope,
            status="pending",
            limit=min(limit, 100),
        )
        recommendations: list[str] = []
        if stale:
            recommendations.append(
                "오래된 현재 기억을 사용자에게 확인한 뒤 갱신하거나 보관 처리하세요."
            )
        if completed_todos:
            recommendations.append(
                "완료·취소된 TODO는 필요하면 archived 상태로 정리하세요."
            )
        if conflicts:
            recommendations.append(
                "충돌은 최신 사용자 확인을 받은 뒤 해결하세요."
            )
        return {
            "scope": scope,
            "total_items": len(items),
            "stale_count": len(stale),
            "stale_items": stale,
            "completed_todo_count": len(completed_todos),
            "completed_todos": completed_todos,
            "pending_conflict_count": len(conflicts),
            "pending_conflicts": [item.as_dict() for item in conflicts],
            "recommendations": recommendations,
        }

    def context_items(self, query: str) -> list[dict[str, Any]]:
        items = list(
            self.search(
                query=(query if self.config.relevance_search_enabled else ""),
                scope="all",
                kind="all",
                status="current",
                limit=min(self.config.context_limit, 100),
                mark_accessed=True,
            )
        )
        if self.config.include_completed_todos_in_context:
            completed = self.search(
                query=query,
                scope="all",
                kind="todo",
                status="completed",
                limit=min(5, self.config.context_limit),
                mark_accessed=True,
            )
            known = {item["id"] for item in items}
            items.extend(item for item in completed if item["id"] not in known)
        return items

    def pending_conflict_count(self) -> int:
        connection = self._require_connection()
        with self._lock:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM memory_conflicts WHERE status = 'pending'"
                ).fetchone()[0]
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._connection.close()
