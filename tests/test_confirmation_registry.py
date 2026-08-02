from __future__ import annotations

import json
import unittest

from src.confirmation import (
    ConfirmationConfig,
    ConfirmationRequirement,
    ConfirmationRisk,
)
from src.tools import (
    ToolRegistry,
    ToolSpec,
)


class ConfirmationRegistryTests(
    unittest.TestCase
):
    def _registry(
        self,
        calls: list[str],
    ) -> ToolRegistry:
        registry = ToolRegistry(
            confirmation_config=(
                ConfirmationConfig(
                    timeout_seconds=30.0
                )
            )
        )
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
                    or {
                        "message": (
                            f"{value} 저장 완료"
                        )
                    }
                ),
                confirmation=(
                    ConfirmationRequirement(
                        summary=lambda arguments: (
                            f"{arguments['value']} 저장"
                        ),
                        risk=(
                            ConfirmationRisk
                            .STANDARD
                        ),
                    )
                ),
            )
        )
        return registry

    def test_handler_runs_only_after_approval(
        self,
    ) -> None:
        calls: list[str] = []
        registry = self._registry(calls)

        pending = registry.execute(
            "protected_write",
            json.dumps(
                {"value": "hello"}
            ),
        )

        self.assertTrue(
            pending.confirmation_required
        )
        self.assertEqual(calls, [])
        self.assertIsNotNone(
            registry.pending_confirmation()
        )

        executed = (
            registry
            .approve_pending_confirmation()
        )
        self.assertTrue(executed.success)
        self.assertEqual(
            calls,
            ["hello"],
        )
        self.assertIsNone(
            registry.pending_confirmation()
        )

    def test_cancel_never_calls_handler(
        self,
    ) -> None:
        calls: list[str] = []
        registry = self._registry(calls)
        registry.execute(
            "protected_write",
            '{"value":"hello"}',
        )

        cancelled = (
            registry
            .cancel_pending_confirmation()
        )

        self.assertTrue(cancelled.success)
        self.assertEqual(calls, [])
        self.assertIsNone(
            registry.pending_confirmation()
        )

    def test_disabled_gate_executes_directly(
        self,
    ) -> None:
        calls: list[str] = []
        registry = ToolRegistry(
            confirmation_config=(
                ConfirmationConfig(
                    enabled=False
                )
            )
        )
        registry.register(
            ToolSpec(
                name="protected_write",
                description="test",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=lambda: (
                    calls.append("called")
                    or {"message": "done"}
                ),
                confirmation=(
                    ConfirmationRequirement(
                        summary=lambda _: "저장"
                    )
                ),
            )
        )

        result = registry.execute(
            "protected_write",
            "{}",
        )

        self.assertTrue(result.success)
        self.assertFalse(
            result.confirmation_required
        )
        self.assertEqual(
            calls,
            ["called"],
        )


if __name__ == "__main__":
    unittest.main()
