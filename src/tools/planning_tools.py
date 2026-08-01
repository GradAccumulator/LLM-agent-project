from __future__ import annotations

from .registry import ToolRegistry, ToolSpec


def _empty_parameters() -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def register_planning_tools(
    registry: ToolRegistry,
) -> None:
    tracker = registry.plan_tracker

    registry.register(
        ToolSpec(
            name="begin_task_plan",
            description=(
                "다단계 컴퓨터 작업을 시작하기 전에 구체적인 실행 "
                "단계 2~6개를 등록한다. 각 단계는 하나의 검증 가능한 "
                "행동 또는 관찰이어야 한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "maxLength": 300,
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "maxLength": 300,
                        },
                        "minItems": 2,
                        "maxItems": 6,
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
                "현재 계획의 진행 상태, 현재 단계와 검증 증거를 "
                "조회한다."
            ),
            parameters=_empty_parameters(),
            handler=tracker.snapshot,
        )
    )

    registry.register(
        ToolSpec(
            name="complete_plan_step",
            description=(
                "현재 단계가 관찰·조회만으로 완료되어 행동 도구의 "
                "자동 검증이 없을 때, 확인한 증거와 함께 완료 처리한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "evidence": {
                        "type": "string",
                        "maxLength": 1000,
                    }
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
                "복구할 수 없는 이유로 현재 계획 단계를 실패 처리한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "maxLength": 1000,
                    }
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
                "모든 단계가 검증 완료된 계획에 최종 요약을 기록한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "maxLength": 1000,
                    }
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
                "사용자 요청 변경이나 안전 제한 때문에 계획 전체를 "
                "중단한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "maxLength": 1000,
                    }
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
            handler=tracker.abandon_plan,
        )
    )
