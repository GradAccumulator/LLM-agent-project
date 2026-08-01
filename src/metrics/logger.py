from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from src.core import StateTransition


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    enabled: bool = True
    directory: Path = Path("logs")
    include_text: bool = False
    flush_each_event: bool = True


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="milliseconds")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable."
    )


class JsonlMetricsLogger:
    def __init__(self, config: MetricsConfig) -> None:
        self.config = config
        self.session_id = uuid4().hex
        self._lock = RLock()
        self._closed = False
        self._file = None
        self.path: Path | None = None

        if not config.enabled:
            return

        config.directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        self.path = (
            config.directory
            / f"session_{timestamp}_"
              f"{self.session_id[:8]}.jsonl"
        )
        try:
            self._file = self.path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            )
        except OSError as exc:
            raise RuntimeError(
                f"Could not open metrics log "
                f"{self.path}: {exc}"
            ) from exc

        self.log(
            "session_started",
            data={"include_text": config.include_text},
        )

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def log(
        self,
        event_type: str,
        *,
        data: Mapping[str, Any] | None = None,
        private: Mapping[str, Any] | None = None,
    ) -> None:
        if not self.config.enabled:
            return

        event_type = event_type.strip()
        if not event_type:
            raise ValueError(
                "event_type must not be empty."
            )

        payload: dict[str, Any] = {
            "timestamp": datetime.now().astimezone(),
            "session_id": self.session_id,
            "event": event_type,
        }
        if data:
            payload.update(data)
        if self.config.include_text and private:
            payload.update(private)

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )

        with self._lock:
            if self._closed or self._file is None:
                return
            self._file.write(encoded + "\n")
            if self.config.flush_each_event:
                self._file.flush()

    def log_state_transition(
        self,
        event: StateTransition,
    ) -> None:
        self.log(
            "state_transition",
            data={
                "previous": event.previous,
                "current": event.current,
                "reason": event.reason,
                "previous_state_seconds": round(
                    event.previous_state_seconds,
                    6,
                ),
                "occurred_at": event.occurred_at,
            },
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

        self.log("session_stopped")

        with self._lock:
            self._closed = True
            if self._file is not None:
                self._file.flush()
                self._file.close()
                self._file = None

    def __enter__(self) -> JsonlMetricsLogger:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
