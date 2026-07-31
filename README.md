# LLM Agent — Step 6.2: Screen Vision

자비스가 현재 화면을 캡처한 뒤 그 이미지를 GPT에 전달해 실제 화면 내용을
보고 답변합니다.

## 동작 흐름

```text
"Hey Jarvis"
→ 음성 명령 인식
→ GPT가 현재 화면 확인이 필요하다고 판단
→ inspect_screen 도구 호출
→ 주 모니터 또는 전체 데스크톱을 PNG로 캡처
→ 캡처 이미지를 OpenAI Responses API의 input_image로 전달
→ GPT가 화면을 분석
→ 화면을 근거로 최종 답변
```

## 가능한 명령 예시

```text
지금 화면에 뭐가 보여?
이 오류가 왜 발생한 거야?
화면에 나온 코드에서 문제점을 찾아줘
현재 열려 있는 설정이 맞는지 봐줘
모든 모니터 화면을 보고 어디에 창이 열려 있는지 알려줘
```

`화면 캡처해줘`라고 말하면 화면을 캡처하고, 캡처한 화면에 무엇이 보이는지도
간단히 설명합니다.

## 등록 도구

이번 버전에서는 기존 `capture_screenshot` 대신 `inspect_screen`을 사용합니다.

```text
inspect_screen(display="primary")
inspect_screen(display="all")
```

- `primary`: 주 모니터만 확인
- `all`: 모든 모니터를 포함한 전체 데스크톱 확인
- 캡처 파일: `screenshots/`
- 전송 형식: Base64 PNG image input
- 기본 이미지 디테일: `original`

화면의 작은 글자, 오류 메시지와 코드를 읽는 데 유리하도록 기본값은
`original`입니다. 비용이나 지연을 줄이려면 다음처럼 바꿀 수 있습니다.

```powershell
python -m src.main --vision-detail high
python -m src.main --vision-detail low
```

## 설치 및 실행

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

## API 키

프로젝트 루트에 `.env`를 만들고 API 키를 넣습니다.

```dotenv
OPENAI_API_KEY=your_api_key_here
```

## 개인 정보 주의

화면 분석을 요청하면 캡처 시점에 화면에 보이는 내용이 이미지 입력으로 API에
전송됩니다. 비밀번호, 인증 코드, 개인 메시지처럼 보내고 싶지 않은 정보는
화면에서 닫거나 가린 뒤 요청하세요.

## 실행 예시

```text
TRANSCRIPT: 이 오류가 왜 나는지 화면 보고 알려줘
THINKING...
TOOL inspect_screen({'display': 'primary'})
TOOL RESULT: success
JARVIS:
화면의 터미널에 ModuleNotFoundError가 보입니다. 현재 가상환경에 해당
패키지가 설치되지 않은 것이 원인이므로 requirements.txt를 설치하세요.
```

## 커밋 메시지

```bash
git commit -m "Add GPT screen vision with screenshot tool output"
```
