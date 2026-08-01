# LLM Agent — Step 15: Streaming LLM + Sentence-Level TTS

GPT 답변 전체가 완성될 때까지 기다리지 않고, Responses API의 텍스트
델타를 받아 완성된 문장부터 Edge TTS 큐에 넣습니다.

## 새 흐름

```text
GPT 첫 문장 생성
→ 첫 문장 Edge TTS 생성·재생
→ GPT는 뒤 문장을 계속 생성
→ 다음 문장이 완성되면 TTS 큐에 추가
```

터미널에도 답변이 생성되는 즉시 표시됩니다.

```text
JARVIS STREAM: 첫 번째 문장입니다. 뒤 문장은 계속 생성 중입니다...
JARVIS META [gpt-5.6-luna | first_text=0.42s | total=1.58s]
STREAM TTS: first_audio=0.81s | chunks=2/2
```

## 도구 호출과 함께 사용할 때

함수 호출이 감지되면 임시 음성 큐를 취소하고 도구를 실행한 뒤, 도구
결과를 반영한 최종 답변 스트림을 새로 읽습니다.

```text
GPT 임시 응답
→ 함수 호출 감지
→ 임시 음성 취소
→ 로컬 도구 실행
→ 최종 답변 스트리밍
```

## 설정

```toml
[streaming]
enabled = true
minimum_sentence_characters = 24
maximum_chunk_characters = 160
```

더 빠르게 첫 음성을 시작:

```powershell
python -m src.main `
  --streaming-minimum-characters 12 `
  --streaming-maximum-characters 100
```

조각이 너무 작으면 말이 끊겨 들릴 수 있으므로 기본값 24자를 먼저
사용하는 편이 좋습니다.

기존 완성형 응답 방식:

```powershell
python -m src.main --disable-streaming
```

## Barge-in 연동

스트리밍 TTS 중에도 기존 말 끊기가 작동합니다.

```text
자비스가 첫 문장 재생
→ 사용자 음성 감지
→ 현재 재생과 남은 TTS 큐 중단
→ 끼어든 명령 캡처
→ 새 명령 처리
```

## 실행

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m src.main
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Stream LLM responses into sentence-level TTS"
```

## 다음 단계

다음은 **작업 계획·검증 루프**입니다. 여러 단계의 컴퓨터 작업을 수행할 때
`계획 → 실행 → 화면·도구 결과 재확인 → 실패 시 수정` 순서로 진행하게
만들어 장시간 작업의 성공률을 높입니다.
