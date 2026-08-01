# LLM Agent — Step 16.2: Normal Edge Window Control

## Step 16.2.1 — Barge-in 상태 전환 핫픽스

다음 오류를 수정했습니다.

```text
Invalid transition CAPTURING -> SLEEPING
```

대화 최대 턴에 도달한 순간 사용자가 TTS를 끊으면 캡처된 음성을 처리하지
않고 수면 상태로 전환하던 조건문이 원인이었습니다.

```text
SPEAKING
→ 사용자 끼어들기
→ CAPTURING
→ 기존 답변 종료
→ 최대 턴이면 새 대화 세션으로 자동 롤오버
→ CAPTURING → TRANSCRIBING
→ 끼어든 명령 처리
```

바지인 결과가 상태 전환보다 조금 늦게 도착하는 경쟁 조건도 방어적으로
수집합니다. `CAPTURING → SLEEPING`을 무작정 허용하지 않아 캡처된 음성이
STT 전에 버려지지 않습니다.

Google 로그인 오류는 Windows 권한 문제가 아니라 Google이 Playwright
브라우저를 자동화 환경으로 판단해서 발생한 문제입니다.

이번 버전의 기본값은 **평소 사용하는 일반 Microsoft Edge 프로필**입니다.

```toml
[browser]
control_mode = "system"
browser = "msedge"
```

## 동작

```text
유튜브 열어줘
→ 설치된 msedge.exe --new-window 실행
→ 평소 Edge의 쿠키·로그인·확장 프로그램 사용
→ Jarvis가 새 창 ID 기록
```

이제 새 창에서 Google 또는 YouTube에 평소처럼 직접 로그인할 수 있습니다.

## 닫기

```text
브라우저 닫아줘
엣지 창 닫아줘
```

Jarvis는 **이번 실행에서 자신이 연 창만** 닫습니다. 사용자가 원래 열어 둔
Edge 창은 닫지 않습니다.

추가 도구:

```text
list_jarvis_browser_windows
close_jarvis_browser_window
```

## Playwright가 필요한 작업

DOM 기반 페이지 읽기·입력·클릭이 필요하면 설정을 바꿉니다.

```toml
[browser]
control_mode = "automation"
browser = "msedge"
```

`automation` 모드는 자동화 전용 프로필이므로 Google 로그인 경고가 다시
나타날 수 있습니다.

## 실행

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

## 커밋 메시지

```bash
git commit -m "Open and close normal user browser windows safely"
```

## 다음 단계

다음은 **Step 17: 로컬 장기 메모리와 사용자 별칭**입니다. 사용자가
명시적으로 기억하라고 한 경로·사이트·브라우저 선호를 SQLite에 저장합니다.
