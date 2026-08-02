# LLM Agent — Step 19.2: Gmail Read-Only

Gmail을 **읽기 전용 OAuth 권한**으로 연결했습니다.

## 가능한 명령

```text
최근 중요한 메일 5개 요약해줘
읽지 않은 메일 몇 개야?
오늘 온 학교 관련 메일 찾아줘
지난 7일 동안 쿠팡에서 온 메일 보여줘
최근 메일 중 답장이 필요해 보이는 것 정리해줘
```

추가된 도구:

```text
gmail_status
gmail_profile
gmail_list_messages
gmail_get_message
gmail_unread_count
gmail_list_labels
```

메일 전송·회신·삭제·보관·읽음 처리·라벨 변경 도구는 없습니다.

## Google Cloud 준비

기존 Google Calendar와 같은 Google Cloud 프로젝트를 사용할 수 있습니다.

```text
Google Cloud Console
→ Gmail API 활성화
→ 기존 Desktop app OAuth Client 사용
```

Calendar에서 사용한 Desktop OAuth JSON을 복사해도 됩니다.

```powershell
Copy-Item `
  config\google_calendar_credentials.json `
  config\gmail_credentials.json
```

또는 Google Cloud에서 같은 Desktop app의 JSON을 다시 다운로드해 다음
경로에 둡니다.

```text
config/gmail_credentials.json
```

OAuth 앱이 테스트 상태라면 로그인할 Google 계정이 테스트 사용자에
등록되어 있어야 합니다.

## 설치 및 최초 인증

```powershell
python -m pip install -r requirements.txt
python -m src.main --gmail-auth
```

요청하는 권한은 다음 하나뿐입니다.

```text
https://www.googleapis.com/auth/gmail.readonly
```

토큰은 Calendar 토큰과 분리해 저장합니다.

```text
data/gmail_token.json
```

상태 확인:

```powershell
python -m src.main --gmail-status
```

정상 출력 예:

```json
{
  "enabled": true,
  "authenticated": true,
  "scope": "https://www.googleapis.com/auth/gmail.readonly"
}
```

## 실행

```powershell
python -m src.main
```

시작 로그:

```text
Gmail          : connected (enabled)
Gmail scope    : read-only
Google Calendar: connected (enabled)
```

## Gmail 검색식

`gmail_list_messages`는 Gmail 검색창과 같은 검색식을 사용합니다.

```text
is:unread
newer_than:7d
from:example@gmail.com
subject:과제
has:attachment
category:primary
```

예:

```text
최근 7일 동안 읽지 않은 학교 메일 요약해줘
```

내부 검색식 예:

```text
is:unread newer_than:7d (학교 OR 인하대)
```

## 본문 처리

여러 메일을 조회할 때는 필요한 개수만 가져오고, 본문은 설정된 글자 수까지만
전달합니다.

```toml
[gmail]
enabled = true
credentials_file = "config/gmail_credentials.json"
token_file = "data/gmail_token.json"
user_id = "me"
max_results = 20
max_body_characters = 8000
oauth_port = 0
open_browser_for_auth = true
```

HTML 메일은 로컬에서 일반 텍스트로 변환합니다. 긴 본문은 잘렸다는 표시와
함께 제한됩니다.

## 보안

다음 파일은 `.gitignore`에 포함했습니다.

```gitignore
config/gmail_credentials.json
data/gmail_token.json
data/gmail_token.json.*
```

Gmail 본문은 도구 결과로 모델에 전달될 수 있으므로, 민감한 메일을 질문할
때는 사용 중인 OpenAI API 데이터 처리 정책도 함께 고려해야 합니다.

## 기능 끄기

```powershell
python -m src.main --disable-gmail
```

## 커밋 메시지

```bash
git commit -m "Add read-only Gmail OAuth integration"
```

## 다음 단계

다음은 **Step 20: 명시적 확인이 필요한 쓰기 작업 계층**입니다.

먼저 Calendar 일정 생성·수정부터 추가하고, 실행 전에 자비스가 변경 내용을
읽어 준 뒤 사용자가 확인해야만 API를 호출하도록 만들 예정입니다.
