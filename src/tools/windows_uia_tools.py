from __future__ import annotations

from src.confirmation import (
    ConfirmationRequirement,
    ConfirmationRisk,
)
from src.windows_uia import WindowsUiAutomation

from .registry import ToolRegistry, ToolSpec


def register_windows_uia_tools(
    registry: ToolRegistry,
    controller: WindowsUiAutomation,
) -> None:
    registry.register(ToolSpec(
        name="uia_find_windows",
        description=(
            "Windows UI Automation으로 열린 최상위 창을 제목과 프로세스 이름으로 "
            "검색한다. UI 요소를 찾기 전에 정확한 window_id를 얻을 때 사용한다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title_contains": {"type": "string"},
                "process_contains": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["title_contains", "process_contains", "limit"],
            "additionalProperties": False,
        },
        handler=controller.find_windows,
    ))

    registry.register(ToolSpec(
        name="uia_inspect_window",
        description=(
            "정확한 window_id 아래의 UI Automation 요소 트리를 읽는다. "
            "각 요소에 짧게 유효한 element_ref가 부여된다. 버튼을 누르거나 "
            "값을 입력하기 전에 반드시 이 도구나 uia_find_elements로 대상을 확인한다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "window_id": {"type": "integer"},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 12},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "include_offscreen": {"type": "boolean"},
                "include_value": {"type": "boolean"},
            },
            "required": [
                "window_id", "max_depth", "limit", "include_offscreen", "include_value"
            ],
            "additionalProperties": False,
        },
        handler=controller.inspect_window,
    ))

    capture_window_context = getattr(
        controller,
        "capture_window_context",
        None,
    )
    if callable(capture_window_context):
        registry.register(ToolSpec(
            name="uia_capture_window_context",
            description=(
                "정확한 window_id의 화면 이미지와 UI Automation 요소 트리를 "
                "한 번에 캡처한다. 버튼 위치·오류 화면·요소 이름을 교차 확인할 때 "
                "사용하며 결과 이미지는 멀티모달 모델에 첨부된다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window_id": {
                        "type": "integer",
                    },
                    "max_depth": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                    },
                    "include_value": {
                        "type": "boolean",
                    },
                },
                "required": [
                    "window_id",
                    "max_depth",
                    "limit",
                    "include_value",
                ],
                "additionalProperties": False,
            },
            handler=capture_window_context,
        ))

    registry.register(ToolSpec(
        name="uia_find_elements",
        description=(
            "창 안에서 이름, automation_id, control_type 조건으로 UI 요소를 찾고 "
            "element_ref를 반환한다. 같은 이름의 후보가 여러 개면 임의로 고르지 않는다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "window_id": {"type": "integer"},
                "name_contains": {"type": "string"},
                "automation_id": {"type": "string"},
                "control_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 20,
                },
                "enabled_only": {"type": "boolean"},
                "visible_only": {"type": "boolean"},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 12},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": [
                "window_id", "name_contains", "automation_id", "control_types",
                "enabled_only", "visible_only", "max_depth", "limit"
            ],
            "additionalProperties": False,
        },
        handler=controller.find_elements,
    ))

    registry.register(ToolSpec(
        name="uia_get_element",
        description=(
            "element_ref가 가리키는 UI 요소의 현재 속성을 다시 읽는다. "
            "ref가 만료되면 창을 다시 검사해야 한다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "element_ref": {"type": "string"},
                "include_value": {"type": "boolean"},
            },
            "required": ["element_ref", "include_value"],
            "additionalProperties": False,
        },
        handler=controller.get_element,
    ))

    if not controller.allow_actions:
        return

    registry.register(ToolSpec(
        name="uia_focus_element",
        description=(
            "검사로 얻은 element_ref의 UI 요소에 키보드 포커스를 준다. "
            "텍스트 입력이나 클릭은 수행하지 않는다."
        ),
        parameters={
            "type": "object",
            "properties": {"element_ref": {"type": "string"}},
            "required": ["element_ref"],
            "additionalProperties": False,
        },
        handler=controller.focus_element,
    ))

    def summary(action: str, arguments: dict) -> str:
        try:
            target = controller.describe_ref(str(arguments.get("element_ref") or ""))
        except Exception:
            target = "선택한 UI 요소"
        return f"{target}에 {action} 수행"

    registry.register(ToolSpec(
        name="uia_invoke_element",
        description=(
            "UI Automation Invoke 패턴을 지원하는 일반 버튼·메뉴를 실행한다. "
            "실행 전 승인이 필요하며 삭제·구매·결제·전송처럼 위험한 이름은 차단된다. "
            "화면 좌표 클릭은 사용하지 않는다."
        ),
        parameters={
            "type": "object",
            "properties": {"element_ref": {"type": "string"}},
            "required": ["element_ref"],
            "additionalProperties": False,
        },
        handler=controller.invoke_element,
        confirmation=ConfirmationRequirement(
            summary=lambda arguments: summary("버튼/메뉴 실행", arguments),
            risk=ConfirmationRisk.STANDARD,
        ),
    ))

    registry.register(ToolSpec(
        name="uia_set_value",
        description=(
            "UI Automation Value 패턴을 지원하는 일반 텍스트 필드 값을 바꾼다. "
            "승인 후 실행되며 비밀번호 필드와 2000자를 넘는 값은 차단한다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "element_ref": {"type": "string"},
                "value": {"type": "string", "maxLength": 2000},
            },
            "required": ["element_ref", "value"],
            "additionalProperties": False,
        },
        handler=controller.set_value,
        confirmation=ConfirmationRequirement(
            summary=lambda arguments: summary(
                f"텍스트 {len(str(arguments.get('value') or ''))}자 입력", arguments
            ),
            risk=ConfirmationRisk.STANDARD,
        ),
    ))

    registry.register(ToolSpec(
        name="uia_toggle_element",
        description=(
            "체크박스나 토글 요소의 상태를 바꾼다. 실행 전 승인이 필요하다."
        ),
        parameters={
            "type": "object",
            "properties": {"element_ref": {"type": "string"}},
            "required": ["element_ref"],
            "additionalProperties": False,
        },
        handler=controller.toggle_element,
        confirmation=ConfirmationRequirement(
            summary=lambda arguments: summary("토글 상태 변경", arguments),
            risk=ConfirmationRisk.STANDARD,
        ),
    ))

    registry.register(ToolSpec(
        name="uia_select_element",
        description=(
            "목록·탭·라디오 항목을 선택한다. 실행 전 승인이 필요하다."
        ),
        parameters={
            "type": "object",
            "properties": {"element_ref": {"type": "string"}},
            "required": ["element_ref"],
            "additionalProperties": False,
        },
        handler=controller.select_element,
        confirmation=ConfirmationRequirement(
            summary=lambda arguments: summary("항목 선택", arguments),
            risk=ConfirmationRisk.STANDARD,
        ),
    ))
