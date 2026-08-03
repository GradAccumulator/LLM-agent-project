from __future__ import annotations

import json
import unittest

from src.google_calendar import (
    GoogleCalendarConfig,
)
from src.tools.google_calendar_tools import (
    register_google_calendar_tools,
)
from src.tools.registry import (
    ToolRegistry,
)


class _Client:
    enabled = True
    config = GoogleCalendarConfig(
        allow_writes=True
    )

    def __init__(self) -> None:
        self.created = 0
        self.updated = 0
        self.deleted = 0

    def status(self):
        return {
            "authenticated": True,
            "write_ready": True,
        }

    def list_calendars(self, max_results):
        del max_results
        return ()

    def get_event(self, **kwargs):
        return {
            "id": kwargs["event_id"],
            "summary": "대상",
        }

    def list_events(self, **kwargs):
        del kwargs
        return ()

    def find_free_slots(self, **kwargs):
        del kwargs
        return ()

    def create_event(self, **kwargs):
        self.created += 1
        return {
            "created": True,
            "verified": True,
            "event": {
                "id": "new",
                "summary": kwargs["summary"],
            },
        }

    def update_event(self, **kwargs):
        self.updated += 1
        return {
            "updated": True,
            "verified": True,
            "changed_fields": [
                "summary"
            ],
            "event": {
                "id": kwargs["event_id"],
                "summary": kwargs["summary"],
            },
        }

    def delete_event(self, **kwargs):
        self.deleted += 1
        return {
            "deleted": True,
            "deletion_verified": True,
            "deleted_event": {
                "id": kwargs["event_id"],
            },
        }


class CalendarWriteToolTests(
    unittest.TestCase
):
    def _registry(self):
        client = _Client()
        registry = ToolRegistry()
        register_google_calendar_tools(
            registry,
            client,
        )
        return registry, client

    def test_create_waits_for_standard_approval(
        self,
    ) -> None:
        registry, client = self._registry()

        result = registry.execute(
            "google_calendar_create_event",
            json.dumps(
                {
                    "calendar_id": None,
                    "summary": "병원",
                    "start": (
                        "2026-08-03T15:00:00+09:00"
                    ),
                    "end": (
                        "2026-08-03T16:00:00+09:00"
                    ),
                    "all_day": False,
                    "timezone_name": (
                        "Asia/Seoul"
                    ),
                    "description": None,
                    "location": None,
                }
            ),
        )

        self.assertTrue(
            result.confirmation_required
        )
        self.assertEqual(
            client.created,
            0,
        )

        executed = (
            registry
            .approve_pending_confirmation()
        )
        self.assertTrue(executed.success)
        self.assertEqual(
            client.created,
            1,
        )

    def test_update_waits_for_approval(
        self,
    ) -> None:
        registry, client = self._registry()

        result = registry.execute(
            "google_calendar_update_event",
            json.dumps(
                {
                    "calendar_id": None,
                    "event_id": "event1",
                    "event_summary": "병원",
                    "existing_start": (
                        "2026-08-03T15:00:00+09:00"
                    ),
                    "summary": "병원 진료",
                    "start": None,
                    "end": None,
                    "all_day": None,
                    "timezone_name": None,
                    "description": None,
                    "location": None,
                }
            ),
        )

        self.assertTrue(
            result.confirmation_required
        )
        self.assertEqual(
            client.updated,
            0,
        )
        registry.approve_pending_confirmation()
        self.assertEqual(
            client.updated,
            1,
        )

    def test_delete_requires_numeric_code(
        self,
    ) -> None:
        registry, client = self._registry()

        result = registry.execute(
            "google_calendar_delete_event",
            json.dumps(
                {
                    "calendar_id": None,
                    "event_id": "event1",
                    "event_summary": "병원",
                    "event_start": (
                        "2026-08-03T15:00:00+09:00"
                    ),
                }
            ),
        )

        self.assertTrue(
            result.confirmation_required
        )
        pending = (
            registry.pending_confirmation()
        )
        self.assertIsNotNone(pending)
        phrase = str(
            pending["required_phrase"]
        )
        self.assertRegex(
            phrase,
            r"^승인 \d{4}$",
        )

        wrong = (
            registry
            .approve_pending_confirmation()
        )
        self.assertFalse(wrong.success)
        self.assertEqual(
            client.deleted,
            0,
        )

        code = phrase.split()[-1]
        executed = (
            registry
            .approve_pending_confirmation(
                code=code
            )
        )
        self.assertTrue(executed.success)
        self.assertEqual(
            client.deleted,
            1,
        )

    def test_write_tools_can_be_disabled(
        self,
    ) -> None:
        client = _Client()
        client.config = (
            GoogleCalendarConfig(
                allow_writes=False
            )
        )
        registry = ToolRegistry()
        register_google_calendar_tools(
            registry,
            client,
        )

        self.assertNotIn(
            "google_calendar_create_event",
            registry.names,
        )
        self.assertIn(
            "google_calendar_list_events",
            registry.names,
        )


if __name__ == "__main__":
    unittest.main()
