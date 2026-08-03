from __future__ import annotations

from src.confirmation import (
    ConfirmationRequirement,
    ConfirmationRisk,
)
from src.edge_cdp import (
    EdgeCdpController,
    EdgeWorkflowCoordinator,
)

from .registry import (
    ToolRegistry,
    ToolSpec,
)


def register_edge_cdp_tools(
    registry: ToolRegistry,
    controller: EdgeCdpController,
) -> None:
    workflow = EdgeWorkflowCoordinator(
        controller
    )
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

    managed_status = getattr(
        controller,
        "managed_edge_status",
        None,
    )
    managed_start = getattr(
        controller,
        "start_managed_edge",
        None,
    )
    if (
        callable(managed_status)
        and callable(managed_start)
    ):
        registry.register(
            ToolSpec(
                name="edge_cdp_managed_status",
                description=(
                    "Jarvis 전용 Edge 프로필, 실행 파일, "
                    "자동 시작 및 CDP 준비 상태를 확인한다."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=managed_status,
            )
        )

        registry.register(
            ToolSpec(
                name="edge_cdp_start_managed",
                description=(
                    "Jarvis 전용 Edge 프로필을 remote debugging "
                    "활성 상태로 시작한다. 이미 실행 중이면 재사용한다."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=managed_start,
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
            handler=workflow.list_tabs,
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
                    },
                    "workflow_ref": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
                "required": [
                    "tab_ref",
                ],
                "additionalProperties": False,
            },
            handler=workflow.select_tab,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_find_tabs",
            description=(
                "열린 Edge 탭의 제목과 URL에서 query를 검색해 "
                "일치 점수와 tab_ref를 반환한다. 여러 탭 중 정확한 "
                "작업 대상을 찾을 때 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": [
                    "query",
                    "limit",
                ],
                "additionalProperties": False,
            },
            handler=workflow.find_tabs,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_begin_workflow",
            description=(
                "여러 탭·여러 페이지에 걸친 Edge 작업을 시작하고 "
                "workflow_ref와 기준 상태를 저장한다. 다단계 브라우저 "
                "작업에서는 행동 전에 한 번 호출한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                    "tab_ref": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
                "required": [
                    "goal",
                ],
                "additionalProperties": False,
            },
            handler=workflow.begin_workflow,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_get_workflow",
            description=(
                "Edge 다단계 작업의 목표, 기준 상태, 실행 단계, "
                "복구 여부와 검증 결과를 읽는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "workflow_ref": {
                        "type": "string",
                    },
                },
                "required": [
                    "workflow_ref",
                ],
                "additionalProperties": False,
            },
            handler=workflow.get_workflow,
        )
    )

    registry.register(
        ToolSpec(
            name="edge_cdp_verify_workflow",
            description=(
                "Edge 다단계 작업의 모든 행동이 검증됐는지 확인하고 "
                "현재 탭의 URL·제목·본문 및 탭 수 조건을 함께 검사한다. "
                "최종 답변 전에 호출하며 verified=false이면 완료로 말하지 않는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "workflow_ref": {
                        "type": "string",
                    },
                    "expected_url_contains": {
                        "type": "string",
                    },
                    "expected_title_contains": {
                        "type": "string",
                    },
                    "expected_text_contains": {
                        "type": "string",
                    },
                    "minimum_tab_count": {
                        "type": [
                            "integer",
                            "null",
                        ],
                        "minimum": 0,
                        "maximum": 200,
                    },
                    "require_all_steps_verified": {
                        "type": "boolean",
                    },
                },
                "required": [
                    "workflow_ref",
                ],
                "additionalProperties": False,
            },
            handler=workflow.verify_workflow,
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
            handler=workflow.get_page_info,
        )
    )

    list_elements = workflow.list_elements
    get_element = workflow.get_element
    find_element = workflow.find_element
    click_element = workflow.click_element
    fill_element = workflow.fill_element
    dom_capable = callable(list_elements) and callable(get_element)
    dom_actions_allowed = bool(
        getattr(controller, "allow_dom_actions", False)
    )
    if dom_capable:
        registry.register(
            ToolSpec(
                name="edge_cdp_list_elements",
                description=(
                    "선택한 Edge 탭에서 보이는 링크·버튼·텍스트 입력창을 읽고 "
                    "짧게 유효한 element_ref와 안전 분류를 반환한다. 요소 조작 "
                    "전에는 반드시 이 도구로 정확한 대상을 확인한다."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tab_ref": {
                            "type": ["string", "null"],
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["all", "link", "button", "textbox"],
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "required": ["tab_ref", "kind", "limit"],
                    "additionalProperties": False,
                },
                handler=list_elements,
            )
        )

        registry.register(
            ToolSpec(
                name="edge_cdp_get_element",
                description=(
                    "edge_cdp_list_elements에서 받은 element_ref가 여전히 같은 "
                    "DOM 요소인지 확인하고 현재 안전 분류를 다시 읽는다."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "element_ref": {"type": "string"},
                    },
                    "required": ["element_ref"],
                    "additionalProperties": False,
                },
                handler=get_element,
            )
        )

        registry.register(
            ToolSpec(
                name="edge_cdp_find_element",
                description=(
                    "현재 Edge 페이지의 보이는 요소를 label·placeholder·href로 "
                    "검색하고 일치 점수를 반환한다. unique_best=true인 경우에만 "
                    "자동 대상 선택에 사용하며 safety는 실행 직전에 재검사된다."
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
                        "kind": {
                            "type": "string",
                            "enum": [
                                "all",
                                "link",
                                "button",
                                "textbox",
                            ],
                        },
                        "query": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "required": [
                        "tab_ref",
                        "kind",
                        "query",
                        "limit",
                    ],
                    "additionalProperties": False,
                },
                handler=find_element,
            )
        )

        if dom_actions_allowed and callable(click_element) and callable(fill_element):
            registry.register(
                ToolSpec(
                    name="edge_cdp_click_element",
                    description=(
                        "safety.allowed=true인 저위험 Edge 링크나 버튼을 정확한 "
                        "element_ref로 클릭하고 URL·제목·상태·새 탭 변화를 검증한다. "
                        "로그인, 제출, 전송, 구매, 결제, 삭제 요소는 차단된다."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "element_ref": {
                                "type": "string",
                            },
                            "workflow_ref": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                        },
                        "required": [
                            "element_ref",
                        ],
                        "additionalProperties": False,
                    },
                    handler=click_element,
                )
            )

            registry.register(
                ToolSpec(
                    name="edge_cdp_fill_element",
                    description=(
                        "safety.allowed=true인 일반 Edge 텍스트 입력창에 초안만 "
                        "입력하고 실제 값을 검증한다. 비밀번호·인증·결제·신원·계좌·"
                        "로그인 필드는 차단하며 제출이나 전송은 하지 않는다."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "element_ref": {"type": "string"},
                            "value": {
                                "type": "string",
                                "maxLength": 2000,
                            },
                            "workflow_ref": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                        },
                        "required": [
                            "element_ref",
                            "value",
                        ],
                        "additionalProperties": False,
                    },
                    handler=fill_element,
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
