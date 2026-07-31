# LLM Agent — Step 2.2

입력 마이크를 자동으로 선택하고, 장치의 기본 샘플레이트를 16 kHz로
리샘플링한 뒤 `Hey Jarvis`를 감지합니다.

## 설치

```powershell
python -m pip install -r requirements.txt
```

## 실행

```powershell
python -m src.main
```

자동 선택 순서:

1. Windows/PortAudio 기본 입력 장치
2. 이름에 `BlackShark`와 `마이크` 또는 `Microphone`이 포함된 장치
3. 사용 가능한 첫 입력 장치

직접 지정도 계속 가능합니다.

```powershell
python -m src.main --device 18
```

원하는 장치 이름 힌트를 바꾸려면:

```powershell
python -m src.main --prefer-device "Realtek"
```
