# LLM Agent — Step 11: Continuous Conversation

한 번 `Hey Jarvis`로 깨운 뒤 일정 시간 동안은 호출어 없이 후속 질문을 받을
수 있게 만들었습니다.

## 동작

```text
Hey Jarvis
→ 첫 명령
→ 자비스 답변
→ 12초 동안 후속 명령 대기
→ 후속 질문
→ 자비스 답변
→ 다시 12초 대기
```

다음 조건이면 호출어 대기 상태로 돌아갑니다.

```text
후속 질문 대기 시간 초과
"대화 종료", "그만", "됐어" 등의 종료 명령
최대 대화 턴 도달
연속 대화 비활성화
복구가 필요한 오류
```

## 상태

```text
STARTING
→ SLEEPING
→ AWAITING_SPEECH
→ CAPTURING
→ TRANSCRIBING
→ THINKING
→ SPEAKING
→ AWAITING_SPEECH
```

`SLEEPING`은 웨이크워드를 기다리는 상태이고, `AWAITING_SPEECH`는 웨이크워드
감지 후 또는 후속 질문을 기다리는 상태입니다. VAD가 실제 발화를 감지할 때
`CAPTURING`으로 전환됩니다.

## 설정

```toml
[conversation]
enabled = true
followup_timeout_seconds = 12.0
max_turns = 8
```

CLI 설정:

```powershell
python -m src.main `
  --followup-timeout 15 `
  --max-conversation-turns 12
```

매번 웨이크워드를 요구:

```powershell
python -m src.main --disable-continuous-conversation
```

## 종료 명령

```text
대화 종료
대화 끝
자비스 그만
이제 그만
이제 됐어
됐어
그만
```

`대화 종료`는 웨이크워드 없는 세션만 종료합니다. GPT 대화 기억까지 지우려면
기존 `대화 초기화` 명령을 사용합니다.

## 로그

기존 JSONL 성능 로그에 다음 정보가 추가됩니다.

```text
conversation_started
followup_listening_started
conversation_turn_completed
conversation_ended
conversation_id
turn_index
wakeword_required
```

## 실행 및 테스트

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.main
```

## 커밋 메시지

```bash
git commit -m "Add wake-word-free continuous conversation sessions"
```

다음 주요 단계는 Windows UI Automation입니다.
