# LLM Agent — Step 8: Explicit State Machine

기존의 거대한 `while True` 음성 파이프라인을 명시적인 상태 머신과 런타임
클래스로 분리했습니다. 기능은 유지하면서 이후 연속 대화, 말 끊기,
비동기 TTS, GUI 상태 표시를 붙일 수 있는 구조로 바꿨습니다.

## 상태

```text
STARTING
LISTENING
CAPTURING
TRANSCRIBING
THINKING
EXECUTING_TOOL
SPEAKING
ERROR
RECOVERING
STOPPED
```

정상적인 명령 흐름:

```text
STARTING
→ LISTENING
→ CAPTURING
→ TRANSCRIBING
→ THINKING
→ EXECUTING_TOOL
→ THINKING
→ SPEAKING
→ LISTENING
```

도구를 사용하지 않거나 TTS가 꺼져 있으면 필요 없는 상태는 건너뜁니다.

## 실행 로그 예시

```text
[STATE] STARTING -> LISTENING | startup completed
[STATE] LISTENING -> CAPTURING | wake word detected
[STATE] CAPTURING -> TRANSCRIBING | speech capture completed
[STATE] TRANSCRIBING -> THINKING | transcription ready
[STATE] THINKING -> EXECUTING_TOOL | tool started: inspect_screen
[STATE] EXECUTING_TOOL -> THINKING | tool finished: inspect_screen (success)
[STATE] THINKING -> SPEAKING | speaking response
[STATE] SPEAKING -> LISTENING | response completed
```

각 줄에는 이전 상태에서 머문 시간도 함께 표시됩니다.

상태 로그를 숨기려면:

```powershell
python -m src.main --hide-state-transitions
```

## 오류 복구

명령 처리 중 복구 가능한 오류가 발생하면:

```text
현재 상태
→ ERROR
→ RECOVERING
→ LISTENING
```

순서로 마이크 큐, 웨이크워드, VAD 상태를 초기화하고 다시 대기합니다.

복구 대기 시간 변경:

```powershell
python -m src.main --recovery-delay 0.5
```

## 새 구조

```text
src/
├── app/
│   ├── cli.py          # CLI 옵션
│   ├── bootstrap.py    # STT, LLM, TTS 등 객체 생성
│   └── runtime.py      # 음성 명령 실행 흐름
├── core/
│   └── state_machine.py
├── llm/
│   └── agent.py        # 도구 시작·종료 이벤트 제공
└── main.py             # 작은 진입점
```

`main.py`는 인자 처리와 시작 오류 처리만 맡고, 실제 음성 비서 흐름은
`VoiceAssistantRuntime`이 담당합니다.

## 상태 전이 검증

허용되지 않은 상태 전이는 즉시 `InvalidStateTransition`을 발생시킵니다.

예를 들어 시작 직후 `STARTING → SPEAKING`은 허용되지 않습니다. 이런 검증은
끼어들기나 비동기 처리를 추가할 때 잘못된 상태 경쟁을 빠르게 발견하는 데
도움이 됩니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

검사 항목:

- 정상 음성 명령 상태 순서
- 잘못된 상태 전이 차단
- 오류 복구 경로
- 상태 리스너 호출

## 설치 및 실행

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

기존 설정은 유지됩니다.

```text
호출어: Hey Jarvis
웨이크워드 임계값: 0.45
STT: Faster-Whisper turbo / CUDA float16 우선
LLM: gpt-5.6-luna
화면 분석: inspect_screen
TTS: Edge Neural TTS
```

## 커밋 메시지

```bash
git commit -m "Refactor voice pipeline into an explicit state machine"
```

## 다음 단계

다음은 CLI 기본값을 TOML 설정 파일로 옮기고, 상태별 지연 시간을 JSONL 또는
SQLite에 기록하는 설정·성능 로깅 단계가 적합합니다.
