from __future__ import annotations

import unittest

from src.conversation import ConversationConfig, ConversationSession


class ConversationSessionTests(unittest.TestCase):
    def test_session_turn_limit(self) -> None:
        session = ConversationSession(
            ConversationConfig(enabled=True, followup_timeout_seconds=12.0, max_turns=2)
        )
        self.assertTrue(session.start())
        self.assertTrue(session.can_accept_followup)
        self.assertEqual(session.complete_turn(), 1)
        self.assertTrue(session.can_accept_followup)
        self.assertEqual(session.complete_turn(), 2)
        self.assertFalse(session.can_accept_followup)

    def test_disabled_mode_never_accepts_followup(self) -> None:
        session = ConversationSession(ConversationConfig(enabled=False))
        session.start()
        session.complete_turn()
        self.assertFalse(session.can_accept_followup)

    def test_end_returns_snapshot_and_resets(self) -> None:
        session = ConversationSession(ConversationConfig())
        session.start()
        session.complete_turn()
        snapshot = session.end()
        self.assertEqual(snapshot.turn_count, 1)
        self.assertFalse(session.active)
        self.assertEqual(session.turn_count, 0)


if __name__ == '__main__':
    unittest.main()
