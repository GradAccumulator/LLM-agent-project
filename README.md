# LLM Agent — Step 23.8.1: Strict Tool Schema Hotfix

OpenAI 요청이 다음 400 오류로 중단되던 문제를 수정했습니다.

```text
Invalid schema for function 'edge_cdp_select_tab'
'required' is required to be supplied and to be an array
including every key in properties. Missing 'workflow_ref'.
```

## 원인

프로젝트의 모든 function tool은 `strict = true`로 OpenAI에 전달됩니다.
strict tool의 object schema에서는 `properties`에 있는 모든 키가 같은 object의
`required` 배열에도 들어가야 합니다. 선택적인 값은 required에서 빼는 것이
아니라 `type = ["string", "null"]`처럼 nullable로 표현해야 합니다.

문제가 있던 schema는 다음 형태였습니다.

```json
{
  "properties": {
    "tab_ref": {"type": "string"},
    "workflow_ref": {"type": ["string", "null"]}
  },
  "required": ["tab_ref"]
}
```

`workflow_ref`가 properties에는 있지만 required에는 없어 요청 전체가 HTTP 400으로
거절됐습니다. 실제 질문이 브라우저와 무관해도 모든 tool schema가 먼저 검증되므로
"갤럭시 폴드 8 평가 어때?" 같은 질문도 답변 생성 전에 실패했습니다.

## 수정한 schema

```text
edge_cdp_select_tab
- tab_ref
- workflow_ref

edge_cdp_begin_workflow
- goal
- tab_ref

edge_cdp_verify_workflow
- workflow_ref
- expected_url_contains
- expected_title_contains
- expected_text_contains
- minimum_tab_count
- require_all_steps_verified

edge_cdp_click_element
- element_ref
- workflow_ref

edge_cdp_fill_element
- element_ref
- value
- workflow_ref
```

nullable 필드는 계속 null을 받을 수 있으므로 기능적으로는 선택값처럼 동작합니다.

## 재발 방지

`ToolRegistry.register()`에 strict JSON schema 검증을 추가했습니다.

```text
properties와 required의 키 집합이 다름
→ Jarvis 시작/테스트 단계에서 즉시 ValueError
→ 잘못된 schema가 OpenAI API까지 전달되지 않음
```

중첩 object, array items, anyOf, oneOf, allOf도 재귀적으로 검사합니다.

## 적용

ZIP 내용을 프로젝트에 덮어쓴 뒤 캐시를 삭제합니다.

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m src.main
```

정상이라면 같은 질문에서 `Invalid schema` 오류 없이 THINKING 단계가 진행됩니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

추가 회귀 테스트:

```text
workflow_ref가 required에서 빠진 schema 등록 차단
모든 Edge tool의 properties == required 확인
nullable workflow 인수들이 required에 포함됐는지 확인
```

## 커밋 메시지

```bash
git commit -m "Fix strict schemas for Edge workflow tools"
```
