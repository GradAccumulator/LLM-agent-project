# LLM Agent — Step 7.2.1: CUDA DLL Hotfix

음성 인식과 음성 출력의 체감 지연을 줄인 성능 우선 버전입니다.

## 핵심 변경

### 명령이 끝났다고 판단하는 시간

```text
기존: 0.8초 침묵
변경: 0.4초 침묵
```

말을 끝낸 뒤 STT가 시작되기까지 기다리는 시간을 약 0.4초 줄였습니다.

### Faster-Whisper

```text
모델: turbo
장치: CUDA 우선 자동 선택
연산: float16
beam size: 1
best_of: 1
CPU fallback threads: 16
workers: 2
startup warm-up: 활성화
timestamps: 비활성화
```

첫 명령에서 CUDA 초기화 때문에 느려지는 현상을 줄이기 위해 프로그램 시작
시 무음 추론을 한 번 수행합니다.

### Edge Neural TTS

기존 구현은 답변마다 새 Python 프로세스를 실행해 `edge-playback`을
호출했습니다. 이번 버전은:

```text
Edge TTS Python API를 프로세스 안에서 직접 사용
pygame 오디오 믹서를 시작할 때 한 번만 초기화
첫 문장을 짧은 조각으로 분리
뒤쪽 문장들은 최대 3개 요청으로 병렬 합성
첫 조각이 준비되는 즉시 재생
```

따라서 긴 답변 전체의 음성이 완성될 때까지 기다리지 않고, 먼저 생성된
첫 부분부터 읽기 시작합니다.


## CUDA DLL 자동 탐색 및 폴백 수정

Windows에서 다음 폴더들을 자동으로 DLL 검색 경로에 등록합니다.

```text
CUDA_PATH\bin
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin
C:\Program Files\NVIDIA\CUDNN\v*\bin\*
PyTorch의 torch\lib
```

또한 CTranslate2가 모델 생성 때가 아니라 첫 추론 시 CUDA DLL을 불러오는
경우를 처리했습니다. 기본 `--stt-device auto`에서는 GPU 워밍업이 실패해도
프로그램이 종료되지 않고 CPU `int8`로 다시 초기화됩니다.

GPU 가속을 사용하려면 Windows에 다음 DLL이 실제로 설치되어 있어야 합니다.

```text
cublas64_12.dll
cudnn_ops64_9.dll
```

확인:

```powershell
where.exe cublas64_12.dll
where.exe cudnn_ops64_9.dll
```

CUDA Toolkit 경로에 파일이 있지만 `where.exe`에서 찾지 못한다면 현재
PowerShell에서 임시로 다음처럼 추가할 수 있습니다.

```powershell
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin;$env:PATH"
python -m src.main
```


## 설치

```powershell
python -m pip install -r requirements.txt
```

## 실행

```powershell
python -m src.main
```

## 기본 저지연 설정

```text
end silence       : 0.4초
STT beam          : 1
STT best-of       : 1
STT compute       : float16
STT warm-up       : 활성화
첫 TTS 조각       : 최대 80자
이후 TTS 조각     : 최대 180자
TTS 병렬 요청     : 3
오디오 버퍼       : 256
```

## 더 공격적으로 줄이기

```powershell
python -m src.main `
  --end-silence 0.32 `
  --tts-first-chunk-characters 55 `
  --tts-chunk-characters 140 `
  --tts-parallel-requests 4
```

`--end-silence`를 너무 낮추면 문장 중간의 짧은 쉼을 명령 종료로 잘못 판단할
수 있습니다. 기본값 0.4초부터 테스트하는 것을 권장합니다.

## 정확도를 조금 올리고 싶을 때

속도 대신 STT 정확도를 조금 더 우선하려면:

```powershell
python -m src.main --stt-beam-size 3 --stt-best-of 3
```

## 성능 확인

STT 출력:

```text
TRANSCRIPT [ko 100.0% | 0.21s]: 계산기 켜줘
```

TTS 출력:

```text
TTS LATENCY: first_audio=0.63s | chunks=2 | total=3.14s
```

`first_audio`가 GPT 답변 생성 후 실제 음성이 시작되기까지의 핵심 수치입니다.

## 참고

Edge TTS의 음성 생성은 온라인 서비스이므로 RTX 5090 사용률을 높이는 것만으로
네트워크 왕복 지연까지 줄일 수는 없습니다. 대신 이번 버전에서는 프로세스
실행 비용을 없애고, 짧은 조각과 병렬 요청으로 첫 음성이 더 빨리 나오도록
구조를 바꿨습니다.

## 커밋 메시지

```bash
git commit -m "Fix Windows CUDA DLL discovery and STT warm-up fallback"
```
