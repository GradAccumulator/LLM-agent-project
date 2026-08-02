from __future__ import annotations
import json
import unittest
from src.app.cli import parse_args
from src.google_calendar import (
    READONLY_SCOPE,
    GoogleCalendarClient,
    GoogleCalendarConfig,
    GoogleCalendarError,
)
from src.tools.google_calendar_tools import register_google_calendar_tools
from src.tools.registry import ToolRegistry


class Exec:
    def __init__(self, payload): self.payload = payload
    def execute(self): return self.payload


class Events:
    def __init__(self, payload): self.payload, self.kwargs = payload, None
    def list(self, **kwargs):
        self.kwargs = kwargs
        return Exec(self.payload)


class FreeBusy:
    def __init__(self, payload): self.payload = payload
    def query(self, *, body):
        self.body = body
        return Exec(self.payload)


class Service:
    def __init__(self, events=None, freebusy=None):
        self._events = Events(events or {"items": []})
        self._freebusy = FreeBusy(freebusy or {"calendars": {}})
    def events(self): return self._events
    def freebusy(self): return self._freebusy


class GoogleCalendarTests(unittest.TestCase):
    def test_cli_defaults_and_scope(self):
        args, _ = parse_args(["--print-config"])
        self.assertTrue(args.google_calendar_enabled)
        self.assertEqual(args.google_calendar_default_id, "primary")
        self.assertEqual(
            READONLY_SCOPE,
            "https://www.googleapis.com/auth/calendar.readonly",
        )

    def test_event_mapping(self):
        client = GoogleCalendarClient(GoogleCalendarConfig())
        service = Service(events={"items": [{
            "id": "1",
            "summary": "수업",
            "status": "confirmed",
            "start": {"dateTime": "2026-08-03T10:00:00+09:00"},
            "end": {"dateTime": "2026-08-03T11:00:00+09:00"},
        }]})
        client._service = service
        events = client.list_events(
            time_min="2026-08-03T00:00:00+09:00",
            time_max="2026-08-04T00:00:00+09:00",
        )
        self.assertEqual(events[0]["summary"], "수업")
        self.assertTrue(service._events.kwargs["singleEvents"])

    def test_free_slot_mapping(self):
        client = GoogleCalendarClient(GoogleCalendarConfig())
        client._service = Service(freebusy={"calendars": {
            "primary": {"busy": [{
                "start": "2026-08-03T01:00:00Z",
                "end": "2026-08-03T02:00:00Z",
            }]}
        }})
        slots = client.find_free_slots(
            time_min="2026-08-03T09:00:00+09:00",
            time_max="2026-08-03T13:00:00+09:00",
            duration_minutes=60,
            calendar_ids=["primary"],
            working_hours_start="09:00",
            working_hours_end="13:00",
            max_slots=5,
        )
        self.assertEqual(slots[0]["start"], "2026-08-03T09:00:00+09:00")
        self.assertEqual(slots[1]["start"], "2026-08-03T11:00:00+09:00")

    def test_tool_registration_is_read_only(self):
        class Client:
            enabled = True
            def status(self): return {"authenticated": True}
            def list_calendars(self, n): return ()
            def list_events(self, **kwargs): return ()
            def find_free_slots(self, **kwargs): return ()
        registry = ToolRegistry()
        register_google_calendar_tools(registry, Client())
        self.assertIn("google_calendar_list_events", registry.names)
        self.assertNotIn("google_calendar_create_event", registry.names)
        result = registry.execute("google_calendar_status", "{}")
        self.assertTrue(result.success)

    def test_bad_range(self):
        client = GoogleCalendarClient(GoogleCalendarConfig())
        client._service = Service()
        with self.assertRaises(GoogleCalendarError):
            client.list_events(
                time_min="2026-08-03T12:00:00+09:00",
                time_max="2026-08-03T11:00:00+09:00",
            )


if __name__ == "__main__":
    unittest.main()
