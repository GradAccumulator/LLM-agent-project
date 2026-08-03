# LLM Agent — Step 23.1–23.4: Computer Agent V2 Foundation

이번 묶음은 다음 네 가지를 함께 구현합니다.

```text
Step 23.1  OpenAI 모델 ID 핫픽스
Step 23.2  Edge DOM element_ref
Step 23.3  안전한 링크·버튼 클릭과 일반 텍스트 초안 입력
Step 23.4  실행 후 URL·제목·요소 상태·입력값 검증
```

## 1. 모델 ID 핫픽스

기존 기본값이었던 아래 ID는 실제 OpenAI API 모델 ID가 아닙니다.

```text
gpt-5.6-luna
gpt-5.6-terra
gpt-5.6-sol
```

새 기본값:

```toml
[llm]
model = "gpt-5.1"
reasoning = "low"

[model_routing]
balanced_model = "gpt-5.1"
balanced_reasoning = "high"
strong_model = "gpt-5-pro"
strong_reasoning = "high"
```

기존 `config/user.toml`에 예전 ID가 남아 있어도 시작 시 메모리에서 자동
변환합니다.

```text
Model migration : gpt-5.6-luna -> gpt-5.1
Model migration : gpt-5.6-terra -> gpt-5.1
Model migration : gpt-5.6-sol -> gpt-5-pro
Model migration : xhigh -> high for gpt-5-pro
```

`gpt-5-pro` 호출 권한이 없는 계정에서는 기존 `fallback_to_default=true`
정책에 따라 위임 실패를 숨기지 않고 기본 모델로 계속 답합니다.

## 2. Edge DOM 참조

새 도구:

```text
edge_cdp_list_elements
edge_cdp_get_element
edge_cdp_click_element
edge_cdp_fill_element
```

요소 조회 예:

```text
현재 Edge 페이지 링크 목록 알려줘
현재 페이지에서 '문서 보기' 링크 눌러줘
메모 입력창에 '회의 내용 확인'이라고 적어줘
```

요소는 다음과 같은 짧은 참조로 반환됩니다.

```text
edge_el_a1b2c3d4e5f6
```

참조는 기본 180초 동안 유효합니다. DOM이 바뀌거나 같은 위치가 다른 요소로
교체되면 fingerprint 검증에 실패하며, 임의의 새 요소를 대신 누르지 않습니다.

## 3. 안전 분류

각 요소에는 다음 정보가 포함됩니다.

```json
{
  "element_ref": "edge_el_...",
  "kind": "link",
  "label": "문서 보기",
  "safety": {
    "allowed": true,
    "category": "low_risk_navigation"
  }
}
```

다음 동작은 자동 클릭·입력에서 차단됩니다.

```text
로그인·로그아웃
폼 제출
메시지 전송·게시·업로드
구매·결제·주문·예약 확정
삭제·탈퇴·송금·이체
비밀번호·인증번호
카드·신원·계좌 필드
로그인·결제 폼
```

일반 텍스트 입력은 **초안 입력만** 수행하며 Enter, 제출, 전송은 하지 않습니다.

## 4. 실행 검증

클릭 후 다음을 비교합니다.

```text
URL
페이지 제목
checked/value/aria-pressed/aria-expanded/aria-selected
새 탭 개수
```

명확한 변화가 있으면 `verification_strength=strong`, 변화는 없지만 클릭 자체가
정상 반환되면 `acknowledged`로 기록합니다.

텍스트 입력 후에는 `input_value()`를 다시 읽어 입력 문자열과 정확히 같은지
확인합니다. 도구 결과에는 실제 텍스트 대신 글자 수만 남깁니다.

## 설정

```toml
[edge_cdp]
element_ref_ttl_seconds = 180.0
max_elements = 100
max_fill_characters = 2000
allow_dom_actions = true
```

읽기 전용으로 실행:

```powershell
python -m src.main --disable-edge-cdp-dom-actions
```

## 실행

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m src.main
```

정상 시작 로그:

```text
LLM model      : gpt-5.1
Route balanced: gpt-5.1 / high
Route strong  : gpt-5-pro / high
Edge DOM       : safe actions / ref TTL=180s
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

Linux 테스트 환경에서는 실제 Edge·OpenAI API를 호출하지 않고 Playwright 형태의
가짜 페이지와 모델 클라이언트를 사용합니다. 실제 Windows Edge 및 계정별 모델
접근 권한은 사용자 PC에서 최종 확인해야 합니다.

## 커밋 메시지

```bash
git commit -m "Add safe Edge DOM actions and real OpenAI model defaults"
```

## 다음 묶음

```text
다운로드 없는 안전한 페이지 탐색 키
다중 탭·새 탭 선택 흐름 강화
페이지 상태 변화 감지 및 재계획
안전한 폼 초안 여러 필드 일괄 작성
```
