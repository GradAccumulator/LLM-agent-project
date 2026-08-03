# LLM Agent — Step 22.3.3: Automatic Microphone Recovery

Windows가 USB·무선 오디오 장치 번호를 바꿨을 때 고정된 `device = 18` 때문에
Jarvis가 종료되던 문제를 수정했습니다.

## 수정 전

```text
config/user.toml
→ device = 18

Windows 재부팅·헤드셋 재연결
→ BlackShark가 다른 번호로 이동

PortAudio
→ Invalid device [PaErrorCode -9996]
→ Jarvis 종료
```

## 수정 후

```text
저장된 장치 번호 확인
→ 실제 InputStream을 짧게 열어 사용 가능 여부 검사
→ 실패하면 같은 이름의 BlackShark 입력 장치 검색
→ WASAPI 등 안정적인 host API 후보 우선
→ 새 장치로 자동 전환
→ config/user.toml의 stale 숫자를 device = "auto"로 교체
→ 이후 실행부터 이름 기반으로 선택
```

시작 로그 예:

```text
Audio recovery  : [18] -> [21] 마이크 (BlackShark V3 Pro - Chat)
Audio config    : stale numeric device changed to device="auto"
Input device    : [21] 마이크 (BlackShark V3 Pro - Chat)
Device select   : preferred-name recovery
```

## 왜 실제로 스트림을 열어보나

`sounddevice.query_devices()`와 `check_input_settings()`가 성공해도 실제
`InputStream.start()`에서 장치 오류가 발생할 수 있습니다. 따라서 시작 초기에
후보 장치를 짧게 열고 닫아 PortAudio가 실제로 사용할 수 있는지 확인합니다.

실제 런타임 시작 시 장치 상태가 다시 바뀐 경우에도 한 번 더 자동 복구합니다.

## 기본 설정

```toml
[audio]
device = "auto"
preferred_device = "BlackShark"
device_recovery = true
probe_devices = true
persist_recovered_device = true
```

`auto`는 고정 번호를 강제하지 않고 `preferred_device` 이름으로 찾는다는 뜻입니다.

## 명시적 CLI 장치는 보존

다음처럼 사용자가 그 실행에서 직접 장치를 지정한 경우:

```powershell
python -m src.main --device 18
```

실패하면 자동 복구는 시도하지만 `config/user.toml`은 수정하지 않습니다.

## 기능 끄기

자동 복구 끄기:

```powershell
python -m src.main --disable-audio-device-recovery
```

시작 시 실제 스트림 probe 끄기:

```powershell
python -m src.main --disable-audio-probe-devices
```

복구하되 user.toml 자동 수정은 끄기:

```powershell
python -m src.main --no-persist-audio-recovery
```

## 지금 실행

새 ZIP으로 파일을 교체한 다음:

```powershell
python -m src.main
```

현재 `config/user.toml`에 `device = 18`이 남아 있어도 첫 실행에서 자동으로
정상 장치를 찾아 `device = "auto"`로 고칩니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

테스트 범위:

```text
stale numeric index → preferred-name recovery
실제 InputStream probe 실패 → 다음 후보 선택
런타임 start 시 장치 실패 → 한 번 재검색 후 재시작
user.toml device = 18 → device = "auto" 원자적 수정
CLI --device 사용 시 config 자동 수정 차단
Windows 환경의 여러 host API 후보 정렬
```

## 커밋 메시지

```bash
git commit -m "Recover automatically from stale microphone device indices"
```
