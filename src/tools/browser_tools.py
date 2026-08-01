from __future__ import annotations

from src.browser import BrowserController

from .registry import ToolRegistry, ToolSpec


def _empty_parameters() -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def register_browser_tools(
    registry: ToolRegistry,
    controller: BrowserController,
) -> None:
    registry.register(
        ToolSpec(
            name="browser_open_page",
            description=(
                "설정에서 선택한 Playwright 브라우저에서 http 또는 https 페이지를 연다. "
                "사용자가 웹페이지 조작을 요청한 경우에 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "maxLength": 2048,
                    }
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            handler=controller.open_page,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_get_page_info",
            description=(
                "현재 자동화 브라우저 페이지의 URL과 제목을 읽고, 필요한 경우 "
                "페이지 본문 텍스트도 제한된 길이로 읽는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "include_text": {
                        "type": "boolean",
                    }
                },
                "required": ["include_text"],
                "additionalProperties": False,
            },
            handler=controller.get_page_info,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_list_elements",
            description=(
                "현재 페이지의 보이는 링크, 버튼 또는 입력창 이름을 "
                "조회한다. 클릭이나 입력 전에 대상을 찾을 때 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "link", "button", "textbox"],
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["kind", "limit"],
                "additionalProperties": False,
            },
            handler=controller.list_elements,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_click_text",
            description=(
                "현재 페이지에서 보이는 저위험 링크나 버튼 텍스트를 "
                "클릭한다. 결제, 구매, 송금, 삭제, 메시지 전송 등 "
                "중요한 동작은 이 도구에서 차단된다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "maxLength": 200,
                    },
                    "exact": {
                        "type": "boolean",
                    },
                },
                "required": ["text", "exact"],
                "additionalProperties": False,
            },
            handler=controller.click_text,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_fill_field",
            description=(
                "label 또는 placeholder로 찾은 일반 텍스트 입력창을 "
                "채운다. 비밀번호, 결제, 신원 및 계좌 필드는 차단된다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["label", "placeholder"],
                    },
                    "name": {
                        "type": "string",
                        "maxLength": 200,
                    },
                    "value": {
                        "type": "string",
                        "maxLength": 1000,
                    },
                },
                "required": ["method", "name", "value"],
                "additionalProperties": False,
            },
            handler=controller.fill_field,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_press_key",
            description=(
                "현재 자동화 브라우저 페이지에 Enter, Escape, Tab, 방향키 등 "
                "허용된 탐색 키 하나를 보낸다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": [
                            "Enter",
                            "Escape",
                            "Tab",
                            "ArrowUp",
                            "ArrowDown",
                            "ArrowLeft",
                            "ArrowRight",
                            "PageUp",
                            "PageDown",
                            "Home",
                            "End",
                        ],
                    }
                },
                "required": ["key"],
                "additionalProperties": False,
            },
            handler=controller.press_key,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_go_back",
            description="현재 자동화 브라우저 페이지에서 한 단계 뒤로 이동한다.",
            parameters=_empty_parameters(),
            handler=controller.go_back,
        )
    )
    registry.register(
        ToolSpec(
            name="browser_close",
            description="Playwright가 관리하는 선택된 브라우저 창을 닫는다.",
            parameters=_empty_parameters(),
            handler=controller.close,
        )
    )

    registry.register_closer(controller.close)
