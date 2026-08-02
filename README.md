# LLM Agent — Step 18.2: OpenAI Hosted Web Search

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
git commit -m "Add hosted web search without opening a browser"
```

## 다음 단계

다음은 기존 로드맵대로 **Step 19: Google Calendar·Gmail 읽기 전용
연결**입니다.

```text
오늘 일정 알려줘
내일 빈 시간 찾아줘
최근 중요한 메일 요약해줘
```
