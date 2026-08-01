# LLM Agent — Step 18: Persistent Reminders and Recurring Tasks

## Step 18.1.1 — 텍스트 입력 비활성 타이머

연속 대화의 12초 제한을 고정된 전체 시간에서 **마지막 키보드 입력 이후의
비활성 시간**으로 변경했습니다.

```text
FOLLOW-UP 시작
→ 8초 뒤 첫 글자 입력
→ 타이머 다시 12초
→ 다음 글자 입력
→ 다시 12초
→ Enter
→ 즉시 텍스트 명령 처리
```

따라서 긴 문장을 입력하는 도중에는 시간이 지나도 끊기지 않습니다. 마지막
글자 이후 음성·키보드 입력이 모두 12초 동안 없을 때만 호출어 대기 상태로
돌아갑니다.

Windows CMD에서는 첫 글자를 상호작용 키로 소비하지 않고 직접 입력 버퍼에
추가합니다. 한글 입력도 첫 글자부터 보존됩니다.

정상 안내 문구:

```text
FOLLOW-UP: listening for 12.0s.
Typing resets the 12.0s inactivity timer.
```

## Step 18.1 — 음성·텍스트 통합 입력과 문장별 출력

별도의 채팅 모드 전환 없이 `python -m src.main`을 실행한 같은 CMD 창에서
바로 텍스트 명령을 입력할 수 있습니다.

```text
Voice: say "Hey Jarvis".
Text: type normally and press Enter.
Ctrl+C stops Jarvis.
YOU> 안녕
```

백그라운드에서 표준 `input()`이 **전체 줄을 그대로** 받기 때문에 첫 번째 글자를
모드 전환 키로 소비하지 않습니다. 예를 들어 `안녕`을 입력하면 `ㅏㄴ녕`이 아니라
`안녕` 전체가 전달됩니다.

텍스트 입력은 음성 파이프라인과 같은 로컬 명령·fast path·GPT·도구를 사용하지만,
그 답변은 TTS로 읽지 않습니다. 음성으로 질문한 답변과 예약 알림 TTS는 기존처럼
동작합니다.

TTS가 재생되는 중 텍스트 한 줄을 제출하면 TTS를 즉시 중단하고, 현재 작업이 안전한
지점에 도달한 뒤 입력된 텍스트를 처리합니다. 음성 캡처 대기 중이라면 캡처를 취소하고
텍스트 명령으로 바로 전환합니다.

GPT와 로컬 응답은 문장별로 줄을 나누고 전체 문장 수를 표시합니다.

```text
JARVIS | 1/3 | 첫 번째 문장입니다.
       | 2/3 | 두 번째 문장입니다.
       | 3/3 | 세 번째 문장입니다.
```

스트리밍 TTS는 그대로 낮은 지연 시간으로 재생하지만, CMD에는 델타를 한 줄로 이어
붙이지 않고 완성된 답변을 위 형식으로 한 번만 출력합니다.

### 커밋 메시지

```bash
git commit -m "Reset follow-up timeout on keyboard activity"
```

### 다음 단계

다음은 **Step 19: Google Calendar·Gmail 읽기 전용 연결**입니다. 오늘 일정,
빈 시간, 최근 중요 메일을 조회하고, 생성·전송 같은 쓰기 작업은 별도 확인을 받게
만드는 단계입니다.


알림과 반복 작업을 SQLite에 저장하고, Jarvis를 다시 실행해도 유지되게
만들었습니다.

## GPT 없이 바로 예약되는 명령

```text
30분 뒤에 물 마시라고 알려줘
2시간 후 과제 하라고 알려줘
알림 목록 보여줘
알림 3번 취소해줘
```

상대 시간 명령은 로컬 fast path에서 처리하므로 OpenAI API를 호출하지 않습니다.

## 날짜·시간 및 반복 알림

```text
내일 오후 3시에 병원 예약 확인하라고 알려줘
매일 오전 8시에 오늘 할 일 확인하라고 알려줘
매주 월요일 오후 7시에 주간 계획 세우라고 알려줘
5번 알림을 20분 미뤄줘
```

복잡한 시간 표현은 GPT가 `get_current_datetime`으로 로컬 시간대를 확인한 뒤
스케줄러 도구를 호출합니다.

## 추가 도구

```text
schedule_relative_reminder
schedule_reminder
schedule_recurring_reminder
list_scheduled_reminders
cancel_scheduled_reminder
snooze_scheduled_reminder
```

## 전달 방식

Jarvis가 `SLEEPING` 상태에서 호출어를 기다리는 동안 예약 시간이 되면 콘솔,
알림음, TTS로 알려줍니다. 대화나 STT가 진행 중이면 큐에 보관했다가 다시
대기 상태가 되었을 때 전달합니다.

프로그램이 꺼져 있던 동안 지난 일회성 알림은 다음 실행 때 한 번 전달됩니다.
반복 알림은 누락 횟수만큼 연속 재생하지 않고 다음 미래 시각으로 이동합니다.

## 설정

```toml
[scheduler]
enabled = true
database = "data/jarvis_tasks.db"
poll_interval_seconds = 0.5
max_tasks = 200
max_message_characters = 500
announce_with_tts = true
max_announcements_per_cycle = 3
```

```powershell
python -m src.main --list-reminders
python -m src.main --scheduler-no-tts
python -m src.main --disable-scheduler
```

## 실행

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

## 커밋 메시지

```bash
git commit -m "Add persistent reminders and recurring task scheduling"
```

## 다음 단계

다음은 **Step 19: 캘린더·이메일 연결 계층**입니다. Google Calendar와 Gmail을
우선 읽기 전용으로 연결하고, 일정 생성이나 메일 전송 같은 쓰기 작업은 별도
확인을 거치게 만듭니다.
