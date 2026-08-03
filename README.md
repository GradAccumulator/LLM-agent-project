# LLM Agent — Step 21.4 + 22.1–22.3 + TTS 1.5×

다음 연결 작업을 한 번에 묶었습니다.

```text
Step 21.4
→ Windows 창 스크린샷 + UI Automation 요소 교차 분석

Step 22.1
→ remote debugging이 활성화된 Microsoft Edge에 CDP로 연결

Step 22.2
→ Edge 탭 목록·선택·승인 후 닫기

Step 22.3
→ 선택한 탭 DOM 본문 읽기·화면 캡처·현재 페이지 요약

TTS
→ 기본 발화 속도 +50%, 약 1.5배로 변경
```

## 1. TTS 속도

기본 설정:

```toml
[tts]
rate_percent = 50
```

시작 로그:

```text
TTS rate       : +50%
```

일시적으로 다른 속도를 사용할 때:

```powershell
python -m src.main --tts-rate 25
python -m src.main --tts-rate 50
```

## 2. Windows 창 화면과 UIA 교차 분석

새 도구:

```text
uia_capture_window_context
```

흐름:

```text
uia_find_windows
→ 정확한 window_id 선택
→ uia_capture_window_context
→ 창 이미지를 멀티모달 모델에 첨부
→ 같은 응답에 UIA 요소 이름·종류·bounds·element_ref 포함
```

가능한 요청:

```text
VSCode 오류 창을 화면과 UI 요소를 같이 보고 설명해줘
설정 창에서 저장 버튼이 어디 있는지 찾아줘
이 창에서 보이는 버튼과 실제 UIA 요소가 일치하는지 확인해줘
```

전체 화면은 기존 `inspect_screen`, 특정 창은
`uia_capture_window_context`를 우선 사용합니다.

## 3. Edge CDP 준비

이 기능은 임의의 평상시 Edge 프로세스에 몰래 붙지 않습니다.
Microsoft Edge에서 remote debugging이 활성화되어 있어야 합니다.

가장 단순한 실행 예:

```powershell
& "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe" `
  --remote-debugging-port=9222
```

Edge가 이미 실행 중이라 연결이 안 되면 모든 Edge 창을 닫은 뒤 위 명령으로
다시 실행합니다.

별도 프로필을 쓰는 예:

```powershell
& "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:LOCALAPPDATA\JarvisEdgeProfile"
```

또는 최신 Edge의 `edge://inspect`에서 현재 브라우저 인스턴스에 remote
debugging을 허용할 수 있는 환경이라면 그 방식을 사용해도 됩니다.

연결 확인:

```powershell
python -m src.main --edge-cdp-status
```

정상 예:

```json
{
  "enabled": true,
  "connected": true,
  "endpoint_url": "http://127.0.0.1:9222",
  "tab_count": 4,
  "error": null
}
```

연결되지 않았더라도 Jarvis 전체 실행은 가능하고, Edge CDP 도구를 사용할
때만 연결 오류를 반환합니다.

## 4. Edge 탭 기능

새 도구:

```text
edge_cdp_status
edge_cdp_list_tabs
edge_cdp_select_tab
edge_cdp_get_page_info
edge_cdp_capture_tab
edge_cdp_close_tab
```

가능한 요청:

```text
현재 열린 Edge 탭 목록 알려줘
유튜브 탭으로 전환해줘
지금 Edge 페이지 내용 요약해줘
현재 탭 화면도 같이 보고 설명해줘
이 탭 닫아줘
```

안전 정책:

```text
탭 목록·DOM 읽기·화면 캡처
→ 읽기 작업

탭 선택
→ 저위험 동작, 결과 검증

탭 닫기
→ 작성 중인 내용 손실 가능성이 있어 별도 "승인" 필요
```

`edge://settings`, `edge://extensions` 같은 내부 페이지는 정상 웹페이지와
같은 DOM 본문을 읽을 수 있다고 가정하지 않습니다.

## 5. 설정

```toml
[edge_cdp]
enabled = true
endpoint_url = "http://127.0.0.1:9222"
connect_timeout_seconds = 5.0
action_timeout_seconds = 10.0
max_page_text_characters = 16000
tab_ref_ttl_seconds = 300.0
screenshot_directory = "screenshots"
allow_tab_close = true

[windows_uia]
screenshot_directory = "screenshots"
```

Edge CDP 끄기:

```powershell
python -m src.main --disable-edge-cdp
```

탭 닫기만 끄기:

```powershell
python -m src.main --disable-edge-cdp-tab-close
```

로컬 endpoint만 허용합니다. 외부 IP의 CDP endpoint는 설정 단계에서
거부합니다.

## 6. 이미지 첨부

다음 신뢰된 도구의 `image_path`만 Responses API 멀티모달 입력으로
변환합니다.

```text
inspect_screen
uia_capture_window_context
edge_cdp_capture_tab
```

임의 도구가 반환한 로컬 파일 경로는 자동 첨부하지 않습니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

Linux 테스트 환경에서는 실제 Windows UIA와 실제 Edge 프로세스에 연결하지
않고 가짜 UIA·Playwright 객체로 탭 수명, DOM 읽기, 캡처, 승인, 닫힘 검증을
확인합니다.

## 커밋 메시지

```bash
git commit -m "Add Edge CDP page context and set TTS speed to 1.5x"
```

## 다음 단계 후보

다음 묶음은 안전 정책을 먼저 확장한 뒤 진행합니다.

```text
Edge DOM 요소 참조
저위험 링크·버튼 탐색
폼 입력 초안
제출·로그인·결제 요소 차단
DOM 실행 뒤 화면·URL·요소 상태 교차 검증
```

폼 제출, 메시지 전송, 구매·결제는 이번 단계에 포함하지 않았습니다.
