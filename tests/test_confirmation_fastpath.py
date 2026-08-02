from __future__ import annotations

import json
import unittest

from src.confirmation import (
    ConfirmationRequirement,
)
from src.fastpath import (
    LocalCommandRouter,
)
from src.tools import (
    ToolRegistry,
    ToolSpec,
)


class ConfirmationFastPathTests(
    unittest.TestCase
):
    def _router(
        self,
        calls: list[str],
    ) -> LocalCommandRouter:
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="protected_write",
                description="test",
                parameters={
                    "type": "object",
                    "properties": {
                        "value": {
                            "type": "string",
                        }
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=lambda value: (
                    calls.append(value)
                    or {"message": "실행했습니다."}
                ),
                confirmation=(
                    ConfirmationRequirement(
                        summary=lambda _: "테스트 저장"
                    )
                ),
            )
        )
        registry.execute(
            "protected_write",
            json.dumps(
                {"value": "hello"}
            ),
        )
        return LocalCommandRouter(
            registry
        )

    def test_exact_approval_executes(
        self,
    ) -> None:
        calls: list[str] = []
        router = self._router(calls)

        result = router.try_execute(
            "승인"
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(
            calls,
            ["hello"],
        )

    def test_ambiguous_yes_is_not_approval(
        self,
    ) -> None:
        calls: list[str] = []
        router = self._router(calls)

        self.assertIsNone(
            router.try_execute("응")
        )
        self.assertEqual(calls, [])

    def test_cancel_discards_action(
        self,
    ) -> None:
        calls: list[str] = []
        router = self._router(calls)

        result = router.try_execute(
            "취소"
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
