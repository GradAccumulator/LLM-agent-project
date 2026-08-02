from __future__ import annotations

from datetime import datetime, timezone
import unittest

from src.confirmation import (
    ConfirmationCodeError,
    ConfirmationConfig,
    ConfirmationError,
    ConfirmationManager,
    ConfirmationRisk,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class ConfirmationManagerTests(
    unittest.TestCase
):
    def test_standard_action_requires_no_code(self) -> None:
        clock = _Clock()
        manager = ConfirmationManager(
            ConfirmationConfig(
                timeout_seconds=30.0
            ),
            clock=clock,
            now=lambda: datetime(
                2026,
                8,
                2,
                tzinfo=timezone.utc,
            ),
        )
        pending = manager.request(
            tool_name="write",
            arguments={"value": 1},
            summary="값 저장",
            risk=ConfirmationRisk.STANDARD,
        )

        self.assertEqual(
            pending.required_phrase,
            "승인",
        )
        approved = manager.approve()
        self.assertEqual(
            approved.tool_name,
            "write",
        )
        self.assertFalse(
            manager.has_pending()
        )

    def test_high_risk_requires_code(self) -> None:
        manager = ConfirmationManager(
            ConfirmationConfig(
                high_risk_code_digits=4,
                max_code_attempts=2,
            )
        )
        pending = manager.request(
            tool_name="delete",
            arguments={"id": 1},
            summary="항목 삭제",
            risk=ConfirmationRisk.HIGH,
        )

        with self.assertRaises(
            ConfirmationCodeError
        ):
            manager.approve(
                code="0000"
            )

        approved = manager.approve(
            code=pending.approval_code
        )
        self.assertEqual(
            approved.action_id,
            pending.action_id,
        )

    def test_expiration_removes_action(self) -> None:
        clock = _Clock()
        manager = ConfirmationManager(
            ConfirmationConfig(
                timeout_seconds=10.0
            ),
            clock=clock,
        )
        manager.request(
            tool_name="write",
            arguments={},
            summary="저장",
            risk=ConfirmationRisk.STANDARD,
        )
        clock.value += 11.0

        self.assertFalse(
            manager.has_pending()
        )
        with self.assertRaises(
            ConfirmationError
        ):
            manager.approve()


if __name__ == "__main__":
    unittest.main()
