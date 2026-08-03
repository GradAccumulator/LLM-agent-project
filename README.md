# LLM Agent — Step 21.1–21.3: Windows UI Automation Bundle

서로 강하게 연결된 세 단계를 한 번에 구현했습니다.

```text
Step 21.1 — 창 검색과 정확한 window_id 식별
Step 21.2 — UI Automation 요소 트리 읽기·검색
Step 21.3 — 승인 기반의 안전한 요소 포커스·실행·입력·토글·선택
```

## 가능한 명령

```text
현재 열린 VSCode 창 찾아줘
설정 창의 버튼 목록 보여줘
현재 창에서 이름에 저장이 들어간 버튼 찾아줘
검색 상자에 파이썬 입력해줘
다크 모드 토글을 바꿔줘
일반적인 확인 버튼 눌러줘
```

## 추가된 도구

읽기·탐색:

```text
uia_find_windows
uia_inspect_window
uia_find_elements
uia_get_element
```

동작:

```text
uia_focus_element
uia_invoke_element
uia_set_value
uia_toggle_element
uia_select_element
```

`uia_focus_element`는 포커스만 옮기며, 나머지 UI 변경 도구는 Step 20 승인 계층을
거쳐 별도의 `승인` 입력 후에만 실행됩니다.

## 안전 구조

```text
창 검색
→ UI 요소 검사
→ element_ref 발급
→ 대상 하나로 확정
→ 변경 작업이면 승인 대기
→ 승인 후 UI Automation 패턴 실행
→ 결과 검증
```

임의 화면 좌표 클릭과 무제한 키보드 입력은 사용하지 않습니다. 요소가 Invoke,
Value, Toggle, SelectionItem 같은 Microsoft UI Automation 패턴을 제공할 때만
동작합니다.

다음 유형은 차단됩니다.

```text
비밀번호 필드 입력
삭제·제거·구매·결제·주문·전송·제출·초기화처럼 위험한 이름의 버튼 Invoke
2000자를 넘는 UI 텍스트 입력
만료되거나 사라진 요소 참조
```

위험한 UI 작업은 잘못 분류해 실행하는 것보다 이번 단계에서 거절하는 쪽으로
설계했습니다.

## element_ref

UI 요소를 검사하면 다음과 같은 임시 참조가 반환됩니다.

```text
uia_a1b2c3d4e5f6
```

기본 유효 시간은 180초입니다. 창이 갱신되거나 참조가 만료되면 다시 검사합니다.
프로그램 재시작 시 모든 참조는 사라집니다.

반환 속성 예:

```text
name
control_type
automation_id
class_name
enabled
visible
offscreen
focusable
focused
password
bounds
```

값은 기본적으로 읽지 않습니다. 사용자가 명시적으로 현재 입력값을 확인해야 할 때만
`include_value=true`를 사용하며 비밀번호 값은 절대 반환하지 않습니다.

## 설치

```powershell
python -m pip install -r requirements.txt
```

추가 의존성:

```text
pywinauto==0.6.9
```

UI Automation backend를 사용합니다.

## 설정

```toml
[windows_uia]
enabled = true
backend = "uia"
element_ttl_seconds = 180.0
max_elements = 200
allow_actions = true
```

읽기 전용으로 실행:

```powershell
python -m src.main --disable-windows-uia-actions
```

전체 비활성화:

```powershell
python -m src.main --disable-windows-uia
```

## 한계

모든 앱이 Microsoft UI Automation 요소를 완전하게 노출하는 것은 아닙니다.
특히 자체 렌더링 UI, 게임, 일부 Java UI는 창 프레임만 보이거나 요소가 누락될 수
있습니다. 그런 경우 좌표를 추측해 클릭하지 않고 `inspect_screen`으로 화면을
설명한 뒤 지원되지 않는다고 보고합니다.

이 환경에서는 Linux 단위 테스트만 실행했으므로 실제 Windows 창, 포커스, UIA
패턴 호출은 사용자의 PC에서 최종 확인해야 합니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Add safe Windows UI Automation inspection and actions"
```

## 다음 단계

다음 묶음은 **Step 21.4 + 22.1–22.3: 화면 이해와 일반 Edge 탭·DOM 읽기**가
적절합니다.

```text
현재 화면과 UIA 요소를 함께 비교
일반 Edge의 열린 탭 목록 조회
현재 페이지 본문 읽기·요약
DOM 요소와 화면 상태 교차 검증
```

로그인·결제·양식 제출처럼 결과가 큰 동작은 자동 실행하지 않고 별도 고위험 정책을
먼저 설계합니다.
