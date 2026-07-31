# LLM Agent — Step 2: Wake-word detection

마이크의 16 kHz mono PCM 스트림을 로컬 `openWakeWord` 모델에 전달해
`Hey Jarvis`를 감지합니다.

## 이번 단계에서 하는 일

```text
마이크 입력
    ↓
80 ms 오디오 프레임
    ↓
openWakeWord
    ↓
"Hey Jarvis" 감지
```

아직 음성인식, GPT, 컴퓨터 조작, 음성합성은 붙이지 않습니다.

## 1. 패키지 설치

가상환경이 활성화된 PowerShell에서:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

설치 중 호환성 오류가 발생하면 먼저 확인합니다.

```powershell
python --version
```

이 프로젝트는 Python 3.10 이상을 전제로 합니다. 최신 패키지의 Windows
휠 문제로 설치가 막히는 경우 Python 3.12 가상환경이 가장 무난합니다.

## 2. 입력 장치 확인

```powershell
python -m src.main --list-devices
```

## 3. 실행

```powershell
python -m src.main
```

첫 실행 시 사전 학습된 모델 파일을 한 번 다운로드하므로 인터넷이 필요합니다.
그 이후 감지는 로컬에서 실행됩니다.

기본 마이크가 아니라면:

```powershell
python -m src.main --device 3
```

## 4. 테스트

영어식으로 짧고 분명하게 말합니다.

```text
Hey Jarvis
```

정상 감지되면 다음과 같이 출력되고 알림음이 납니다.

```text
WAKE WORD DETECTED | phrase=hey jarvis | score=0.842
```

종료는 `Ctrl+C`입니다.

## 민감도 조절

기본 임계값은 `0.5`입니다.

자주 놓치면:

```powershell
python -m src.main --threshold 0.35
```

상관없는 말에 반응하면:

```powershell
python -m src.main --threshold 0.65
```

임계값은 한 번에 크게 바꾸지 말고 `0.05`씩 조절하는 편이 좋습니다.

## 장치 선택 예시

장치 번호 3, 임계값 0.45:

```powershell
python -m src.main --device 3 --threshold 0.45
```

## 완료 기준

- 가까운 거리에서 `Hey Jarvis`를 20번 말했을 때 대부분 감지한다.
- 한 번 말했을 때 감지 메시지가 여러 번 연속 출력되지 않는다.
- 아무 말 없이 켜뒀을 때 오탐이 거의 없다.
- `Ctrl+C`로 정상 종료된다.

현재 포함된 모델은 영어 `Hey Jarvis`용입니다. 한국어식 `자비스` 전용
커스텀 모델은 전체 파이프라인이 안정화된 뒤 교체할 수 있습니다.
