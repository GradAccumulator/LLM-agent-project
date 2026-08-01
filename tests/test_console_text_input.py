from __future__ import annotations

from io import StringIO
from threading import Event
import time
import unittest

from src.console_io import ConsoleTextInput


class ConsoleTextInputTests(unittest.TestCase):
    def test_first_character_is_preserved(self) -> None:
        values = iter(["안녕"])
        submitted = Event()

        def fake_input(prompt: str) -> str:
            del prompt
            try:
                return next(values)
            except StopIteration as exc:
                raise EOFError from exc

        console = ConsoleTextInput(
            input_function=fake_input,
            output=StringIO(),
        )
        console.start(
            on_submit=lambda text: submitted.set()
        )
        try:
            self.assertTrue(
                submitted.wait(timeout=1.0)
            )
            self.assertEqual(
                console.try_read(),
                "안녕",
            )
        finally:
            console.close()

    def test_blank_lines_are_ignored(self) -> None:
        values = iter(["   "])

        def fake_input(prompt: str) -> str:
            del prompt
            try:
                return next(values)
            except StopIteration as exc:
                raise EOFError from exc

        console = ConsoleTextInput(
            input_function=fake_input,
            output=StringIO(),
        )
        console.start()
        try:
            deadline = time.monotonic() + 0.5
            while console.running and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNone(console.try_read())
        finally:
            console.close()


if __name__ == "__main__":
    unittest.main()
