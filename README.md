# LLM Agent — Step 16.1: Selectable Installed Browser

Playwright 전용 Chromium 대신 PC에 설치된 **Microsoft Edge를 기본값**으로
사용합니다. Chrome 또는 다른 Chromium 기반 브라우저도 설정 파일에서
선택할 수 있습니다.

## 기본 설정: Microsoft Edge

`config/default.toml`:

```toml
[browser]
enabled = true
headless = false
browser = "msedge"
executable_path = ""
profile_directory = "browser_profiles"
```

이 설정은 Playwright의 `msedge` 채널을 통해 PC에 설치된 Microsoft Edge를
실행합니다. 별도의 Playwright Chromium 설치는 필요하지 않습니다.

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

## Google Chrome으로 변경

`config/user.toml`:

```toml
[browser]
browser = "chrome"
executable_path = ""
```

또는 한 번만 CLI에서 변경:

```powershell
python -m src.main --browser chrome
```

## 다른 Chromium 기반 브라우저

Brave, Vivaldi, Opera처럼 Chromium 기반인 브라우저는 실행 파일 경로를
지정합니다.

```toml
[browser]
browser = "custom"
executable_path = 'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe'
```

CLI:

```powershell
python -m src.main `
  --browser custom `
  --browser-executable "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
```

Playwright는 임의 실행 파일과의 완전한 호환성을 보장하지 않으므로
**Chromium 기반 브라우저만** 대상으로 합니다. 일반 설치형 Firefox를
`custom` 경로로 지정하는 방식은 지원하지 않습니다.

## 설치된 브라우저 확인

```powershell
python -m src.main --list-browsers
```

Edge, Chrome과 일반적인 Brave·Vivaldi·Opera 설치 위치를 검사합니다.

## 빠른 명령도 같은 브라우저 사용

다음 명령도 이제 Windows 기본 브라우저가 아니라 `[browser]`에서 선택한
브라우저를 사용합니다.

```text
브라우저 열어줘
유튜브 열어줘
구글에서 Faster-Whisper 검색해줘
```

즉 fast path 명령과 Playwright 자동화 명령이 같은 Edge/Chrome 창과 같은
자동화 프로필을 공유합니다.

## 브라우저별 프로필 분리

설정의 `profile_directory`는 기준 폴더입니다.

```text
browser_profiles/
├── msedge/
├── chrome/
└── custom-brave/
```

Edge에서 Chrome으로 바꿔도 쿠키와 로그인 상태가 섞이지 않습니다.

이 프로필은 평소 사용하는 Edge 기본 프로필과 **분리된 자동화 전용
프로필**입니다. 평소 Edge 프로필을 그대로 사용하면 이미 실행 중인 Edge와
충돌하거나 프로필 잠금이 발생할 수 있어 기본 구조에서는 사용하지 않습니다.

## Playwright Chromium을 다시 선택

필요한 경우에만:

```toml
[browser]
browser = "chromium"
```

이 선택에서만 별도 설치가 필요합니다.

```powershell
python -m playwright install chromium
```

## 커밋 메시지

```bash
git commit -m "Use configurable installed browsers for web automation"
```

## 다음 단계

다음은 기존 로드맵의 **Step 17: 로컬 장기 메모리와 사용자 별칭**입니다.

```text
"내 LLM 프로젝트" → 프로젝트 폴더
"학교 사이트" → 인하대 포털
"기본 브라우저는 Edge로 기억해" → 브라우저 선호
```

명시적으로 기억하라고 한 별칭과 선호만 SQLite에 저장해 다음 실행에서도
유지하게 됩니다.
