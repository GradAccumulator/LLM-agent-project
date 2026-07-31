# LLM Agent — Step 6: GPT Tool Calling

`Hey Jarvis`로 명령을 받은 뒤 GPT가 필요한 로컬 도구를 선택하고,
도구 실행 결과를 다시 GPT에 전달해 최종 답변을 생성합니다.

## 전체 흐름

```text
마이크 자동 선택
→ "Hey Jarvis" 감지
→ Silero VAD 명령 녹음
→ Faster-Whisper 로컬 STT
→ GPT가 도구 사용 여부 판단
→ 로컬 Python 도구 실행
→ 실행 결과를 GPT에 반환
→ 최종 답변을 터미널에 출력
```

OpenAI Responses API의 function calling 흐름을 사용합니다.

```text
사용자 명령
→ GPT function_call
→ 로컬 함수 실행
→ function_call_output
→ GPT 최종 응답
```

## 이번 단계에서 실제로 가능한 작업

### 앱 열기

지원 앱:

- 계산기
- 메모장
- 파일 탐색기
- Windows 설정
- 기본 브라우저
- VS Code
- 터미널

예시:

```text
계산기 켜줘
메모장 열어줘
VS Code 실행해줘
```

### 웹사이트 열기

지원 사이트:

- YouTube
- Google
- Naver
- GitHub
- ChatGPT
- OpenAI

예시:

```text
유튜브 열어줘
깃허브 열어줘
```

### 브라우저 검색

Google, Naver, YouTube 검색을 기본 브라우저에서 엽니다.

```text
유튜브에서 뉴진스 ETA 검색해줘
구글에서 파이썬 GIL 검색해줘
```

### 시스템 상태 조회

CPU, RAM, 디스크, 배터리와 사용 가능한 경우 NVIDIA GPU 상태를 읽습니다.

```text
컴퓨터 상태 알려줘
그래픽카드 온도 알려줘
```

### 시간 조회

```text
지금 몇 시야?
오늘 날짜 알려줘
```

### 메모 저장

프로젝트의 `notes/` 폴더에 Markdown 파일을 생성합니다.

```text
내일 텐서보드 로거 수정하기라고 메모해줘
```

## 안전 설계

이번 단계에서는 GPT가 임의의 PowerShell, CMD 또는 Python 코드를 실행할 수
없습니다. 앱과 사이트는 허용 목록으로 제한되어 있고, 임의 파일 삭제나
프로세스 종료 기능도 넣지 않았습니다.

## 설치

```powershell
python -m pip install -r requirements.txt
```

## API 키 설정

```powershell
Copy-Item .env.example .env
```

`.env`:

```dotenv
OPENAI_API_KEY=your_api_key_here
```

## 실행

```powershell
python -m src.main
```

기본값:

- 호출어: `Hey Jarvis`
- 웨이크워드 임계값: `0.45`
- STT: Faster-Whisper `turbo`
- LLM: `gpt-5.6-luna`
- Reasoning: `low`
- Tool choice: `auto`
- 한 명령당 최대 도구 라운드: `4`
- 대화 기억: 활성화

## 도구 관련 옵션

도구를 완전히 끄기:

```powershell
python -m src.main --disable-tools
```

최대 도구 라운드 변경:

```powershell
python -m src.main --llm-max-tool-rounds 6
```

## 실행 예시

```text
TRANSCRIPT [ko 100.0% | 0.28s]: 계산기 켜줘
THINKING...
TOOL open_application({"application": "calculator"})
TOOL RESULT: success
JARVIS [gpt-5.6-luna | 1.03s | 150→35 tokens | tools=1]:
계산기를 열었습니다.
```

```text
TRANSCRIPT [ko 100.0% | 0.31s]: 컴퓨터 상태 알려줘
THINKING...
TOOL get_system_status({})
TOOL RESULT: success
JARVIS [...]:
현재 CPU 사용률은 7%, 메모리는 31% 사용 중이고 GPU 온도는 45도입니다.
```

## 다음 단계

다음 단계에서는 현재 터미널 텍스트 답변을 로컬 TTS로 읽게 만듭니다.
