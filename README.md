# LLM Agent — Step 22.3.4: WDM-KS Callback Probe Fix

BlackShark V3 Pro 마이크가 장치 목록에 정상적으로 존재하고
`check_input_settings()`도 통과하지만 다음 오류로 자동 검사에서 탈락하던
문제를 수정했습니다.

```text
Blocking API not supported yet
Windows WDM-KS error -9999
```

## 원인

`sounddevice.InputStream`에 callback을 전달하지 않으면 PortAudio의
blocking read/write 모드로 열립니다.

이전 자동 검사:

```python
sd.InputStream(
    device=device,
    samplerate=48000,
    channels=1,
    dtype="int16",
)
```

사용자의 BlackShark WDM-KS 장치는 callback 스트림은 사용할 수 있지만
blocking API는 지원하지 않아, 실제 Jarvis에서 사용할 수 있는 마이크가
검사 단계에서 잘못 제외됐습니다.

실제 Jarvis 런타임은 원래 callback 기반입니다. 따라서 자동 검사도
런타임과 동일하게 수정했습니다.

```python
sd.InputStream(
    device=device,
    samplerate=48000,
    channels=1,
    dtype="int16",
    blocksize=3840,
    callback=probe_callback,
)
```

## 적용 후 흐름

```text
장치 18 확인
→ check_input_settings
→ callback 방식 InputStream 생성
→ start / stop / close
→ 성공하면 BlackShark WDM-KS 선택
→ 실제 Jarvis도 callback 방식으로 시작
```

예상 로그:

```text
Input device   : [18] 마이크 (BlackShark V3 Pro - Chat)
Device select  : requested device
Audio recovery : enabled / probe=callback
```

숫자 장치가 실제로 바뀌었을 때는 이전 단계의 이름 기반 자동 복구도 그대로
유지됩니다.

## 실행

새 ZIP의 파일을 프로젝트에 덮어쓴 뒤:

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m src.main
```

장치 번호 변경에 강한 설정:

```toml
[audio]
device = "auto"
preferred_device = "BlackShark"
device_recovery = true
probe_devices = true
```

## callback 방식 단독 테스트

```powershell
python -c "import sounddevice as sd; cb=lambda i,f,t,s: None; x=sd.InputStream(device=18,channels=1,samplerate=48000,dtype='int16',callback=cb); x.start(); print('callback stream started'); x.stop(); x.close()"
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

회귀 테스트는 같은 가짜 WDM-KS 장치가:

```text
callback 없음 → Blocking API not supported yet
callback 있음 → 정상 개방
```

으로 동작하도록 만들어, 자동 검사에서 callback 전달을 강제합니다.

## 커밋 메시지

```bash
git commit -m "Probe WDM-KS microphones with callback streams"
```
