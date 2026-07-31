# LLM Agent — Step 1: Microphone stream

첫 번째 목표는 웨이크워드 모델을 붙이기 전에 마이크 입력이 안정적으로 들어오는지 확인하는 것입니다.

## 설치

PowerShell에서 가상환경을 활성화한 뒤:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 실행

입력 장치 목록 확인:

```powershell
python -m src.main --list-devices
```

기본 마이크로 테스트:

```powershell
python -m src.main
```

특정 장치 선택:

```powershell
python -m src.main --device 3
```

정상 동작하면 말할 때 콘솔의 음량 막대가 움직입니다. 종료는 `Ctrl+C`입니다.

## 완료 기준

- 프로그램이 오류 없이 계속 실행된다.
- 말하거나 박수를 치면 음량 막대가 움직인다.
- 조용할 때 막대가 거의 내려간다.
- `Ctrl+C`로 정상 종료된다.

이 단계에서는 음성을 파일로 저장하거나 인터넷으로 전송하지 않습니다.
