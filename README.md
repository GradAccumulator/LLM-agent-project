# LLM Agent — Step 4: Local STT

`Hey Jarvis`를 감지한 뒤 명령을 녹음하고, Faster-Whisper로 로컬에서
한국어 텍스트로 변환합니다.

## 동작 흐름

```text
마이크 자동 선택
→ 장치 기본 샘플레이트로 입력
→ 16 kHz 리샘플링
→ "Hey Jarvis" 감지
→ Silero VAD로 명령 구간 녹음
→ Faster-Whisper로 로컬 STT
→ 터미널에 인식 문장 출력
→ 다시 웨이크워드 대기
```

## 설치

기존 가상환경에서 다음 명령을 실행합니다.

```powershell
python -m pip install -r requirements.txt
```

## 실행

```powershell
python -m src.main
```

첫 실행에서는 Faster-Whisper의 `turbo` 모델을 다운로드하므로 시간이
걸릴 수 있습니다. 모델은 기본적으로 `models/faster-whisper`에 저장됩니다.

## 기본 설정

- 웨이크워드: `Hey Jarvis`
- 웨이크워드 임계값: `0.45`
- VAD 임계값: `0.50`
- STT 모델: `turbo`
- STT 언어: 한국어 (`ko`)
- STT 장치: 자동 선택 (`CUDA` 우선, 실패 시 CPU)
- CUDA 연산 형식: `float16`
- CPU 연산 형식: `int8`
- Beam size: `5`
- 녹음 파일 저장: 활성화

## 실행 예시

```text
Say "Hey Jarvis". Press Ctrl+C to stop.

[07:50:12] WAKE WORD DETECTED | phrase=hey jarvis | score=0.812
COMMAND: waiting for speech...
COMMAND CAPTURED | duration=2.24s | peak VAD=0.998 | end=silence
Saved: recordings\command_20260801_075014_123456.wav
TRANSCRIBING...
TRANSCRIPT [ko 100.0% | 0.31s]: 유튜브에서 뉴진스 ETA 틀어줘.
```

## 주요 옵션

다른 Whisper 모델을 사용하려면:

```powershell
python -m src.main --stt-model small
python -m src.main --stt-model large-v3
```

CPU를 강제로 사용하려면:

```powershell
python -m src.main --stt-device cpu --stt-compute-type int8
```

CUDA를 강제로 사용하려면:

```powershell
python -m src.main --stt-device cuda --stt-compute-type float16
```

언어를 자동 감지하려면:

```powershell
python -m src.main --stt-language auto
```

녹음 WAV 파일을 남기지 않으려면:

```powershell
python -m src.main --no-save-audio
```

전체 옵션:

```powershell
python -m src.main --help
```

## CUDA 관련 참고

Faster-Whisper의 최신 CTranslate2는 CUDA 12와 cuDNN 9를 사용합니다.
이 프로젝트는 Windows에서 PyTorch의 DLL 폴더를 자동으로 등록하고,
`--stt-device auto`일 때 CUDA 초기화가 실패하면 CPU `int8`로 한 번
자동 재시도합니다.

CUDA를 반드시 사용해야 하는 상황에서 CPU로 폴백되면 터미널의 경고
메시지를 확인하세요.
