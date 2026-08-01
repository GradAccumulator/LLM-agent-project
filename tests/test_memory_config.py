from __future__ import annotations

import unittest

from src.app.cli import parse_args


class MemoryConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args, _ = parse_args(
            ['--print-config']
        )
        self.assertTrue(
            args.long_term_memory_enabled
        )
        self.assertEqual(
            args.memory_context_limit,
            20,
        )
        self.assertEqual(
            args.memory_max_entries,
            200,
        )

    def test_can_disable(self) -> None:
        args, _ = parse_args(
            [
                '--print-config',
                '--disable-long-term-memory',
            ]
        )
        self.assertFalse(
            args.long_term_memory_enabled
        )


if __name__ == '__main__':
    unittest.main()
