# LLM Agent — Step 5: GPT Reasoning

`Hey Jarvis`를 감지한 뒤 음성을 로컬에서 텍스트로 바꾸고,
OpenAI Responses API에 전달해 자비스의 답변을 생성합니다.

## 동작 흐름

```text
마이크 자동 선택
→ 16 kHz 리샘플링
→ "Hey Jarvis" 감지
→ Silero VAD로 명령 구간 녹음
→ Faster-Whisper 로컬 STT
→ GPT-5.6로 답변 생성
→ 터미널에 답변 출력
→ 다시 웨이크워드 대기
```

아직 컴퓨터 제어와 음성 출력은 연결하지 않았습니다. 따라서 이번 단계에서는
자비스의 답변이 터미널에 텍스트로 출력됩니다.

## 1. 설치

기존 가상환경에서 다음 명령을 실행합니다.

```powershell
python -m pip install -r requirements.txt
```

## 2. OpenAI API 키 설정

### 방법 A: `.env` 파일

프로젝트 루트에서 예시 파일을 복사합니다.

```powershell
Copy-Item .env.example .env
```

`.env` 파일을 열고 값을 자신의 API 키로 바꿉니다.

```dotenv
OPENAI_API_KEY=your_api_key_here
```

`.env`는 `.gitignore`에 포함되어 있으므로 커밋하지 않습니다.

### 방법 B: Windows 환경 변수

```powershell
setx OPENAI_API_KEY "your_api_key_here"
```

`setx`를 사용했다면 현재 터미널을 닫고 새 터미널에서 실행합니다.

## 3. 실행

```powershell
python -m src.main
```

## 기본 설정

- 웨이크워드: `Hey Jarvis`
- 웨이크워드 임계값: `0.45`
- VAD 임계값: `0.50`
- STT 모델: `turbo`
- STT 언어: 한국어 (`ko`)
- LLM 모델: `gpt-5.6-luna`
- Reasoning effort: `low`
- 최대 출력: `512` 토큰
- 대화 기억: 현재 프로그램 실행 중 활성화

개발·테스트 중 API 비용과 응답 시간을 줄이기 위해 기본 모델은
`gpt-5.6-luna`로 설정했습니다. 더 강한 모델을 사용하려면:

```powershell
python -m src.main --llm-model gpt-5.6-terra
python -m src.main --llm-model gpt-5.6
```

## 실행 예시

```text
[08:02:11] WAKE WORD DETECTED | phrase=hey jarvis | score=0.812
COMMAND: waiting for speech...
TRANSCRIBING...
TRANSCRIPT [ko 100.0% | 0.28s]: 파이썬의 GIL이 뭐야?
THINKING...
JARVIS [gpt-5.6-luna | 1.42s | 86→74 tokens]:
GIL은 한 프로세스 안에서 한 번에 하나의 스레드만 파이썬 바이트코드를
실행하게 하는 CPython의 잠금입니다.
```

후속 명령은 같은 실행 세션의 대화 문맥을 이어갑니다.

```text
사용자: 그럼 멀티스레딩은 의미가 없어?
자비스: I/O 작업에서는 여전히 유용하지만, CPU 연산 병렬화에는 제약이 있습니다.
```

다음 음성 명령 중 하나를 말하면 대화 문맥만 초기화합니다.

```text
대화 초기화
기억 초기화
대화 리셋
컨텍스트 초기화
```

## LLM 관련 옵션

```powershell
python -m src.main --llm-model gpt-5.6-terra
python -m src.main --llm-reasoning low
python -m src.main --llm-reasoning medium
python -m src.main --llm-max-output-tokens 800
python -m src.main --llm-timeout 90
python -m src.main --no-llm-memory
```

전체 옵션:

```powershell
python -m src.main --help
```

## 주의

ChatGPT Plus와 OpenAI API는 별도 서비스입니다. API 호출에는 별도의 API
결제 설정이 필요하며, 사용량에 따라 비용이 발생합니다. API 키는 코드나
Git 저장소에 직접 넣지 마세요.
