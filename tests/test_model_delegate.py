from __future__ import annotations

from types import SimpleNamespace
import unittest

from src.model_routing import (
    ModelRoutingConfig,
    ModelRoutingError,
    SelectiveModelDelegate,
)


class _Responses:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("temporary failure")
        return SimpleNamespace(
            model=kwargs["model"],
            output_text="판단 결과",
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
        )


class _Client:
    def __init__(self, *, fail: bool = False) -> None:
        self.responses = _Responses(fail=fail)


class ModelDelegateTests(unittest.TestCase):
    def test_delegation_has_no_tools_or_memory(self) -> None:
        client = _Client()
        delegate = SelectiveModelDelegate(
            client=client,
            base_model="gpt-5.6-luna",
            config=ModelRoutingConfig(),
        )
        delegate.begin_turn(
            "강한 모델로 판단해줘"
        )

        result = delegate.delegate(
            task="후보를 검토",
            relevant_context="후보 A, 후보 B",
            reason="충돌하는 제약",
            target_tier="balanced",
            output_format="결론과 이유",
        )

        self.assertTrue(result["delegation_succeeded"])
        call = client.responses.calls[0]
        self.assertEqual(call["model"], "gpt-5.6-sol")
        self.assertEqual(
            call["reasoning"], {"effort": "xhigh"}
        )
        self.assertFalse(call["store"])
        self.assertNotIn("tools", call)
        self.assertNotIn("previous_response_id", call)
        self.assertTrue(delegate.records[0].explicit)

    def test_automatic_delegation_uses_requested_tier(self) -> None:
        client = _Client()
        delegate = SelectiveModelDelegate(
            client=client,
            base_model="gpt-5.6-luna",
            config=ModelRoutingConfig(),
        )
        delegate.begin_turn("코드 구조를 검토해줘")
        result = delegate.delegate(
            task="두 구조 비교",
            relevant_context="A와 B",
            reason="아키텍처 판단",
            target_tier="balanced",
            output_format="추천",
        )
        self.assertEqual(
            result["model"],
            "gpt-5.6-terra",
        )
        self.assertFalse(
            result["explicit_user_request"]
        )

    def test_per_turn_limit(self) -> None:
        delegate = SelectiveModelDelegate(
            client=_Client(),
            base_model="gpt-5.6-luna",
            config=ModelRoutingConfig(
                max_delegations_per_turn=1
            ),
        )
        delegate.begin_turn("검토해줘")
        kwargs = dict(
            task="검토",
            relevant_context="문맥",
            reason="복잡함",
            target_tier="strong",
            output_format="결론",
        )
        delegate.delegate(**kwargs)
        with self.assertRaises(ModelRoutingError):
            delegate.delegate(**kwargs)

    def test_input_context_is_bounded(self) -> None:
        client = _Client()
        delegate = SelectiveModelDelegate(
            client=client,
            base_model="gpt-5.6-luna",
            config=ModelRoutingConfig(
                max_input_characters=1000
            ),
        )
        delegate.begin_turn("검토해줘")
        delegate.delegate(
            task="판단",
            relevant_context="x" * 5000,
            reason="복잡함",
            target_tier="strong",
            output_format="결론",
        )
        content = client.responses.calls[0]["input"][0]["content"]
        self.assertLess(len(content), 1400)

    def test_failure_falls_back(self) -> None:
        delegate = SelectiveModelDelegate(
            client=_Client(fail=True),
            base_model="gpt-5.6-luna",
            config=ModelRoutingConfig(
                fallback_to_default=True
            ),
        )
        delegate.begin_turn("강한 모델로 판단해줘")
        result = delegate.delegate(
            task="검토",
            relevant_context="문맥",
            reason="복잡함",
            target_tier="strong",
            output_format="결론",
        )
        self.assertFalse(result["delegation_succeeded"])
        self.assertTrue(result["fallback_to_default"])
        self.assertFalse(delegate.records[0].success)


if __name__ == "__main__":
    unittest.main()
