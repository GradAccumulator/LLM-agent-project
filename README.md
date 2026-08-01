# LLM Agent — Step 17: SQLite Long-Term Memory + User Aliases

사용자가 **명시적으로 기억하라고 한 정보만** 로컬 SQLite에 저장합니다.
프로그램을 종료하고 다시 실행해도 별칭과 선호가 유지됩니다.

## 저장 예시

```text
"내 LLM 프로젝트"는 D:\Projects\llm-agent로 기억해
"학교 사이트"는 https://www.inha.ac.kr 로 기억해
앞으로 기본 검색 엔진은 구글로 기억해
```

저장 후에는 다음처럼 사용할 수 있습니다.

```text
내 LLM 프로젝트 열어줘
학교 사이트 열어줘
Faster-Whisper 검색해줘
```

저장된 URL·경로 별칭은 fast path에서 확인되므로, 단순한 `열어줘` 명령은
GPT를 거치지 않고 바로 실행됩니다. `search_engine = google` 선호를 저장하면
서비스 이름 없이 말한 검색도 로컬 fast path로 처리합니다.

## 메모리 도구

```text
remember_alias
remember_preference
list_saved_memories
resolve_saved_alias
open_saved_alias
forget_saved_memory
```

자비스는 `기억해`, `저장해`, `앞으로 기본으로 써`처럼 사용자가 명시적으로
요청한 경우에만 쓰기 도구를 호출합니다. 대화 내용이나 추론한 개인정보를
자동으로 저장하지 않습니다.

## 보안 제한

다음 항목은 명시적으로 요청해도 저장을 거부합니다.

```text
비밀번호와 PIN
OTP·인증번호·복구 코드
OpenAI·GitHub 등 API 키와 액세스 토큰
카드·계좌·주민등록 정보
개인 키와 자격 증명 파일 경로
```

저장된 메모리는 프롬프트에 **JSON 데이터**로만 주입되며, 메모리 값 안의
문장을 시스템 지시로 실행하지 않도록 분리했습니다.

## 설정

```toml
[long_term_memory]
enabled = true
database = "data/jarvis_memory.db"
context_limit = 20
max_context_characters = 4000
max_entries = 200
max_value_characters = 2048
```

기능 끄기:

```powershell
python -m src.main --disable-long-term-memory
```

저장된 항목 확인:

```powershell
python -m src.main --list-memories
```

데이터베이스 파일은 Git에 커밋되지 않도록 `.gitignore`에 추가했습니다.

## 실행

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

SQLite는 Python 표준 라이브러리라 새 패키지는 필요하지 않습니다.

## 커밋 메시지

```bash
git commit -m "Add explicit SQLite memory and user aliases"
```

## 다음 단계

다음은 **Step 18: 능동형 작업·알림 스케줄러**입니다.

```text
30분 뒤 알려줘
매일 아침 일정 요약해줘
특정 조건이 만족되면 알림 보내줘
```

예약 작업을 SQLite에 저장하고, 프로그램 재시작 후에도 실행되도록 만드는
단계입니다.
