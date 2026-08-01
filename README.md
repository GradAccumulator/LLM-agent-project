# LLM Agent — Step 12: Windows Desktop Control + Audio Retention

이번 단계에서는 안전한 Windows 제어 도구를 추가하고, 녹음된 명령 음성은
최신 5개만 남기도록 변경했습니다.

## 새 Windows 도구

```text
get_active_window
list_open_windows
focus_window
set_window_state
media_control
get_clipboard_text
set_clipboard_text
```

가능한 요청 예시:

```text
지금 활성화된 창이 뭐야?
열려 있는 VS Code 창 목록 보여줘
방금 찾은 VS Code 창으로 전환해줘
현재 창 최소화해줘
음악 일시정지해줘
다음 곡으로 넘겨줘
음량 한 단계 낮춰줘
클립보드 내용 읽어줘
이 문장을 클립보드에 복사해줘
```

창 전환과 상태 변경은 `list_open_windows`가 반환한 `window_id`를 기준으로
수행합니다. 임의 키 입력, 좌표 클릭, 셸 명령 실행은 넣지 않았습니다.

클립보드 읽기·쓰기와 창 조작은 사용자가 명시적으로 요청했을 때만
실행하도록 자비스의 시스템 지침도 강화했습니다.

## 음성 파일은 최신 5개만 유지

기본 설정:

```toml
[audio]
save_audio = true
save_directory = "recordings"
max_saved_files = 5
```

프로그램 시작 시 기존 `command_*.wav`를 정리하고, 새 음성을 저장한 뒤에도
다시 정리합니다. `command_*.wav` 형식만 정리하므로 같은 폴더의 다른 WAV
파일은 삭제하지 않습니다.

개수 변경:

```powershell
python -m src.main --max-saved-audio-files 10
```

녹음을 아예 저장하지 않기:

```powershell
python -m src.main --no-save-audio
```

## 설치 및 실행

새 외부 패키지는 필요하지 않습니다. 창과 클립보드 제어는 Python 표준
라이브러리의 Windows API 호출로 구현했습니다.

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Add safe Windows desktop tools and audio retention"
```

다음 주요 단계는 **Playwright 브라우저 자동화**입니다.
