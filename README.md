# LLM Agent — Step 7: Local Text-to-Speech

자비스가 GPT 답변을 터미널에 출력하는 것뿐 아니라 Windows 기본 스피커로
직접 읽어줍니다.

## 전체 흐름

```text
"Hey Jarvis"
→ Silero VAD 명령 녹음
→ Faster-Whisper 로컬 STT
→ GPT 추론 및 로컬 도구 호출
→ 필요하면 현재 화면 캡처·분석
→ GPT 최종 답변
→ Windows SAPI5 로컬 TTS
→ 다시 웨이크워드 대기
```

TTS는 OpenAI 음성 API를 호출하지 않습니다. Windows에 설치된 SAPI 음성을
사용하므로 음성 합성 자체는 로컬에서 실행됩니다.

## 설치

```powershell
python -m pip install -r requirements.txt
```

## 실행

```powershell
python -m src.main
```

기본 설정:

- 웨이크워드: `Hey Jarvis`
- 웨이크워드 임계값: `0.45`
- TTS: 활성화
- TTS 엔진: Windows SAPI5
- 음성 선택: 설치된 한국어 음성을 우선 자동 선택
- 말하기 속도: `0`
- 음량: `100`
- 최대 낭독 길이: `1200`자

## 설치된 음성 확인

```powershell
python -m src.main --list-tts-voices
```

예시:

```text
[0] Microsoft Heami Desktop (language=412)  [selected]
[1] Microsoft David Desktop (language=409)
```

특정 음성을 선택하려면 이름 일부를 넘깁니다.

```powershell
python -m src.main --tts-voice "Heami"
```

해당 음성이 목록에 없다면 Windows 언어 및 음성 설정에서 한국어 음성
패키지를 설치해야 할 수 있습니다.

## 속도와 음량

```powershell
python -m src.main --tts-rate 1
python -m src.main --tts-rate -1
python -m src.main --tts-volume 80
```

속도 범위:

```text
-10 ~ 10
```

음량 범위:

```text
0 ~ 100
```

## 음성 출력 끄고 시작하기

```powershell
python -m src.main --disable-tts
```

실행 중에도 음성으로 전환할 수 있습니다.

```text
음성 출력 꺼줘
음성 출력 켜줘
TTS 꺼줘
TTS 켜줘
```

## 긴 답변 처리

긴 코드 블록과 URL은 그대로 읽지 않고 화면에 출력합니다. 답변이 기본
`1200`자를 넘으면 앞부분까지만 읽은 뒤 자세한 내용은 화면에 출력했다고
알립니다.

```powershell
python -m src.main --tts-max-characters 2000
```

## 자비스가 자기 목소리를 다시 인식하지 않도록 한 처리

TTS가 말하는 동안 마이크 인식 루프는 다음 명령을 처리하지 않습니다.
낭독이 끝난 뒤 마이크 대기 큐와 웨이크워드 상태를 초기화하므로 스피커에서
나온 자비스 음성이 다음 명령으로 들어가는 가능성을 줄였습니다.

## 실행 예시

```text
TRANSCRIPT: 지금 화면의 오류가 왜 나는지 알려줘
THINKING...
TOOL inspect_screen({'display': 'primary'})
TOOL RESULT: success
JARVIS:
화면에 ModuleNotFoundError가 보입니다. 현재 가상환경에 해당 패키지가
설치되지 않은 것이 원인입니다.
TTS:
위 답변을 Windows 음성으로 읽음
```

## 커밋 메시지

```bash
git commit -m "Add local Windows text-to-speech responses"
```
