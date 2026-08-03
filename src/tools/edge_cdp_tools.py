from __future__ import annotations

from src.confirmation import (
    ConfirmationRequirement,
    ConfirmationRisk,
)
from src.edge_cdp import (
    EdgeCdpController,
)

from .registry import (
    ToolRegistry,
    ToolSpec,
)


def register_edge_cdp_tools(
    registry: ToolRegistry,
    controller: EdgeCdpController,
) -> None:
    registry.register(
        ToolSpec(
            name="edge_cdp_status",
            description=(
                "로컬 Microsoft Edge CDP 연결 상태와 "
                "attach 가능한 탭 수를 확인한다."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=controller.status,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_list_tabs",
            description=(
                "remote debugging이 활성화된 Microsoft Edge의 "
                "열린 탭 목록을 읽고 tab_ref를 반환한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                    }
                },
                "required": ["limit"],
                "additionalProperties": False,
            },
            handler=controller.list_tabs,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_select_tab",
            description=(
                "edge_cdp_list_tabs에서 얻은 tab_ref의 Edge 탭을 "
                "앞으로 가져오고 이후 DOM 조회 대상으로 선택한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tab_ref": {
                        "type": "string",
                    }
                },
                "required": ["tab_ref"],
                "additionalProperties": False,
            },
            handler=controller.select_tab,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_get_page_info",
            description=(
                "선택한 Edge 탭의 제목, URL, DOM 본문 텍스트를 읽는다. "
                "현재 페이지 요약·내용 질문에는 include_text=true를 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tab_ref": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "include_text": {
                        "type": "boolean",
                    },
                },
                "required": [
                    "tab_ref",
                    "include_text",
                ],
                "additionalProperties": False,
            },
            handler=controller.get_page_info,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_capture_tab",
            description=(
                "선택한 Edge 탭을 이미지로 캡처해 멀티모달 분석에 첨부한다. "
                "DOM만으로 화면 상태를 알기 어려울 때 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tab_ref": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "full_page": {
                        "type": "boolean",
                    },
                },
                "required": [
                    "tab_ref",
                    "full_page",
                ],
                "additionalProperties": False,
            },
            handler=controller.capture_tab,
        )
    )

    if not controller.allow_tab_close:
        return

    def close_summary(
        arguments: dict,
    ) -> str:
        try:
            return (
                controller.describe_tab(
                    str(
                        arguments.get(
                            "tab_ref"
                        )
                        or ""
                    )
                )
                + " 닫기"
            )
        except Exception:
            return "선택한 Edge 탭 닫기"

    registry.register(
        ToolSpec(
            name="edge_cdp_close_tab",
            description=(
                "정확한 tab_ref의 Edge 탭을 닫는다. "
                "작성 중인 내용이 사라질 수 있어 실행 전 승인이 필요하다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tab_ref": {
                        "type": "string",
                    }
                },
                "required": ["tab_ref"],
                "additionalProperties": False,
            },
            handler=controller.close_tab,
            confirmation=(
                ConfirmationRequirement(
                    summary=close_summary,
                    risk=(
                        ConfirmationRisk.STANDARD
                    ),
                )
            ),
        )
    )
