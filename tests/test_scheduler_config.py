from __future__ import annotations

import unittest
from src.app.cli import parse_args


class SchedulerConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args, _ = parse_args(['--print-config'])
        self.assertTrue(args.scheduler_enabled)
        self.assertEqual(args.scheduler_database.name, 'jarvis_tasks.db')
        self.assertEqual(args.scheduler_poll_interval, 0.5)
        self.assertTrue(args.scheduler_announce_tts)


if __name__ == '__main__':
    unittest.main()
