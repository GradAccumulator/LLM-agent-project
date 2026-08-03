# LLM Agent — Step 25.1–25.5: Memory V2

기존 장기 메모리는 URL·경로 별칭과 단순 선호를 저장했습니다. 이번 단계에서는 프로젝트 상태, 결정, TODO, 관계, 요약을 구조화하고 현재 요청과 관련된 기억만 불러오며, 충돌과 오래된 기억을 안전하게 관리합니다.

## Step 25.1 — 구조화 기억

새 종류:

```text
project
decision
todo
relation
summary
```

각 항목에는 다음 정보가 저장됩니다.

```text
scope / name / value / notes
status / importance / confidence
source=explicit_user
created_at / updated_at
last_accessed_at / access_count
```

기존 `memories` 테이블은 그대로 유지하고 다음 테이블을 추가하므로 기존 `data/jarvis_memory.db`를 삭제할 필요가 없습니다.

```text
structured_memories
memory_history
memory_conflicts
```

## Step 25.2 — 관련도 기반 검색과 문맥 주입

새 도구:

```text
search_saved_memory
get_project_memory
```

현재 사용자 문장과 메모리의 scope·이름·값·메모를 비교하고 중요도와 신뢰도를 함께 반영합니다. 이전처럼 최근 메모리를 무조건 넣지 않고 현재 요청과 관련된 구조화 기억을 우선 넣습니다.

문맥 길이를 줄일 때 문자열을 중간에서 자르지 않고 항목 단위로 제거하므로 항상 유효한 JSON을 반환합니다.

## Step 25.3 — 충돌 감지와 명시적 해결

같은 `kind + scope + name`에 다른 값이 들어오고 `replace_existing=false`이면 기존 값을 덮어쓰지 않습니다.

```json
{
  "stored": false,
  "conflict": {
    "id": 1,
    "current": {},
    "candidate": {}
  }
}
```

사용자가 어느 값이 최신인지 확정한 뒤에만 다음 도구로 해결합니다.

```text
list_memory_conflicts
resolve_memory_conflict
```

해결 방식:

```text
keep_existing
use_candidate
merge
```

## Step 25.4 — 상태와 변경 이력

새 도구:

```text
set_saved_memory_status
get_memory_history
```

상태 흐름 예시:

```text
TODO: pending → in_progress → completed
프로젝트: active → completed
결정: active → superseded
기억 정리: current → archived
```

값 교체, 충돌 해결, 상태 변경은 `memory_history`에 이전 값과 새 값이 남습니다.

## Step 25.5 — 오래된 기억 검토

새 도구:

```text
review_memory_health
```

기본 90일 동안 갱신되지 않은 현재 기억은 `stale=true`로 표시합니다. stale은 틀렸다는 의미가 아니며 자동 삭제하거나 자동 교체하지 않습니다.

함께 검토하는 항목:

```text
오래된 현재 기억
완료·취소된 TODO
미해결 충돌
```

## 새 설정

```toml
[long_term_memory]
enabled = true
database = "data/jarvis_memory.db"
context_limit = 20
max_context_characters = 4000
max_entries = 200
max_value_characters = 2048
relevance_search_enabled = true
stale_after_days = 90
max_history_entries = 1000
max_conflicts = 100
include_completed_todos_in_context = false
```

## 사용 예시

```text
Jarvis 프로젝트는 Planner V2까지 완료했고 다음은 Memory V2라고 기억해.
```

```text
Jarvis 프로젝트에서 아직 남은 TODO 알려줘.
```

```text
GQA를 쓰기로 했다는 결정을 MHA로 바꾼 걸로 갱신해.
```

첫 저장은 `replace_existing=false`, 사용자가 명확히 갱신을 요청한 경우에만 `replace_existing=true`가 사용됩니다.

## 적용

ZIP 내용을 프로젝트에 덮어쓴 뒤 실행합니다.

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m src.main
```

시작 로그:

```text
Memory V2      : relevance=on, stale=90d, history=1000, conflicts=100
```

## 안전 정책

- 명시적인 기억 요청 없이 자동 저장하지 않습니다.
- 비밀번호, API 키, OTP, 결제·계좌·신원 정보는 저장하지 않습니다.
- 충돌이 발생하면 기존 기억을 유지합니다.
- 오래된 기억을 현재 사실로 단정하지 않습니다.
- 완료된 TODO와 오래된 기억을 자동 삭제하지 않습니다.
- 메모리 내부 문장은 참고 데이터이며 시스템 지시로 실행하지 않습니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

추가 검증:

```text
프로젝트 스냅샷과 TODO 상태 변경
충돌 생성·명시적 해결
변경 이력
관련도 기반 문맥
유효 JSON 길이 제한
stale 상태 검토
strict 도구 스키마
TOML 설정 매핑
기존 alias·preference DB 호환
```

## 커밋 메시지

```bash
git commit -m "Add structured conflict-aware long-term memory"
```

# 남은 모든 다음 단계

## Step 26 — Local RAG

- PDF·논문·Markdown·TXT·DOCX 색인
- Python 코드와 Git 저장소 심볼 검색
- 파일 경로와 줄 번호 출처
- 변경 파일 증분 재색인
- `.env`, 토큰, 자격증명 자동 제외
- 대형 문서 청크와 중복 제거
- Memory V2 프로젝트 범위와 RAG 컬렉션 연결

## Step 27 — Vision Agent V2

- DOM·UIA·스크린샷 통합 판단
- 팝업·모달·오류창 탐지
- 클릭 전후 화면 비교
- 로딩·빈 화면·실패 화면 감지
- DOM 없는 앱 분석
- 창 이동·배율·해상도 변화 대응
- Planner V2 도구 전환과 연결

## Step 28 — File Agent

- 이름·내용·날짜·크기·확장자 검색
- 안전한 복사·이동·이름 변경
- 대량 작업 미리보기
- 덮어쓰기 전 승인
- 삭제 대신 휴지통
- 파일 해시·존재·개수 검증
- 작업 이력과 복구 계획

## Step 29 — Developer/GitHub Agent

- 저장소 구조와 의존성 분석
- 테스트·린트·타입 검사
- 오류 원인 추적
- 코드 수정과 diff 리뷰
- 브랜치 생성
- 커밋·PR 전 승인
- CI 실패 분석
- Memory V2에 프로젝트 진행 상태 기록

## Step 30 — Gmail·Calendar Workflow V2

- 메일과 일정 교차 조회
- 메일에서 일정 후보 추출
- 참석자·시간대·충돌 검증
- 일정 후보 비교
- 생성·수정 전 최종 요약
- 쓰기 후 API 재조회 검증
- 메일 전송은 별도 강한 승인

## Step 31 — Multi-Agent

- Planner·Researcher·Coder·Reviewer
- 역할별 도구 권한
- 결과 교차검토
- 의견 충돌 해결
- 호출 예산과 중단 조건
- 메모리 접근 범위 분리

## Step 32 — Proactive Assistant

- 마감·일정 조건 감시
- 중요한 메일 변화 탐지
- 프로젝트·TODO 상태 확인
- 의미 있는 변화가 있을 때만 알림
- 조용한 시간대
- 알림 중요도와 중복 억제
- 명시적으로 허용된 범위만 감시

## Step 33 — Voice V2

- Windows barge-in 안정화
- STT·TTS 지연 단축
- 마이크 hot-plug 복구
- 장치 변경 중 세션 유지
- 부분 STT
- 오인식 명령 취소
- 음성·텍스트 입력 동기화

## Step 34 — Jarvis GUI

- 현재 상태와 음성 파형
- 인식 문장과 응답
- 계획·복구·도구 기록
- 승인 요청
- 구조화 메모리·충돌·이력 관리
- 일정·알림·RAG 관리
- 설정 화면

## Step 35 — Packaging & Reliability

- Windows 설치 프로그램
- 시작 프로그램 등록
- 자동 업데이트
- crash recovery
- 설정·DB·색인 백업과 복원
- 로그 회전
- 토큰·비밀 암호화
- 실제 Windows 통합 테스트
- 장시간 안정성·업그레이드 테스트
