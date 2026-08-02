# LLM Agent — Step 18.2: OpenAI Hosted Web Search

## Step 18.2.2 — 스트리밍 TTS URL 완전 차단

화면의 최종 답변에서는 링크가 제거됐지만 TTS가 가끔 `링크` 또는 URL 조각을
읽는 문제를 수정했습니다.

원인은 두 가지였습니다.

```text
1. 스트리밍 문장 분리기가 URL 내부의 마침표를 문장 끝으로 판단
2. TTS 최종 정리 함수가 원문 URL을 제거하지 않고 "링크"라는 단어로 치환
```

이제 다음 보호 장치를 모두 적용합니다.

```text
LLM 스트리밍 델타
→ URL 내부 마침표는 문장 경계로 사용하지 않음
→ 완전한 Markdown 링크와 원문 URL 제거
→ 분할된 도메인·경로·query 조각 제거
→ citation 전용 조각은 TTS 큐에 넣지 않음
→ SpeechSynthesizer 직전에도 동일 필터를 한 번 더 적용
```

차단되는 예시:

```text
https://example.com/a
example.com/a
/vp/products/123/items/456
utm_source=openai
([example.com](https://example.com))
```

TTS는 URL을 `링크`라는 단어로 바꾸지 않고 완전히 생략합니다. 실제 출처는
기존처럼 CMD의 `WEB SOURCES`에만 표시됩니다.

## Step 18.2.1 — 웹 검색 링크 본문·TTS 제거

hosted web search 답변에 다음과 같은 링크 문장이 붙는 문제를 수정했습니다.

```text
([coupang.com](https://www.coupang.com/...))
```

이제 처리 순서는 다음과 같습니다.

```text
모델 답변 수신
→ 본문의 Markdown 링크·원문 URL·숫자 citation 제거
→ citation만 있는 문장은 통째로 제거
→ 정리된 본문만 번호를 붙여 출력
→ 정리된 본문만 TTS 재생
→ 실제 출처 URL은 WEB SOURCES에만 표시
```

의미가 있는 링크 문구는 주소만 제거하고 문구를 남깁니다.

```text
[OpenAI 공식 문서](https://...)
→ OpenAI 공식 문서
```

도메인명이나 숫자만 들어간 출처 링크는 문장 전체에서 제거됩니다.

```text
([example.com](https://...))
[1]
→ 제거
```

스트리밍 TTS에도 같은 필터를 적용해 마지막 citation 문장이 이미 음성 큐에
들어가는 문제를 막았습니다.

이제 최신 정보를 찾을 때 사용자의 Edge·Chrome 검색창을 열지 않고,
**OpenAI Responses API의 hosted `web_search` 도구**를 사용합니다.

## 동작 구분

```text
"오늘 AI 뉴스 검색해서 알려줘"
→ OpenAI 서버에서 hosted web search
→ 브라우저 창 열리지 않음
→ 답변과 출처 URL을 CMD에 표시
```

```text
"구글에서 King Gnu 검색해줘"
"브라우저 검색창에 RTX 5090 검색해줘"
→ 사용자가 화면에 검색 결과를 열어 달라고 명시
→ 설정된 Edge/Chrome 창을 열어 검색
```

일반적인 `검색해줘`, `찾아줘`, `최신 정보 알려줘` 명령은 더 이상
저장된 기본 검색 엔진 fast path로 전달되지 않습니다.

## 설정

```toml
[web_search]
enabled = true
external_web_access = true
max_sources_display = 5
```

기능 끄기:

```powershell
python -m src.main --disable-web-search
```

캐시·인덱스 결과만 사용:

```powershell
python -m src.main --web-search-cache-only
```

표시할 출처 수 변경:

```powershell
python -m src.main --web-search-max-sources 8
```

## 출력

```text
JARVIS | 1/2 | ...
       | 2/2 | ...

WEB SEARCH: OpenAI hosted search | calls=1 | sources=3
WEB QUERIES: ...
WEB SOURCES:
  [1] 문서 제목
      https://...
```

URL은 답변 TTS에 포함하지 않습니다. 음성 질문에는 본문만 읽고, 출처는
CMD에 표시합니다.

## 로컬 도구와 함께 사용

hosted web search와 기존 로컬 function tool을 같은 Responses API 요청에
함께 등록합니다.

```text
공개 최신 정보 조사 → hosted web_search
실제 앱·창 조작 → 로컬 function tools
검색 결과 창 열기 → search_browser
```

모델이 단순 정보 검색에 `search_browser`를 선택하지 못하도록, 명시적인
브라우저 요청이 없는 경우 해당 로컬 도구를 API 요청에서 제외합니다.

## 비용 참고

hosted web search는 일반 모델 토큰 외에 웹 검색 도구 호출 비용이 발생할
수 있습니다. 정확한 금액은 OpenAI API 가격 정책을 확인해야 합니다.

## 실행

```powershell
python -m pip install -r requirements.txt
python -m src.main
```

## 커밋 메시지

```bash
git commit -m "Block URLs and citation fragments from streaming TTS"
```

## 다음 단계

다음은 기존 로드맵대로 **Step 19: Google Calendar·Gmail 읽기 전용
연결**입니다.

```text
오늘 일정 알려줘
내일 빈 시간 찾아줘
최근 중요한 메일 요약해줘
```
