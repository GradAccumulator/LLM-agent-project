# LLM Agent — Step 14: Barge-In Voice Interruption

자비스가 말하는 도중 사용자가 말을 시작하면 음성 출력을 즉시 멈추고,
그 말을 새로운 후속 명령으로 바로 처리합니다.

## 동작 흐름

```text
사용자: Hey Jarvis, 오늘 일정 설명해줘
자비스: 오늘은 첫 번째로...
사용자: 아니, 내일 일정만 말해줘
자비스 TTS 즉시 중단
→ 끼어든 음성을 끝까지 캡처
→ STT
→ 빠른 명령 또는 GPT 처리
→ 새 답변
```

사용자가 끼어들었을 때 같은 말을 다시 반복할 필요가 없습니다.

## 오작동 방지

자비스 자신의 스피커 음성이 마이크로 들어오는 것을 사용자 발화로 잘못
판단하지 않도록 다음 조건을 함께 사용합니다.

```text
TTS 시작 후 0.65초 유예
별도 Silero VAD 모델
VAD 확률 0.78 이상
0.32초 연속 음성
최소 RMS 0.008
0.48초 침묵 시 발화 종료
```

헤드셋을 사용하면 스피커 재입력에 의한 오작동이 더 적습니다.

## 설정

`config/default.toml`:

```toml
[barge_in]
enabled = true
vad_threshold = 0.78
grace_seconds = 0.65
trigger_speech_seconds = 0.32
end_silence_seconds = 0.48
max_utterance_seconds = 12.0
pre_roll_seconds = 0.24
minimum_rms = 0.008
```

기능 끄기:

```powershell
python -m src.main --disable-barge-in
```

더 민감하게:

```powershell
python -m src.main `
  --barge-in-vad-threshold 0.68 `
  --barge-in-trigger-speech 0.24 `
  --barge-in-minimum-rms 0.005
```

자비스 목소리에 잘못 반응한다면:

```powershell
python -m src.main `
  --barge-in-vad-threshold 0.86 `
  --barge-in-trigger-speech 0.40 `
  --barge-in-minimum-rms 0.012
```

## TTS 변경

Edge TTS 재생 루프에 중단 이벤트를 추가했습니다. 사용자 발화가 감지되면
보통 다음 오디오 확인 주기인 약 10ms 안에 현재 재생을 중지합니다.

로그 예시:

```text
BARGE-IN: voice detected, stopping TTS...
TTS LATENCY: first_audio=0.51s | chunks=1/4 | total=1.37s | interrupted=True
BARGE-IN: processing the interruption now.
```

JSONL 성능 로그에는 다음 이벤트가 추가됩니다.

```text
barge_in_captured
barge_in_command_started
trigger_latency_seconds
interrupted
```

## 기존 기능 유지

```text
최신 명령 녹음 5개만 유지
GPT 우회 빠른 명령
Playwright 브라우저 도구
연속 대화
화면 분석
Windows 창·미디어·클립보드 제어
```

## 설치 및 실행

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m src.main
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Add interruptible TTS with barge-in voice capture"
```

## 다음 단계

다음은 **스트리밍 LLM + 스트리밍 TTS**입니다. GPT 답변 전체가 완성될 때까지
기다리지 않고 첫 문장이 생성되는 즉시 읽기 시작해서 체감 응답 시간을 더
줄입니다.
