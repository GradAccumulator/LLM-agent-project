from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread

from .store import DueReminder, SchedulerStore


@dataclass(frozen=True, slots=True)
class ReminderSchedulerConfig:
    enabled: bool = True
    poll_interval_seconds: float = 0.5
    claim_limit: int = 20

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError('poll_interval_seconds must be positive.')
        if not 1 <= self.claim_limit <= 100:
            raise ValueError('claim_limit must be between 1 and 100.')


class ReminderScheduler:
    def __init__(self, store: SchedulerStore, config: ReminderSchedulerConfig) -> None:
        self.store = store
        self.config = config
        self._queue: Queue[DueReminder] = Queue()
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self.store.enabled

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(target=self._run, name='jarvis-reminder-scheduler', daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                for reminder in self.store.claim_due(limit=self.config.claim_limit):
                    self._queue.put(reminder)
            except Exception:
                pass
            self._stop.wait(self.config.poll_interval_seconds)

    def drain(self, *, limit: int = 10) -> tuple[DueReminder, ...]:
        if not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100.')
        items: list[DueReminder] = []
        for _ in range(limit):
            try:
                items.append(self._queue.get_nowait())
            except Empty:
                break
        return tuple(items)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def close(self) -> None:
        self.stop()
