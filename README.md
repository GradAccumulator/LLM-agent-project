# LLM Agent — Step 13: Playwright Browser Automation + GPT Fast Path

이번 단계에서는 두 기능을 함께 추가했습니다.

- Playwright Chromium을 이용한 구조화된 브라우저 자동화
- 단순하고 명확한 명령은 GPT API를 거치지 않고 로컬에서 즉시 실행

## 설치

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Playwright 패키지와 Chromium 실행 파일은 별도로 설치해야 합니다.

## 브라우저 자동화 도구

```text
browser_open_page
browser_get_page_info
browser_list_elements
browser_click_text
browser_fill_field
browser_press_key
browser_go_back
browser_close
```

예시:

```text
Playwright 브라우저로 인하대 홈페이지 열어줘
현재 페이지의 링크 목록 보여줘
입학처라는 링크를 클릭해줘
검색 입력창에 인공지능공학과를 입력해줘
엔터 눌러줘
현재 페이지 내용을 읽고 요약해줘
```

브라우저는 기본 브라우저와 별개의 Playwright 관리 Chromium이며 로그인 상태는
`browser_profile/`에 저장됩니다.

안전 제한:

```text
http/https URL만 허용
다운로드 자동 수락 안 함
결제·구매·송금·삭제·메시지 전송 클릭 차단
비밀번호·카드·신원·계좌 입력 차단
임의 JavaScript 실행 없음
임의 셸 명령 없음
```

브라우저 자동화 끄기:

```powershell
python -m src.main --disable-browser-automation
```

백그라운드 브라우저:

```powershell
python -m src.main --browser-headless
```

## GPT를 거치지 않는 빠른 명령

다음처럼 의미가 명확한 명령은 정규식과 허용 목록으로 판별한 뒤 바로 로컬 도구를
실행합니다.

```text
지금 몇 시야
오늘 날짜 알려줘
계산기 켜줘
메모장 열어줘
VS Code 실행해줘
유튜브 열어줘
구글에서 Faster-Whisper 검색해줘
음량 내려줘
다음 곡
현재 창 최소화해줘
현재 활성 창 알려줘
열린 창 목록 보여줘
클립보드 내용 읽어줘
안녕하세요를 클립보드에 복사해줘
브라우저 뒤로 가
자동화 브라우저 닫아줘
```

로그 예시:

```text
FAST TOOL open_application({'application': 'calculator'}) -> success (0.012s)
FAST PATH [open_application:calculator | 0.012s | GPT bypassed]
```

해당 명령은 OpenAI API 요청이 없으므로 LLM 지연과 토큰 비용이 발생하지 않습니다.
모호하거나 설명·판단·화면 분석이 필요한 요청은 기존처럼 GPT로 전달됩니다.

빠른 명령 끄기:

```powershell
python -m src.main --disable-fast-path
```

설정 파일:

```toml
[browser]
enabled = true
headless = false
profile_directory = "browser_profile"
navigation_timeout_seconds = 20.0
action_timeout_seconds = 10.0
max_page_text_characters = 12000

[fast_path]
enabled = true
```

기존 설정인 녹음 파일 최신 5개 유지도 그대로 적용됩니다.

## 실행

```powershell
python -m src.main
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Add Playwright browser tools and local fast-path commands"
```

다음 주요 단계는 TTS 도중 사용자가 말하면 즉시 멈추는 **끼어들기 기능**입니다.
