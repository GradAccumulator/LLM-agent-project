# LLM Agent — Step 21.3.1: Selective Stronger-Model Routing

기본 모델은 계속 `gpt-5.6-luna`를 사용하면서, **판단이 어려운 부분만**
`gpt-5.6-terra` 또는 `gpt-5.6-sol`에 위임하는 선택적 라우터를 추가했습니다.

## 작동 방식

```text
일상 대화·단순 조회·확정된 도구 실행
→ gpt-5.6-luna가 그대로 처리

복잡한 판단이 필요한 하위 문제
→ delegate_reasoning에 필요한 문맥만 전달
→ Terra 또는 Sol이 판단만 수행
→ Luna가 판단 결과와 로컬 도구 결과를 합쳐 최종 응답
```

상위 모델에는 Calendar, Gmail, Windows UIA, 파일, 브라우저 등의 작업 도구를
전혀 제공하지 않습니다. 상위 모델은 판단 결과만 반환하며 실제 변경은 기존
도구와 승인 계층을 통과해야 합니다.

## 사용자가 직접 요청

다음 표현은 코드에서 명시적 승격 요청으로 감지합니다.

```text
이번 건 강한 모델로 판단해줘
상위 모델로 검토해줘
Sol로 분석해줘
더 깊게 생각해줘
Terra로 검토해줘
```

명시적 요청은 첫 판단 라운드에서 `delegate_reasoning`을 강제로 한 번 호출합니다.
기본 모델이 요청을 무시하거나 단순 답변으로 건너뛰지 못합니다.

단순히 다음처럼 모델에 관해 질문하는 것은 승격 요청으로 취급하지 않습니다.

```text
강한 모델이 뭐야?
Sol 모델 가격이 뭐야?
```

## 자동 승격

기본 모델은 다음 상황에서만 `delegate_reasoning`을 선택할 수 있습니다.

```text
서로 충돌하는 증거 또는 후보
복잡한 코드 구조·아키텍처 판단
중대한 선택에서 높은 불확실성
도구 실행이 반복해서 실패해 복구 판단이 필요함
여러 제약을 동시에 만족해야 하는 계획 검토
```

다음 작업은 자동 승격 대상이 아닙니다.

```text
현재 시간
단순 일정 조회
읽지 않은 메일 수
앱 열기
일상 대화
이미 확정된 도구 실행
```

기본 제한은 요청당 한 번입니다. 상위 모델 호출에는 도구가 없어서 재귀 위임도
불가능합니다.

## 위임되는 정보

`delegate_reasoning` 입력:

```text
task             정확한 하위 문제 하나
relevant_context 필요한 사실·후보·도구 결과만
reason           상위 모델이 필요한 이유
target_tier      balanced 또는 strong
output_format    원하는 결과 형식
```

전체 대화를 자동으로 넘기지 않으며 총 입력 문자는 기본 20,000자로 제한됩니다.
비밀번호, OTP, API 키, 결제·계좌 정보는 보내지 않도록 시스템 지침에도 명시했습니다.

## 실패 처리

상위 모델 호출이 실패하면 기본 설정에서는:

```text
실패 기록
→ 실패 사실을 기본 모델에 전달
→ 기본 모델이 가능한 범위에서 응답
→ 성공한 것처럼 숨기지 않음
```

실패 시 전체 요청을 중단하게 만들 수도 있습니다.

```powershell
python -m src.main --disable-routing-fallback
```

## 설정

```toml
[model_routing]
enabled = true
balanced_model = "gpt-5.6-terra"
strong_model = "gpt-5.6-sol"
balanced_reasoning = "high"
strong_reasoning = "xhigh"
allow_user_override = true
allow_automatic_escalation = true
max_delegations_per_turn = 1
max_input_characters = 20000
max_output_tokens = 1200
timeout_seconds = 90.0
fallback_to_default = true
```

자동 판단만 끄고 사용자가 직접 요청한 경우에만 사용:

```powershell
python -m src.main --disable-routing-automatic
```

전체 라우팅 끄기:

```powershell
python -m src.main --disable-model-routing
```

상위 모델 변경:

```powershell
python -m src.main `
  --routing-balanced-model gpt-5.6-terra `
  --routing-strong-model gpt-5.6-sol
```

## 콘솔 로그

```text
MODEL ROUTE: gpt-5.6-luna -> gpt-5.6-sol
             [strong | explicit | success]
DELEGATED: 후보 일정 3개 중 제약을 가장 잘 만족하는 시간 판단
REASON: 제약이 충돌하고 결과가 일정 생성에 영향을 줌
DELEGATE META: reasoning=xhigh | total=4.82s | 1240→386 tokens
```

`JARVIS META`에도 위임 횟수가 표시됩니다.

```text
JARVIS META [gpt-5.6-luna | ... | tools=2 | delegates=1 | web=0]
```

JSONL metrics에는 모델, 이유, 명시/자동 여부, 지연시간, 입출력 토큰 수, 성공 여부가
기록됩니다. 전체 위임 문맥은 로그에 저장하지 않고 짧은 task preview만 남깁니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

실제 OpenAI API는 단위 테스트에서 호출하지 않습니다. 가짜 Responses API로
명시적 감지, 강제 tool choice, 문맥 제한, 요청당 횟수 제한, 실패 fallback,
도구 미제공을 검사합니다.

## 커밋 메시지

```bash
git commit -m "Add selective stronger-model delegation"
```

## 다음 묶음

다음은 원래 예정한 다음 작업으로 돌아갑니다.

```text
Step 21.4
화면 캡처와 UIA 요소 교차 분석

Step 22.1-22.3
일반 Edge 탭 연결
탭 조회·전환
현재 페이지 DOM 본문 읽기·요약
```

화면과 DOM의 판단이 복잡할 때 이번 단계의 선택적 Sol/Terra 위임을 바로 활용할 수
있습니다.
