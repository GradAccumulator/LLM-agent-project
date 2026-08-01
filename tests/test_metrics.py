from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.metrics import (
    JsonlMetricsLogger,
    MetricsConfig,
)


class MetricsTests(unittest.TestCase):
    def test_private_text_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = JsonlMetricsLogger(
                MetricsConfig(
                    directory=Path(directory),
                    include_text=False,
                )
            )
            path = logger.path
            self.assertIsNotNone(path)

            logger.log(
                "test_event",
                data={"duration": 0.25},
                private={
                    "transcript": "비밀 문장"
                },
            )
            logger.close()

            events = [
                json.loads(line)
                for line in path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            event = next(
                item
                for item in events
                if item["event"] == "test_event"
            )
            self.assertEqual(
                event["duration"],
                0.25,
            )
            self.assertNotIn(
                "transcript",
                event,
            )

    def test_private_text_can_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = JsonlMetricsLogger(
                MetricsConfig(
                    directory=Path(directory),
                    include_text=True,
                )
            )
            path = logger.path
            logger.log(
                "test_event",
                private={"transcript": "저장됨"},
            )
            logger.close()

            events = [
                json.loads(line)
                for line in path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            event = next(
                item
                for item in events
                if item["event"] == "test_event"
            )
            self.assertEqual(
                event["transcript"],
                "저장됨",
            )


if __name__ == "__main__":
    unittest.main()
