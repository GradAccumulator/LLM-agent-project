from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Queue
import sys
from threading import Event, Lock, Thread
from typing import TextIO


InputFunction = Callable[[str], str]
SubmitCallback = Callable[[str], None]


class ConsoleTextInput:
    """Background line input that never consumes a separate activation key."""

    def __init__(
        self,
        *,
        prompt: str = "YOU> ",
        input_function: InputFunction = input,
        output: TextIO | None = None,
    ) -> None:
        self.prompt = prompt
        self._input_function = input_function
        self._output = output or sys.stdout
        self._queue: Queue[str] = Queue()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._on_submit: SubmitCallback | None = None
        self._closed = False

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    def start(
        self,
        *,
        on_submit: SubmitCallback | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError(
                    "Console text input is closed."
                )
            self._on_submit = on_submit
            if self.running:
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="jarvis-console-input",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                value = self._input_function(self.prompt)
            except EOFError:
                break
            except KeyboardInterrupt:
                # The process-level Ctrl+C handler remains authoritative.
                break
            except Exception as exc:
                print(
                    f"Console input stopped: {exc}",
                    file=self._output,
                )
                break

            text = value.strip()
            if not text:
                continue

            # The full line, including its first character, is queued.
            # No getch/kbhit activation character is consumed separately.
            self._queue.put(text)
            callback = self._on_submit
            if callback is not None:
                try:
                    callback(text)
                except Exception as exc:
                    print(
                        f"Console submit callback warning: {exc}",
                        file=self._output,
                    )

    def has_pending(self) -> bool:
        return not self._queue.empty()

    def try_read(self) -> str | None:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def close(self, timeout: float = 0.05) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        # input() cannot be forcefully cancelled portably. The daemon
        # thread exits with the process; join briefly when it already can.
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def __enter__(self) -> ConsoleTextInput:
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
