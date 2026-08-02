# LLM Agent — Step 20: Explicit Confirmation Gate

실제 데이터를 변경하는 도구를 바로 실행하지 않고 **사용자가 별도의 승인
문구를 말하거나 입력해야만 실행**하는 공통 승인 계층을 추가했습니다.

## 기본 흐름

```text
사용자: 이 내용을 메모로 저장해줘

Jarvis:
실행 전 확인이 필요합니다.
notes 폴더에 '제목' Markdown 메모 저장
진행하려면 정확히 '승인', 취소하려면 '취소'라고 말해주세요.

사용자: 승인
→ 그때 실제 create_note 실행
→ 결과 검증
```

최초 요청에 `승인해줘`가 같이 들어 있어도 그 요청 안에서는 실행되지
않습니다. 승인은 반드시 **도구가 대기 작업을 만든 뒤의 별도 입력**이어야
합니다.

## 상태

새 상태:

```text
AWAITING_CONFIRMATION
```

콘솔 예:

```text
CONFIRMATION REQUIRED [a1b2c3d4e5 | standard]
ACTION: notes 폴더에 '여행 준비' Markdown 메모 저장
APPROVE: 승인
CANCEL : 취소
EXPIRES: approximately 60.0s
```

텍스트와 음성에서 동일하게 동작합니다.

```text
승인
실행 승인
이대로 실행해
취소
작업 취소
승인 대기 작업 보여줘
```

`응`, `그래`, `알겠어` 같은 모호한 표현은 승인으로 처리하지 않습니다.

## 위험 등급

공통 API는 두 등급을 지원합니다.

```text
standard
→ 정확한 "승인" 필요

high
→ 화면에 표시된 일회용 숫자 코드를 포함한
  "승인 1234" 형태 필요
```

코드를 여러 번 틀리면 대기 작업이 자동 취소됩니다.

## 만료와 재시작

승인 대기 작업은 기본 60초 후 만료됩니다. 대화의 12초 follow-up이 먼저
끝나더라도 승인 시간이 남아 있다면:

```text
Hey Jarvis
→ 승인
```

또는 CMD에 `승인`을 입력해 실행할 수 있습니다.

대기 작업은 메모리에만 존재하므로 프로그램을 종료하거나 오류 복구가
발생하면 사라집니다. 재시작 뒤에 오래된 쓰기 작업이 실행되는 것을 막기
위한 의도적인 설계입니다.

## 보호되는 현재 도구

Step 20에서는 기존 도구 중 실제 파일을 생성하는 다음 도구를 먼저
보호했습니다.

```text
create_note
```

Calendar와 Gmail은 현재 읽기 전용이므로 승인 대상이 아닙니다.

향후 쓰기 도구는 `ToolSpec`에 다음처럼 정책을 선언합니다.

```python
ToolSpec(
    name="example_write",
    description="...",
    parameters={...},
    handler=handler,
    confirmation=ConfirmationRequirement(
        summary=summarize_action,
        risk=ConfirmationRisk.STANDARD,
    ),
)
```

## 설정

```toml
[confirmation]
enabled = true
timeout_seconds = 60.0
high_risk_code_digits = 4
max_code_attempts = 3
```

CLI:

```powershell
python -m src.main --confirmation-timeout 90
python -m src.main --disable-confirmation
```

`--disable-confirmation`은 개발·테스트 용도이며 실제 사용에서는 끄지 않는
것을 권장합니다.

## 감사 로그

기존 JSONL metrics에 다음 정보가 기록됩니다.

```text
confirmation_required
confirmation_id
confirmation_waiting
tool execution result
```

승인 전에는 도구 handler가 호출되지 않으며, 실행 검증도 승인 후에만
수행됩니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Add explicit confirmation gate for protected actions"
```

## 다음 단계

다음은 **Step 20.1: 승인 후 Google Calendar 일정 생성**입니다.

```text
사용자: 내일 오후 3시에 병원 일정 추가해줘
Jarvis: 이 내용으로 생성할까요? 승인 또는 취소라고 말해주세요.
사용자: 승인
Jarvis: 일정을 생성하고 다시 조회해 생성 결과를 검증
```

Calendar OAuth scope를 쓰기 가능한 최소 범위로 확장하며, 기존 읽기 전용
토큰과 마이그레이션 절차도 함께 추가할 예정입니다.
