# LLM Agent — Step 19.1: Google Calendar Read-Only

Google Calendar를 읽기 전용 OAuth로 연결했습니다.

## 가능한 명령

```text
오늘 일정 알려줘
내일 일정 뭐 있어?
이번 주 일정 중 시험만 찾아줘
내일 1시간 비는 시간 찾아줘
접근 가능한 캘린더 목록 보여줘
```

추가된 도구:

```text
google_calendar_status
google_calendar_list_calendars
google_calendar_list_events
google_calendar_find_free_time
```

일정 생성·수정·삭제 도구는 없습니다.

## Google Cloud 준비

1. Google Cloud 프로젝트를 만듭니다.
2. Google Calendar API를 활성화합니다.
3. Google Auth Platform에서 OAuth 동의 화면을 설정합니다.
4. OAuth Client를 만들고 **Desktop app**을 선택합니다.
5. 다운로드한 JSON을 다음 위치에 둡니다.

```text
config/google_calendar_credentials.json
```

OAuth 앱이 테스트 상태라면 자신의 Google 계정을 테스트 사용자에 추가합니다.

## 설치 및 최초 인증

```powershell
python -m pip install -r requirements.txt
python -m src.main --google-calendar-auth
```

요청 scope:

```text
https://www.googleapis.com/auth/calendar.readonly
```

토큰 저장 위치:

```text
data/google_calendar_token.json
```

상태 확인:

```powershell
python -m src.main --google-calendar-status
```

실행:

```powershell
python -m src.main
```

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
```

민감 파일은 `.gitignore`에 포함했습니다.

```gitignore
config/google_calendar_credentials.json
data/google_calendar_token.json
data/google_calendar_token.json.*
```

## 커밋 메시지

```bash
git commit -m "Add read-only Google Calendar OAuth integration"
```

## 다음 단계

다음은 **Step 19.2: Gmail 읽기 전용 연결**입니다.
