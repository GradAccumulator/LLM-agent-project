from __future__ import annotations

import unittest

from src.model_routing import (
    ModelTier,
    detect_explicit_model_request,
)


class ModelRoutingDetectionTests(unittest.TestCase):
    def test_strong_model_requests(self) -> None:
        for text in (
            "이번 건 강한 모델로 판단해줘",
            "GPT-5 pro로 분석해줘",
            "상위 모델로 검토해줘",
            "이건 더 깊게 생각해줘",
        ):
            with self.subTest(text=text):
                result = detect_explicit_model_request(text)
                self.assertIsNotNone(result)
                self.assertEqual(result.tier, ModelTier.STRONG)

    def test_balanced_request(self) -> None:
        result = detect_explicit_model_request(
            "이번 부분은 균형 모델로 검토해줘"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.tier, ModelTier.BALANCED)

    def test_model_question_is_not_override(self) -> None:
        self.assertIsNone(
            detect_explicit_model_request(
                "강한 모델이 뭐야?"
            )
        )
        self.assertIsNone(
            detect_explicit_model_request(
                "GPT-5 pro 가격이 뭐야?"
            )
        )


if __name__ == "__main__":
    unittest.main()
