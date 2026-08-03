# LLM Agent — Step 20.1–20.2: Confirmed Calendar Writes

서로 밀접한 다음 작업을 묶어서 구현했습니다.

```text
Step 20.1
→ 승인 후 Google Calendar 일정 생성

Step 20.2
→ 승인 후 일정 수정
→ 숫자 코드 승인 후 일정 삭제
```

## 가능한 명령

```text
내일 오후 3시부터 4시까지 병원 일정 추가해줘
내일 병원 일정을 오후 5시로 옮겨줘
금요일 저녁 약속 제목을 저녁 모임으로 바꿔줘
내일 병원 일정 삭제해줘
```

## 실행 흐름

일정 생성과 수정:

```text
사용자 요청
→ 현재 날짜·시간대 확인
→ 생성 내용 또는 정확한 기존 event_id 확인
→ 작업 요약 표시
→ 사용자가 별도 입력으로 "승인"
→ API 실행
→ events.get으로 다시 조회
→ 결과 검증
```

일정 삭제:

```text
삭제 대상 event_id 확인
→ 고위험 승인 코드 표시
→ 사용자가 "승인 1234" 입력
→ events.delete 실행
→ 다시 조회해 404/410 확인
```

같은 제목의 일정이 여러 개면 자비스가 임의로 고르지 않고 후보를 보여준
뒤 사용자가 선택해야 합니다.

## 새 도구

```text
google_calendar_get_event
google_calendar_create_event
google_calendar_update_event
google_calendar_delete_event
```

기존 조회 도구도 그대로 유지됩니다.

```text
google_calendar_status
google_calendar_list_calendars
google_calendar_list_events
google_calendar_find_free_time
```

## OAuth scope 확장

기존 읽기 전용 토큰에는 일정 쓰기 권한이 없습니다. 이 버전으로 교체한 뒤
**한 번 다시 인증**해야 합니다.

```powershell
python -m src.main --google-calendar-auth
```

요청 scope:

```text
https://www.googleapis.com/auth/calendar.readonly
https://www.googleapis.com/auth/calendar.events
```

기존 OAuth Desktop Client JSON은 그대로 사용할 수 있습니다.

상태 확인:

```powershell
python -m src.main --google-calendar-status
```

정상 예:

```json
{
  "authenticated": true,
  "ready": true,
  "missing_scopes": [],
  "reauthorization_required": false,
  "write_ready": true
}
```

이전 토큰인 경우:

```json
{
  "authenticated": true,
  "ready": false,
  "missing_scopes": [
    "https://www.googleapis.com/auth/calendar.events"
  ],
  "reauthorization_required": true,
  "write_ready": false
}
```

이때 `--google-calendar-auth`를 다시 실행하면 새 권한으로 토큰 파일을
덮어씁니다.

## 안전 정책

```text
생성: standard 승인
수정: standard 승인
삭제: high 승인 코드
```

최초 요청에 “승인해서 만들어줘”라고 같이 말해도 바로 실행되지 않습니다.
반드시 승인 대기 작업이 생긴 다음 별도의 입력으로 승인해야 합니다.

Calendar API에는 다음 옵션을 사용합니다.

```text
sendUpdates="none"
```

현재 단계에서는 참석자 초대 기능을 제공하지 않으며 초대 메일도 보내지
않습니다.

수정은 부분 변경 방식으로 처리해 지정하지 않은 기존 일정 필드를 유지합니다.
삭제 후에는 해당 event_id를 다시 조회해 실제 삭제 여부를 검증합니다.

## 설정

```toml
[google_calendar]
enabled = true
credentials_file = "config/google_calendar_credentials.json"
token_file = "data/google_calendar_token.json"
default_calendar_id = "primary"
max_results = 50
oauth_port = 0
open_browser_for_auth = true
allow_writes = true
```

쓰기 기능만 끄기:

```powershell
python -m src.main --disable-google-calendar-writes
```

이 경우 조회 기능은 유지되고 생성·수정·삭제 도구만 등록되지 않습니다.

## 예시

```text
너:
내일 오후 3시부터 4시까지 병원 일정 추가해줘

자비스:
Google Calendar 'primary'에 '병원' 일정 생성
(2026-08-03T15:00:00+09:00 ~ 2026-08-03T16:00:00+09:00)
진행하려면 정확히 '승인', 취소하려면 '취소'라고 말해주세요.

너:
승인

자비스:
일정을 생성하고 다시 조회해 검증했습니다.
```

삭제 예:

```text
자비스:
APPROVE: 승인 4821

너:
승인 4821
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

실제 Google API 쓰기 호출은 테스트에서 수행하지 않으며 가짜 API 서비스로
생성·수정·삭제와 검증 흐름을 확인합니다.

## 커밋 메시지

```bash
git commit -m "Add confirmed Calendar create update and delete actions"
```

## 다음 단계

다음은 **Step 21.1–21.2: Windows 창 탐색과 UI Automation 요소 인식**입니다.

```text
VSCode 창 앞으로 가져와줘
설정 창의 저장 버튼 눌러줘
현재 창에서 검색 상자 찾아줘
```

먼저 읽기·탐색 중심으로 구현하고 실제 클릭·입력은 기존 승인 계층과 연결합니다.
