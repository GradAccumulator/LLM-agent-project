# LLM Agent — Step 24.1–24.5: Planner V2

## Step 24.1 — 실패 원인 자동 분류

실행 예외와 postcondition 실패를 다음 범주로 분류합니다.

```text
stale_reference
ambiguous_target
verification_failed
invalid_arguments
network / rate_limited / transient
auth_required / permission_denied
safety_block
unavailable / unsupported
invalid_state / unknown
```

도구 결과의 `plan_progress.steps[].last_failure`에 범주, signature,
반복 횟수, 복구 가능 여부와 사용자 개입 필요 여부가 기록됩니다.

## Step 24.2 — 같은 실패 반복 차단과 시도 예산

각 단계의 총 시도 예산은 다음과 같습니다.

```text
1회 기본 시도 + max_repair_attempts
```

같은 failure signature가 `max_same_failure_repeats`만큼 반복되면 해당 도구는
`blocked_tools`에 들어갑니다. 이후 같은 도구로 `retry`할 수 없고 다른 도구를
지정한 `switch_tool`이 필요합니다.

## Step 24.3 — DOM → UIA → Vision 도구 전환

새 실패 보고 도구:

```text
get_plan_recovery
```

예를 들어 Edge DOM 클릭 후 변화 검증이 실패하면 다음 후보를 제공합니다.

```text
uia_capture_window_context
uia_find_elements
inspect_screen
```

stale·모호한 DOM 참조라면 먼저 구조화된 DOM 재조회 도구를 권장합니다.

```text
edge_cdp_find_element
edge_cdp_list_elements
edge_cdp_get_page_info
```

안전·권한·인증 실패는 다른 도구로 우회하지 않습니다.

## Step 24.4 — 현재 단계만 부분 재계획

새 도구:

```text
repair_task_plan
```

전략:

```text
retry             현재 단계를 새 상태로 한 번 더 시도
switch_tool       현재 단계는 유지하고 다른 도구 채널 사용
replace_current   실패한 현재 단계만 새 단계들로 교체
replace_remaining 현재와 남은 단계만 다시 작성
```

완료된 이전 단계와 검증 증거는 보존됩니다. 수정 전 단계는 revision 기록에
남아 전체 변경 과정을 확인할 수 있습니다.

## Step 24.5 — 최종 계획 감사

`finish_task_plan`은 다음 조건을 모두 검사합니다.

```text
모든 단계가 completed
모든 단계에 verified=true 증거 존재
미해결 repairing/failed 단계 없음
```

감사 결과가 `audit.passed=true`일 때만 계획을 최종 완료합니다.

## 새 기본 설정

```toml
[planning]
enabled = true
max_steps = 6
max_repair_attempts = 2
max_revisions = 3
max_same_failure_repeats = 2
tool_switching = true
```

## 예상 복구 흐름

```text
행동 실행
→ verification=false
→ plan status=repairing
→ get_plan_recovery
→ 실패 범주·추천 도구 확인
→ repair_task_plan
→ 수정된 현재 단계부터 재개
→ 모든 단계 검증
→ finish_task_plan audit
```

## 적용

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m src.main
```

도구 목록에서 다음을 확인합니다.

```text
get_plan_recovery
repair_task_plan
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 커밋 메시지

```bash
git commit -m "Add bounded partial replanning and failure recovery"
```

# 전체 이후 로드맵

## Step 25 — Memory V2
프로젝트 상태, 결정 사항, TODO, 관계형 메모리, 충돌·오래된 메모리 정리.

## Step 26 — Local RAG
PDF·논문·코드·문서 색인, 파일·줄 출처, 증분 재색인, 비밀 파일 제외.

## Step 27 — Vision Agent V2
DOM·UIA·스크린샷 통합, 팝업·오류창 탐지, 클릭 전후 화면 비교.

## Step 28 — File Agent
안전한 파일 검색·복사·이동·이름 변경, 대량 작업 미리보기와 검증.

## Step 29 — Developer/GitHub Agent
저장소 분석, 테스트·린트, diff 리뷰, 브랜치·커밋·PR 승인 흐름.

## Step 30 — Gmail·Calendar Workflow V2
메일·일정 교차 조회, 후보 일정과 충돌 검증, 쓰기 후 API 재검증.

## Step 31 — Multi-Agent
Planner·Researcher·Coder·Reviewer 역할 분리와 결과 교차검토.

## Step 32 — Proactive Assistant
마감·메일·프로젝트 변화를 조건 기반으로 확인하고 필요한 경우만 알림.

## Step 33 — Voice V2
실제 Windows barge-in 안정화, STT/TTS 지연 단축, hot-plug 복구.

## Step 34 — Jarvis GUI
파형, 상태, 계획, 승인, 메모리, 일정, 도구 실행 기록 UI.

## Step 35 — Packaging & Reliability
설치 프로그램, 자동 업데이트, crash recovery, 백업, 비밀 암호화,
Windows 통합·장시간 테스트.
