from __future__ import annotations

from .registry import ToolRegistry, ToolSpec


def _empty_parameters() -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def register_planning_tools(registry: ToolRegistry) -> None:
    tracker = registry.plan_tracker

    registry.register(
        ToolSpec(
            name="begin_task_plan",
            description=(
                "다단계 컴퓨터 작업 전에 검증 가능한 실행 단계 2~설정된 "
                "최대 개수를 등록한다. 각 단계는 하나의 행동 또는 관찰이어야 한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "maxLength": 300},
                    "steps": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 300},
                        "minItems": 2,
                        "maxItems": 10,
                    },
                },
                "required": ["goal", "steps"],
                "additionalProperties": False,
            },
            handler=tracker.begin_plan,
        )
    )

    registry.register(
        ToolSpec(
            name="get_task_plan",
            description=(
                "현재 계획, 현재 단계, 시도 예산, 부분 재계획 기록과 검증 증거를 조회한다."
            ),
            parameters=_empty_parameters(),
            handler=tracker.snapshot,
        )
    )

    registry.register(
        ToolSpec(
            name="get_plan_recovery",
            description=(
                "현재 단계가 repairing일 때 실패 분류, 반복 횟수, 차단된 도구, "
                "권장 전략과 DOM·UIA·Vision 대체 도구를 조회한다."
            ),
            parameters=_empty_parameters(),
            handler=tracker.recovery_report,
        )
    )

    registry.register(
        ToolSpec(
            name="repair_task_plan",
            description=(
                "실패한 현재 단계만 재개하거나 교체한다. 같은 실패가 반복되면 "
                "retry 대신 다른 preferred_tool을 지정한 switch_tool을 사용한다. "
                "완료된 이전 단계와 증거는 보존된다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "maxLength": 1000},
                    "strategy": {
                        "type": "string",
                        "enum": [
                            "retry",
                            "switch_tool",
                            "replace_current",
                            "replace_remaining",
                        ],
                    },
                    "replacement_steps": {
                        "type": ["array", "null"],
                        "items": {"type": "string", "maxLength": 300},
                        "minItems": 1,
                        "maxItems": 10,
                    },
                    "preferred_tool": {"type": ["string", "null"]},
                    "expected_evidence": {"type": ["string", "null"]},
                },
                "required": [
                    "reason",
                    "strategy",
                    "replacement_steps",
                    "preferred_tool",
                    "expected_evidence",
                ],
                "additionalProperties": False,
            },
            handler=tracker.repair_current_step,
        )
    )

    registry.register(
        ToolSpec(
            name="complete_plan_step",
            description=(
                "현재 관찰 단계가 완료됐음을 구체적인 확인 증거와 함께 기록한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "evidence": {"type": "string", "maxLength": 1000},
                },
                "required": ["evidence"],
                "additionalProperties": False,
            },
            handler=tracker.complete_current_step,
        )
    )

    registry.register(
        ToolSpec(
            name="fail_plan_step",
            description=(
                "사용자 개입이 필요하거나 안전·권한·지원 제한으로 복구할 수 없는 "
                "현재 단계를 실패 처리한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "maxLength": 1000},
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
            handler=tracker.fail_current_step,
        )
    )

    registry.register(
        ToolSpec(
            name="finish_task_plan",
            description=(
                "모든 단계가 completed이고 각 단계에 verified=true 증거가 있을 때만 "
                "최종 감사 후 계획을 마무리한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "maxLength": 1000},
                },
                "required": ["summary"],
                "additionalProperties": False,
            },
            handler=tracker.finish_plan,
        )
    )

    registry.register(
        ToolSpec(
            name="abandon_task_plan",
            description=(
                "사용자 요청 변경 또는 전체 작업 중단 요청으로 계획을 폐기한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "maxLength": 1000},
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
            handler=tracker.abandon_plan,
        )
    )
