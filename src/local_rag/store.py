from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sqlite3
from threading import RLock
from time import time
from typing import Any, Iterable, Iterator


class LocalRagError(ValueError):
    pass


_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".py",
    ".pyi",
    ".toml",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".csv",
    ".log",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".rs",
    ".go",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
}
_SUPPORTED_EXTENSIONS = _TEXT_EXTENSIONS | {".pdf", ".docx"}
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "edge_profile",
}
_EXACT_EXCLUDED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "google_calendar_credentials.json",
    "gmail_credentials.json",
    "service-account.json",
    "service_account.json",
    "token.json",
    "id_rsa",
    "id_ed25519",
    "private_key.pem",
}
_SENSITIVE_NAME_PARTS = (
    "credential",
    "secret",
    "private_key",
    "private-key",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
)
_SECRET_CONTENT_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣_]{2,}", re.UNICODE)
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "있는",
    "하는",
    "에서",
    "으로",
    "그리고",
    "관련",
    "내용",
    "파일",
}


@dataclass(frozen=True, slots=True)
class LocalRagConfig:
    enabled: bool = True
    database: Path = Path("data/jarvis_rag.db")
    roots: tuple[Path, ...] = (
        Path("documents"),
        Path("notes"),
        Path("src"),
    )
    default_collection: str = "jarvis"
    auto_index_on_startup: bool = False
    max_file_bytes: int = 10 * 1024 * 1024
    chunk_characters: int = 1_800
    chunk_overlap_characters: int = 240
    max_files: int = 5_000
    max_chunks: int = 100_000
    default_search_limit: int = 8
    prune_missing: bool = True

    def __post_init__(self) -> None:
        if not self.default_collection.strip():
            raise ValueError("default_collection must not be empty.")
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive.")
        if self.chunk_characters < 200:
            raise ValueError("chunk_characters must be at least 200.")
        if not 0 <= self.chunk_overlap_characters < self.chunk_characters:
            raise ValueError(
                "chunk_overlap_characters must be non-negative and smaller than chunk_characters."
            )
        if self.max_files <= 0:
            raise ValueError("max_files must be positive.")
        if self.max_chunks <= 0:
            raise ValueError("max_chunks must be positive.")
        if not 1 <= self.default_search_limit <= 50:
            raise ValueError("default_search_limit must be between 1 and 50.")


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    text: str
    line_start: int | None
    line_end: int | None
    page: int | None


@dataclass(frozen=True, slots=True)
class RagChunk:
    id: int
    collection: str
    path: str
    extension: str
    text: str
    line_start: int | None
    line_end: int | None
    page: int | None
    chunk_index: int
    indexed_at: str

    def citation(self) -> str:
        if self.page is not None:
            return f"{self.path}#page={self.page}"
        if self.line_start is not None:
            if self.line_end == self.line_start:
                return f"{self.path}:L{self.line_start}"
            return f"{self.path}:L{self.line_start}-L{self.line_end}"
        return self.path

    def as_dict(self, *, score: float | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "chunk_id": self.id,
            "collection": self.collection,
            "path": self.path,
            "extension": self.extension,
            "text": self.text,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "indexed_at": self.indexed_at,
            "citation": self.citation(),
        }
        if score is not None:
            result["score"] = round(score, 4)
        return result


def _utc_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_collection(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise LocalRagError("collection must not be empty.")
    if len(cleaned) > 100:
        raise LocalRagError("collection must not exceed 100 characters.")
    return cleaned


def _tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in _TOKEN_PATTERN.findall(text)
        if token.casefold() not in _STOPWORDS
    ]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _looks_sensitive(path: Path) -> bool:
    lowered = path.name.casefold()
    if lowered in _EXACT_EXCLUDED_FILES:
        return True
    if lowered.startswith(".env"):
        return True
    stem = path.stem.casefold()
    return any(part in stem for part in _SENSITIVE_NAME_PARTS)


def _is_excluded_path(path: Path) -> bool:
    return any(part.casefold() in _EXCLUDED_DIRECTORIES for part in path.parts)


def _decode_text(raw: bytes) -> str:
    if b"\x00" in raw[:4096]:
        raise LocalRagError("Binary files are not indexed.")
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _chunk_numbered_lines(
    lines: list[tuple[int, str]],
    *,
    chunk_characters: int,
    overlap_characters: int,
    page: int | None = None,
) -> list[ExtractedSection]:
    cleaned = [(number, text.rstrip()) for number, text in lines]
    cleaned = [(number, text) for number, text in cleaned if text.strip()]
    if not cleaned:
        return []

    sections: list[ExtractedSection] = []
    start = 0
    while start < len(cleaned):
        length = 0
        end = start
        while end < len(cleaned):
            addition = len(cleaned[end][1]) + 1
            if end > start and length + addition > chunk_characters:
                break
            length += addition
            end += 1
        if end == start:
            end += 1

        selected = cleaned[start:end]
        sections.append(
            ExtractedSection(
                text="\n".join(text for _, text in selected).strip(),
                line_start=(selected[0][0] if page is None else None),
                line_end=(selected[-1][0] if page is None else None),
                page=page,
            )
        )
        if end >= len(cleaned):
            break

        overlap = 0
        next_start = end
        while next_start > start + 1 and overlap < overlap_characters:
            next_start -= 1
            overlap += len(cleaned[next_start][1]) + 1
        start = max(start + 1, next_start)
    return sections


def _extract_text_file(path: Path, config: LocalRagConfig) -> list[ExtractedSection]:
    raw = path.read_bytes()
    text = _decode_text(raw)
    return _chunk_numbered_lines(
        list(enumerate(text.splitlines(), start=1)),
        chunk_characters=config.chunk_characters,
        overlap_characters=config.chunk_overlap_characters,
    )


def _extract_pdf(path: Path, config: LocalRagConfig) -> list[ExtractedSection]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise LocalRagError(
            "PDF support requires pypdf. Run `python -m pip install -r requirements.txt`."
        ) from exc

    sections: list[ExtractedSection] = []
    reader = PdfReader(str(path))
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        sections.extend(
            _chunk_numbered_lines(
                list(enumerate(text.splitlines(), start=1)),
                chunk_characters=config.chunk_characters,
                overlap_characters=config.chunk_overlap_characters,
                page=page_index,
            )
        )
    return sections


def _extract_docx(path: Path, config: LocalRagConfig) -> list[ExtractedSection]:
    try:
        from docx import Document
    except ImportError as exc:
        raise LocalRagError(
            "DOCX support requires python-docx. Run `python -m pip install -r requirements.txt`."
        ) from exc

    document = Document(str(path))
    lines = [
        (index, paragraph.text)
        for index, paragraph in enumerate(document.paragraphs, start=1)
    ]
    return _chunk_numbered_lines(
        lines,
        chunk_characters=config.chunk_characters,
        overlap_characters=config.chunk_overlap_characters,
    )


def _extract_sections(path: Path, config: LocalRagConfig) -> list[ExtractedSection]:
    extension = path.suffix.casefold()
    if extension in _TEXT_EXTENSIONS:
        return _extract_text_file(path, config)
    if extension == ".pdf":
        return _extract_pdf(path, config)
    if extension == ".docx":
        return _extract_docx(path, config)
    raise LocalRagError(f"Unsupported file extension: {extension}")


class LocalRagStore:
    def __init__(self, config: LocalRagConfig) -> None:
        self.config = config
        self._lock = RLock()
        self._closed = False
        self._connection: sqlite3.Connection | None = None
        self._project_root = Path.cwd().resolve()
        self._roots = tuple(self._resolve_configured_root(root) for root in config.roots)

        if not config.enabled:
            return

        database = config.database.expanduser()
        if not database.is_absolute():
            database = self._project_root / database
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        self._connection = connection
        self._initialize_schema()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def _resolve_configured_root(self, root: Path) -> Path:
        expanded = root.expanduser()
        if not expanded.is_absolute():
            expanded = self._project_root / expanded
        return expanded.resolve(strict=False)

    def _require_connection(self) -> sqlite3.Connection:
        if not self.config.enabled:
            raise RuntimeError("Local RAG is disabled.")
        if self._closed or self._connection is None:
            raise RuntimeError("Local RAG store is closed.")
        return self._connection

    def _initialize_schema(self) -> None:
        connection = self._require_connection()
        with self._lock, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    path TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(collection, path)
                );

                CREATE INDEX IF NOT EXISTS idx_rag_documents_collection
                ON rag_documents(collection, path);

                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
                    collection TEXT NOT NULL,
                    path TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    page INTEGER,
                    token_json TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(document_id, chunk_index)
                );

                CREATE INDEX IF NOT EXISTS idx_rag_chunks_collection
                ON rag_chunks(collection, extension, path);
                """
            )

    def _resolve_allowed_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self._project_root / path
        resolved = path.resolve(strict=False)
        if not any(_is_relative_to(resolved, root) for root in self._roots):
            roots = ", ".join(str(root) for root in self._roots)
            raise LocalRagError(
                f"Path is outside configured Local RAG roots: {resolved}. Allowed roots: {roots}"
            )
        return resolved

    def _iter_candidates(self, requested: Path) -> Iterator[Path]:
        if requested.is_symlink():
            return
        if requested.is_file():
            yield requested
            return
        if not requested.exists():
            return
        if not requested.is_dir():
            return

        for path in requested.rglob("*"):
            try:
                if path.is_symlink() or not path.is_file():
                    continue
            except OSError:
                continue
            relative = path.relative_to(requested)
            if _is_excluded_path(relative):
                continue
            yield path

    def _safe_candidate(self, path: Path) -> tuple[bool, str]:
        if _is_excluded_path(path):
            return False, "excluded_directory"
        if _looks_sensitive(path):
            return False, "sensitive_filename"
        if path.suffix.casefold() not in _SUPPORTED_EXTENSIONS:
            return False, "unsupported_extension"
        try:
            stat = path.stat()
        except OSError:
            return False, "stat_failed"
        if stat.st_size > self.config.max_file_bytes:
            return False, "file_too_large"
        return True, "allowed"

    @staticmethod
    def _digest(path: Path) -> str:
        hasher = sha256()
        with path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                hasher.update(block)
        return hasher.hexdigest()

    def _document_row(self, collection: str, path: str) -> sqlite3.Row | None:
        return self._require_connection().execute(
            "SELECT * FROM rag_documents WHERE collection = ? AND path = ?",
            (collection, path),
        ).fetchone()

    def _counts(self) -> tuple[int, int]:
        connection = self._require_connection()
        documents = int(connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0])
        chunks = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
        return documents, chunks

    def _replace_document(
        self,
        *,
        collection: str,
        path: Path,
        sections: list[ExtractedSection],
        size_bytes: int,
        mtime_ns: int,
        digest: str,
    ) -> tuple[int, int]:
        connection = self._require_connection()
        path_string = str(path)
        extension = path.suffix.casefold()
        timestamp = _utc_iso()
        existing = self._document_row(collection, path_string)
        current_documents, current_chunks = self._counts()
        replacing_chunks = int(existing["chunk_count"]) if existing is not None else 0

        if existing is None and current_documents >= self.config.max_files:
            raise LocalRagError("Local RAG file limit reached.")
        projected_chunks = current_chunks - replacing_chunks + len(sections)
        if projected_chunks > self.config.max_chunks:
            raise LocalRagError("Local RAG chunk limit reached.")

        with self._lock, connection:
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO rag_documents (
                        collection, path, extension, size_bytes, mtime_ns,
                        sha256, chunk_count, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        collection,
                        path_string,
                        extension,
                        size_bytes,
                        mtime_ns,
                        digest,
                        len(sections),
                        timestamp,
                    ),
                )
                document_id = int(cursor.lastrowid)
            else:
                document_id = int(existing["id"])
                connection.execute(
                    "DELETE FROM rag_chunks WHERE document_id = ?",
                    (document_id,),
                )
                connection.execute(
                    """
                    UPDATE rag_documents
                    SET extension = ?, size_bytes = ?, mtime_ns = ?, sha256 = ?,
                        chunk_count = ?, indexed_at = ?
                    WHERE id = ?
                    """,
                    (
                        extension,
                        size_bytes,
                        mtime_ns,
                        digest,
                        len(sections),
                        timestamp,
                        document_id,
                    ),
                )

            for chunk_index, section in enumerate(sections):
                token_counter = Counter(_tokens(section.text))
                connection.execute(
                    """
                    INSERT INTO rag_chunks (
                        document_id, collection, path, extension, chunk_index,
                        text, line_start, line_end, page, token_json,
                        token_count, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        collection,
                        path_string,
                        extension,
                        chunk_index,
                        section.text,
                        section.line_start,
                        section.line_end,
                        section.page,
                        json.dumps(token_counter, ensure_ascii=False, separators=(",", ":")),
                        sum(token_counter.values()),
                        timestamp,
                    ),
                )
        return document_id, len(sections)

    def index_paths(
        self,
        *,
        paths: Iterable[str],
        collection: str,
        force: bool,
        prune_missing: bool,
    ) -> dict[str, Any]:
        collection = _normalize_collection(collection)
        requested_paths = [self._resolve_allowed_path(path) for path in paths]
        if not requested_paths:
            raise LocalRagError("At least one path is required.")

        candidates: dict[str, Path] = {}
        skipped_reasons: Counter[str] = Counter()
        for requested in requested_paths:
            for candidate in self._iter_candidates(requested):
                allowed, reason = self._safe_candidate(candidate)
                if not allowed:
                    skipped_reasons[reason] += 1
                    continue
                resolved = candidate.resolve(strict=False)
                if not any(_is_relative_to(resolved, root) for root in self._roots):
                    skipped_reasons["outside_root"] += 1
                    continue
                candidates[str(resolved)] = resolved

        indexed = 0
        updated = 0
        unchanged = 0
        failed: list[dict[str, str]] = []
        chunks_written = 0
        seen_paths: set[str] = set()

        for path_string in sorted(candidates):
            path = candidates[path_string]
            seen_paths.add(path_string)
            try:
                stat = path.stat()
                existing = self._document_row(collection, path_string)
                if (
                    not force
                    and existing is not None
                    and int(existing["size_bytes"]) == stat.st_size
                    and int(existing["mtime_ns"]) == stat.st_mtime_ns
                ):
                    unchanged += 1
                    continue

                digest = self._digest(path)
                if not force and existing is not None and str(existing["sha256"]) == digest:
                    with self._lock, self._require_connection():
                        self._require_connection().execute(
                            "UPDATE rag_documents SET size_bytes = ?, mtime_ns = ? WHERE id = ?",
                            (stat.st_size, stat.st_mtime_ns, int(existing["id"])),
                        )
                    unchanged += 1
                    continue

                sections = _extract_sections(path, self.config)
                sections = [section for section in sections if section.text.strip()]
                combined_text = "\n".join(section.text for section in sections)
                if any(pattern.search(combined_text) for pattern in _SECRET_CONTENT_PATTERNS):
                    skipped_reasons["sensitive_content"] += 1
                    continue
                if not sections:
                    skipped_reasons["empty_text"] += 1
                    continue
                self._replace_document(
                    collection=collection,
                    path=path,
                    sections=sections,
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    digest=digest,
                )
                chunks_written += len(sections)
                if existing is None:
                    indexed += 1
                else:
                    updated += 1
            except Exception as exc:
                failed.append({"path": path_string, "error": str(exc) or type(exc).__name__})

        removed = 0
        removed_paths: list[str] = []
        if prune_missing:
            removed_paths = self._prune_missing_internal(
                collection=collection,
                requested_roots=requested_paths,
                seen_paths=seen_paths,
            )
            removed = len(removed_paths)

        return {
            "collection": collection,
            "requested_paths": [str(path) for path in requested_paths],
            "candidate_files": len(candidates),
            "indexed_files": indexed,
            "updated_files": updated,
            "unchanged_files": unchanged,
            "removed_files": removed,
            "removed_paths": removed_paths,
            "chunks_written": chunks_written,
            "skipped": dict(skipped_reasons),
            "failed_count": len(failed),
            "failures": failed[:50],
            "completed": len(failed) == 0,
        }

    def _prune_missing_internal(
        self,
        *,
        collection: str,
        requested_roots: list[Path],
        seen_paths: set[str],
    ) -> list[str]:
        connection = self._require_connection()
        rows = connection.execute(
            "SELECT id, path FROM rag_documents WHERE collection = ?",
            (collection,),
        ).fetchall()
        to_remove: list[tuple[int, str]] = []
        for row in rows:
            indexed_path = Path(str(row["path"]))
            if not any(_is_relative_to(indexed_path, root) for root in requested_roots):
                continue
            if str(indexed_path) not in seen_paths or not indexed_path.exists():
                to_remove.append((int(row["id"]), str(indexed_path)))

        if to_remove:
            with self._lock, connection:
                connection.executemany(
                    "DELETE FROM rag_documents WHERE id = ?",
                    [(document_id,) for document_id, _ in to_remove],
                )
        return [path for _, path in to_remove]

    def search(
        self,
        *,
        query: str,
        collection: str,
        extension: str,
        limit: int,
    ) -> dict[str, Any]:
        query = " ".join(query.strip().split())
        if not query:
            raise LocalRagError("query must not be empty.")
        collection = _normalize_collection(collection)
        if not 1 <= limit <= 20:
            raise LocalRagError("limit must be between 1 and 20.")
        extension = extension.strip().casefold()
        if extension and extension != "all" and not extension.startswith("."):
            extension = "." + extension

        connection = self._require_connection()
        parameters: list[Any] = [collection]
        extension_clause = ""
        if extension not in {"", "all"}:
            extension_clause = " AND extension = ?"
            parameters.append(extension)
        rows = connection.execute(
            """
            SELECT * FROM rag_chunks
            WHERE collection = ?
            """
            + extension_clause
            + " ORDER BY id",
            tuple(parameters),
        ).fetchall()
        if not rows:
            return {
                "query": query,
                "collection": collection,
                "extension": extension or "all",
                "count": 0,
                "results": [],
                "message": "No indexed chunks match this collection/filter.",
            }

        query_counter = Counter(_tokens(query))
        if not query_counter:
            raise LocalRagError("query must contain searchable letters or numbers.")

        document_frequency: Counter[str] = Counter()
        parsed_rows: list[tuple[sqlite3.Row, Counter[str]]] = []
        total_length = 0
        for row in rows:
            frequencies = Counter(json.loads(str(row["token_json"])))
            parsed_rows.append((row, frequencies))
            document_frequency.update(frequencies.keys())
            total_length += max(1, int(row["token_count"]))

        total_chunks = len(parsed_rows)
        average_length = total_length / total_chunks
        scored: list[tuple[float, sqlite3.Row]] = []
        k1 = 1.5
        b = 0.75
        normalized_query = query.casefold()
        for row, frequencies in parsed_rows:
            chunk_length = max(1, int(row["token_count"]))
            score = 0.0
            for token, query_weight in query_counter.items():
                frequency = frequencies.get(token, 0)
                if frequency <= 0:
                    continue
                df = document_frequency[token]
                idf = math.log(1 + (total_chunks - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (
                    1 - b + b * chunk_length / max(1.0, average_length)
                )
                score += query_weight * idf * (frequency * (k1 + 1) / denominator)

            text_lower = str(row["text"]).casefold()
            path_lower = str(row["path"]).casefold()
            if normalized_query in text_lower:
                score += 4.0
            if normalized_query in path_lower:
                score += 3.0
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda item: (-item[0], str(item[1]["path"]), int(item[1]["chunk_index"])))
        selected = scored[:limit]
        results = [
            self._row_to_chunk(row).as_dict(score=score)
            for score, row in selected
        ]
        return {
            "query": query,
            "collection": collection,
            "extension": extension or "all",
            "count": len(results),
            "results": results,
            "source_citations": [result["citation"] for result in results],
        }

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> RagChunk:
        return RagChunk(
            id=int(row["id"]),
            collection=str(row["collection"]),
            path=str(row["path"]),
            extension=str(row["extension"]),
            text=str(row["text"]),
            line_start=(int(row["line_start"]) if row["line_start"] is not None else None),
            line_end=(int(row["line_end"]) if row["line_end"] is not None else None),
            page=(int(row["page"]) if row["page"] is not None else None),
            chunk_index=int(row["chunk_index"]),
            indexed_at=str(row["indexed_at"]),
        )

    def get_chunk(self, chunk_id: int) -> dict[str, Any]:
        if chunk_id <= 0:
            raise LocalRagError("chunk_id must be positive.")
        row = self._require_connection().execute(
            "SELECT * FROM rag_chunks WHERE id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            raise LocalRagError("RAG chunk was not found.")
        return self._row_to_chunk(row).as_dict()

    def status(self, *, collection: str) -> dict[str, Any]:
        collection = _normalize_collection(collection)
        connection = self._require_connection()
        row = connection.execute(
            """
            SELECT COUNT(*) AS documents, COALESCE(SUM(chunk_count), 0) AS chunks,
                   COALESCE(SUM(size_bytes), 0) AS bytes,
                   MAX(indexed_at) AS last_indexed_at
            FROM rag_documents WHERE collection = ?
            """,
            (collection,),
        ).fetchone()
        extensions = connection.execute(
            """
            SELECT extension, COUNT(*) AS count
            FROM rag_documents WHERE collection = ?
            GROUP BY extension ORDER BY extension
            """,
            (collection,),
        ).fetchall()
        return {
            "enabled": self.enabled,
            "collection": collection,
            "configured_roots": [str(root) for root in self._roots],
            "document_count": int(row["documents"]),
            "chunk_count": int(row["chunks"]),
            "indexed_bytes": int(row["bytes"]),
            "last_indexed_at": row["last_indexed_at"],
            "extensions": {str(item["extension"]): int(item["count"]) for item in extensions},
            "supported_extensions": sorted(_SUPPORTED_EXTENSIONS),
        }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> "LocalRagStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()
