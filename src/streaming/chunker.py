from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class SentenceChunkerConfig:
    minimum_characters: int = 24
    maximum_characters: int = 160

    def __post_init__(self) -> None:
        if self.minimum_characters <= 0:
            raise ValueError(
                "minimum_characters must be positive."
            )
        if self.maximum_characters <= 0:
            raise ValueError(
                "maximum_characters must be positive."
            )
        if (
            self.minimum_characters
            > self.maximum_characters
        ):
            raise ValueError(
                "minimum_characters must not exceed "
                "maximum_characters."
            )


class IncrementalSentenceChunker:
    """Turns token deltas into speakable sentence-sized chunks."""

    _BOUNDARY_PATTERN = re.compile(
        r"[.!?。！？](?:[\"'”’)\]]*)"
        r"(?=\s|[가-힣A-Z0-9\"“\'‘])"
    )

    def __init__(
        self,
        config: SentenceChunkerConfig,
    ) -> None:
        self.config = config
        self._buffer = ""

    @property
    def pending_text(self) -> str:
        return self._buffer

    def reset(self) -> None:
        self._buffer = ""

    def feed(self, delta: str) -> tuple[str, ...]:
        if not delta:
            return ()

        self._buffer += delta
        chunks: list[str] = []

        while True:
            chunk = self._take_sentence()
            if chunk is None:
                chunk = self._take_maximum_length()
            if chunk is None:
                break
            chunks.append(chunk)

        return tuple(chunks)

    def flush(self) -> tuple[str, ...]:
        text = self._buffer.strip()
        self._buffer = ""
        return (text,) if text else ()

    def _take_sentence(self) -> str | None:
        for match in self._BOUNDARY_PATTERN.finditer(
            self._buffer
        ):
            end = match.end()
            candidate = self._buffer[:end].strip()
            if (
                len(candidate)
                < self.config.minimum_characters
            ):
                continue

            self._buffer = self._buffer[end:].lstrip()
            return candidate
        return None

    def _take_maximum_length(self) -> str | None:
        limit = self.config.maximum_characters
        if len(self._buffer) < limit:
            return None

        split_at = max(
            self._buffer.rfind(" ", 0, limit + 1),
            self._buffer.rfind(",", 0, limit + 1),
            self._buffer.rfind("，", 0, limit + 1),
        )
        if (
            split_at
            < self.config.minimum_characters
        ):
            split_at = limit

        candidate = self._buffer[:split_at].strip()
        self._buffer = self._buffer[split_at:].lstrip()
        return candidate or None
