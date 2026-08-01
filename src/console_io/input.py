from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Queue
import signal
import sys
from threading import Event, Lock, Thread
from time import monotonic
from typing import TextIO


InputFunction = Callable[[str], str]
SubmitCallback = Callable[[str], None]
KeyReader = Callable[[], str]


class ConsoleTextInput:
    """Background line input with per-key activity tracking on Windows."""

    def __init__(
        self,
        *,
        prompt: str = "YOU> ",
        input_function: InputFunction = input,
        output: TextIO | None = None,
        use_windows_key_reader: bool | None = None,
        key_reader: KeyReader | None = None,
    ) -> None:
        self.prompt = prompt
        self._input_function = input_function
        self._output = output or sys.stdout
        self._queue: Queue[str] = Queue()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._activity_lock = Lock()
        self._on_submit: SubmitCallback | None = None
        self._closed = False
        self._activity_sequence = 0
        self._last_activity_monotonic: float | None = None
        self._line_has_text = False

        if use_windows_key_reader is None:
            use_windows_key_reader = (
                sys.platform == "win32"
                and input_function is input
                and bool(
                    getattr(
                        sys.stdin,
                        "isatty",
                        lambda: False,
                    )()
                )
            )
        self._use_windows_key_reader = (
            use_windows_key_reader
        )
        self._key_reader = key_reader

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(
            thread is not None
            and thread.is_alive()
        )

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def activity_sequence(self) -> int:
        """Monotonic edit counter used to reset input inactivity timers."""

        with self._activity_lock:
            return self._activity_sequence

    @property
    def line_has_text(self) -> bool:
        with self._activity_lock:
            return self._line_has_text

    @property
    def seconds_since_activity(self) -> float | None:
        with self._activity_lock:
            timestamp = self._last_activity_monotonic
        if timestamp is None:
            return None
        return max(0.0, monotonic() - timestamp)

    def _record_activity(
        self,
        *,
        line_has_text: bool,
    ) -> None:
        with self._activity_lock:
            self._activity_sequence += 1
            self._last_activity_monotonic = monotonic()
            self._line_has_text = line_has_text

    def _finish_line_activity(self) -> None:
        with self._activity_lock:
            self._line_has_text = False

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

    def _get_windows_character(self) -> str:
        if self._key_reader is not None:
            return self._key_reader()

        import msvcrt

        return msvcrt.getwch()

    def _read_windows_line(self) -> str | None:
        """Small Unicode line editor that records every typed character."""

        self._output.write(self.prompt)
        self._output.flush()
        characters: list[str] = []

        while not self._stop_event.is_set():
            character = self._get_windows_character()

            if character in {"\r", "\n"}:
                self._output.write("\n")
                self._output.flush()
                self._finish_line_activity()
                return "".join(characters)

            if character == "\x03":
                # Normally ENABLE_PROCESSED_INPUT sends Ctrl+C directly
                # to Python. Forward it to the process if it arrives here.
                signal.raise_signal(signal.SIGINT)
                return None

            if character == "\x1a":
                self._output.write("\n")
                self._output.flush()
                self._finish_line_activity()
                return None

            if character in {"\x00", "\xe0"}:
                # Function and navigation keys use a two-character code.
                # Consume the second code without treating it as text.
                self._get_windows_character()
                continue

            if character in {"\b", "\x7f"}:
                if characters:
                    characters.pop()
                    self._output.write("\b \b")
                    self._output.flush()
                    self._record_activity(
                        line_has_text=bool(characters)
                    )
                continue

            if (
                character == "\t"
                or character.isprintable()
            ):
                # The very first printable character is appended and
                # echoed exactly like every later character.
                characters.append(character)
                self._output.write(character)
                self._output.flush()
                self._record_activity(
                    line_has_text=True
                )

        return None

    def _read_line(self) -> str | None:
        if self._use_windows_key_reader:
            return self._read_windows_line()
        return self._input_function(self.prompt)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                value = self._read_line()
            except EOFError:
                break
            except KeyboardInterrupt:
                break
            except Exception as exc:
                print(
                    f"Console input stopped: {exc}",
                    file=self._output,
                )
                break

            if value is None:
                break

            text = value.strip()
            self._finish_line_activity()
            if not text:
                continue

            self._queue.put(text)
            callback = self._on_submit
            if callback is not None:
                try:
                    callback(text)
                except Exception as exc:
                    print(
                        "Console submit callback warning: "
                        f"{exc}",
                        file=self._output,
                    )

    def has_pending(self) -> bool:
        return not self._queue.empty()

    def try_read(self) -> str | None:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def close(
        self,
        timeout: float = 0.05,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop_event.set()
            thread = self._thread
            self._thread = None

        # Console reads cannot always be cancelled safely. The daemon
        # thread exits with the process; join briefly when it already can.
        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(timeout=timeout)

    def __enter__(self) -> ConsoleTextInput:
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        self.close()
