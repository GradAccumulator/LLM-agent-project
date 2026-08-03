# LLM Agent — Step 22.3.1: Managed Jarvis Edge Profile

Jarvis가 시작될 때 **전용 Microsoft Edge 프로필을 자동 실행**하고,
항상 로컬 CDP 포트로 연결할 수 있도록 만들었습니다.

이제 매번 직접 다음 명령을 실행할 필요가 없습니다.

```text
msedge.exe --remote-debugging-port=9222
```

## 기본 동작

```text
Jarvis 시작
→ 127.0.0.1:9222 /json/version 확인
→ 이미 전용 Edge가 실행 중이면 재사용
→ 없으면 Edge 실행 파일 자동 탐색
→ data/edge_profile 생성 또는 재사용
→ --remote-debugging-port=9222
→ --user-data-dir=data/edge_profile
→ CDP 준비 완료까지 대기
→ Playwright CDP 연결
```

일반 Edge 프로필과 별도의 user-data-dir을 사용하므로, 평소 사용하는 Edge가
이미 켜져 있어도 Jarvis 전용 Edge를 별도 인스턴스로 시작할 수 있습니다.

## 최초 실행

새 버전으로 교체한 뒤 평소처럼 실행하면 됩니다.

```powershell
python -m src.main
```

시작 중 다음 로그가 표시됩니다.

```text
Managed Edge   : started / ready
Edge profile   : data\edge_profile
Edge auto start: enabled
```

이미 실행 중이면:

```text
Managed Edge   : reused / ready
```

## Edge만 먼저 시작하거나 확인

명시적으로 시작:

```powershell
python -m src.main --edge-cdp-start
```

상태 확인:

```powershell
python -m src.main --edge-cdp-status
```

자동 시작이 켜져 있으므로 상태 확인 시 전용 Edge가 없으면 먼저 시작합니다.

자동 시작 없이 현재 상태만 확인하려면:

```powershell
python -m src.main `
  --edge-cdp-status `
  --disable-edge-cdp-auto-start
```

## 로그인과 세션 유지

첫 실행 때 열린 Jarvis 전용 Edge에서 필요한 사이트에 직접 로그인합니다.
쿠키와 세션은 다음 디렉터리에 유지됩니다.

```text
data/edge_profile
```

기본적으로 이전 세션 복원 플래그를 사용하며, Jarvis가 종료되어도 전용 Edge는
계속 실행됩니다.

```toml
restore_last_session = true
keep_running_on_exit = true
```

이 프로필에는 쿠키, 로그인 세션, 방문 기록 등 민감한 브라우저 데이터가
들어갈 수 있으므로 Git과 ZIP에서 제외됩니다.

## 설정

```toml
[edge_cdp]
enabled = true
endpoint_url = "http://127.0.0.1:9222"

auto_start = true
executable_path = ""
profile_directory = "data/edge_profile"
startup_timeout_seconds = 15.0
startup_poll_seconds = 0.2
startup_url = ""
restore_last_session = true
keep_running_on_exit = true
```

Edge를 자동으로 찾지 못할 때:

```toml
executable_path = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
```

또는:

```powershell
python -m src.main `
  --edge-cdp-executable `
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
```

자동 시작 끄기:

```powershell
python -m src.main --disable-edge-cdp-auto-start
```

Jarvis가 이번에 직접 실행한 Edge를 종료 시 같이 끄기:

```powershell
python -m src.main --edge-cdp-stop-on-exit
```

기본값은 세션 유지를 위해 계속 실행입니다.

## 바탕화면 바로가기

선택적으로 다음 스크립트를 한 번 실행하면 바탕화면에 `Jarvis Edge` 바로가기를
만들 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts\create_jarvis_edge_shortcut.ps1
```

해당 바로가기는 프로젝트의 가상환경을 우선 사용해 전용 Edge를 시작합니다.

## 포트 충돌 보호

9222 포트가 열려 있지만 정상적인 Edge CDP `/json/version` 응답이 아니라면,
Jarvis는 다른 프로세스를 종료하지 않고 실행을 중단합니다.

```text
Port 9222 is already occupied...
```

이 경우 다른 포트를 설정합니다.

```toml
endpoint_url = "http://127.0.0.1:9333"
```

실행 명령의 `--remote-debugging-port`도 자동으로 9333으로 맞춰집니다.

## 정책 오류

시작은 됐지만 CDP가 준비되지 않는 경우:

```text
edge://policy
→ RemoteDebuggingAllowed
```

를 확인합니다. 회사나 학교 정책으로 remote debugging이 비활성화되어 있으면
Jarvis가 이를 우회하지 않습니다.

## 새 내부 도구

```text
edge_cdp_managed_status
edge_cdp_start_managed
```

사용 예:

```text
Jarvis 전용 Edge 상태 알려줘
Jarvis Edge 켜줘
현재 열린 Edge 탭 목록 알려줘
```

## 검증

```powershell
python -m unittest discover -s tests -v
```

Linux 테스트 환경에서는 실제 Edge를 시작하지 않고 가짜 포트 탐지기,
프로세스 실행기, CDP 응답으로 다음 흐름을 검사합니다.

```text
실행 파일 탐색
명령 인수 생성
전용 프로필 생성
준비 상태 polling
이미 실행 중인 Edge 재사용
포트 충돌 차단
자동 시작 후 CDP attach
종료 시 세션 유지
```

## 커밋 메시지

```bash
git commit -m "Add auto-started dedicated Edge CDP profile"
```

## 다음 단계

다음 묶음에서는 기존 계획으로 돌아갑니다.

```text
Edge DOM 요소 참조
안전한 링크·버튼 탐색
일반 텍스트 입력
DOM 동작 뒤 URL·화면·요소 상태 검증
제출·전송·로그인·결제 요소 차단
```
