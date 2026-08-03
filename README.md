# LLM Agent — Step 26.1–26.7: Local RAG

Jarvis가 로컬 PDF, DOCX, Markdown, TXT, 코드 파일을 색인하고 파일 경로와 줄 번호 또는 PDF 페이지를 근거로 답하도록 추가했습니다.

## 구현 내용

### Step 26.1 — 로컬 문서·코드 색인

지원 형식:

```text
PDF, DOCX, TXT, Markdown, RST
Python, JavaScript, TypeScript, TOML, JSON, YAML
C/C++, Java, Rust, Go, SQL, Shell, PowerShell
HTML, CSS, CSV, LOG
```

새 도구:

```text
index_local_knowledge
```

기본 허용 경로는 `documents`, `notes`, `src`이며 허용 루트 밖의 경로는 거부합니다.

### Step 26.2 — 증분 재색인

파일별 `size_bytes`, `mtime_ns`, `sha256`, `chunk_count`, `indexed_at`을 저장합니다.

```text
크기·수정 시간 동일 → 건너뜀
수정 시간만 다르고 SHA-256 동일 → 메타데이터만 갱신
내용 변경 → 해당 파일 청크만 교체
파일 삭제 → prune_missing=true일 때 색인에서 제거
```

### Step 26.3 — 청크와 출처

텍스트·코드·DOCX:

```text
C:\project\src\attention.py:L10-L42
```

PDF:

```text
C:\papers\gqa.pdf#page=4
```

새 도구:

```text
search_local_knowledge
get_local_knowledge_chunk
```

### Step 26.4 — 로컬 BM25 검색

외부 임베딩 API 없이 토큰 빈도, 문서 빈도, 청크 길이, 정확한 문구와 파일 경로 일치를 사용해 검색합니다. `limit=0`은 설정의 기본값을 사용하며 최대 20개로 제한됩니다.

### Step 26.5 — 비밀 파일 차단

다음은 색인하지 않습니다.

```text
.env 및 .env.*
credentials.json, token.json
Google/Gmail OAuth 자격증명
private key 파일
.git, .venv, node_modules, __pycache__, Edge 프로필
```

파일 내용에 실제 OpenAI/GitHub/Google/Slack 토큰 또는 PEM 개인 키 패턴이 있어도 제외합니다.

### Step 26.6 — Memory V2 범위 연결

Local RAG의 `collection`을 Memory V2의 프로젝트 `scope`와 같은 이름으로 쓰도록 프롬프트와 도구 설명을 수정했습니다.

```text
Memory scope: Jarvis
RAG collection: Jarvis
```

### Step 26.7 — 화면 출처 유지, TTS 출처 제거

화면에는 파일 출처를 남기지만 TTS에서는 출처 전용 줄을 제거해 Windows 경로나 줄 번호를 읽지 않습니다.

## 설정

`config/user.toml`에 추가:

```toml
[local_rag]
enabled = true
database = "data/jarvis_rag.db"
roots = ["documents", "notes", "src"]
default_collection = "jarvis"
auto_index_on_startup = false
max_file_bytes = 10485760
chunk_characters = 1800
chunk_overlap_characters = 240
max_files = 5000
max_chunks = 100000
default_search_limit = 8
prune_missing = true
```

별도 논문 폴더 예시:

```toml
roots = [
    "documents",
    "notes",
    "src",
    "C:/Users/LEEJUHYOUNG/Documents/papers"
]
```

## 설치 및 실행

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m pip install -r requirements.txt
python -m src.main
```

추가 패키지:

```text
pypdf
python-docx
```

예상 로그:

```text
Local RAG     : enabled, collection=jarvis, documents=0, chunks=0
RAG roots     : documents, notes, src
```

## 사용 예시

```text
src 폴더를 Jarvis 컬렉션으로 색인해줘.
```

```text
내 코드에서 GQA의 query와 key shape 처리 부분 찾아줘.
```

```text
내 논문 폴더에서 KV Cache를 설명하는 부분 찾아서 출처와 함께 요약해줘.
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

검증 범위:

```text
텍스트·코드 색인과 줄 citation
실제 PDF 페이지 추출·검색
실제 DOCX 문단 추출·검색
BM25 검색
증분 갱신과 삭제 prune
허용 루트 밖 경로 차단
비밀 파일명·실제 비밀 패턴 차단
strict function schema
TOML 배열 설정
Local RAG 출처 TTS 제거
기존 Step 1~25 회귀 테스트
```

## 커밋 메시지

```bash
git commit -m "Add secure incremental Local RAG"
```

# 남은 모든 다음 단계

## Step 27 — Vision Agent V2

- DOM·UIA·스크린샷 통합 분석
- 팝업·모달·오류창 감지
- 클릭 전후 화면 비교
- 로딩·빈 화면·실패 화면 분류
- DOM이 없는 앱 분석
- 창 이동·배율·해상도 변화 대응
- Planner V2의 DOM→UIA→Vision 복구 연결

## Step 28 — File Agent

- 파일 이름·내용·날짜·크기·확장자 검색
- 복사·이동·이름 변경
- 대량 작업 미리보기
- 덮어쓰기 전 승인
- 삭제 대신 휴지통
- 파일 해시·개수·존재 여부 검증
- 실패 시 원상복구 계획

## Step 29 — Developer/GitHub Agent

- 저장소 구조와 의존성 분석
- 테스트·린트·타입 검사
- 오류 원인 추적
- 코드 수정과 diff 리뷰
- 브랜치 생성
- 커밋·PR 전 사용자 승인
- CI 실패 분석
- Memory V2에 개발 진행 상황 기록

## Step 30 — Gmail·Calendar Workflow V2

- 메일과 일정 교차 조회
- 메일에서 일정 후보 추출
- 참석자·시간대·충돌 검증
- 일정 후보 비교
- 쓰기 전 최종 요약
- 쓰기 후 API 재조회 검증
- 메일 작성·전송과 강한 승인

## Step 31 — Multi-Agent

- Planner, Researcher, Coder, Reviewer
- 역할별 도구 권한 분리
- 결과 교차 검토와 의견 충돌 해결
- 모델 호출 예산과 중단 조건
- Memory·RAG 접근 범위 분리

## Step 32 — Proactive Assistant

- 일정·마감·메일·프로젝트 변화 감지
- 의미 있는 변화가 있을 때만 알림
- 조용한 시간대와 중요도
- 중복 알림 억제
- 허용된 범위만 감시

## Step 33 — Voice V2

- Windows barge-in 안정화
- STT·TTS 지연 단축
- 마이크 hot-plug 복구
- 장치 전환 중 세션 유지
- 부분 STT와 오인식 취소
- 음성·텍스트 입력 동기화
- 장치별 VAD 자동 보정

## Step 34 — Jarvis GUI

- 현재 상태와 마이크 파형
- 인식 문장과 응답
- 계획·복구·도구 기록
- 승인 요청
- Memory V2와 Local RAG 관리
- 일정·알림·설정 화면

## Step 35 — Packaging & Reliability

- Windows 설치 프로그램
- 시작 프로그램과 자동 업데이트
- crash recovery
- 설정·DB·RAG 색인 백업·복원
- 버전 데이터 마이그레이션
- 로그 회전과 비밀 암호화
- 실제 Windows 통합·장시간·롤백 테스트
