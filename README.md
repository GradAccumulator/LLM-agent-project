# LLM Agent — Step 23.5–23.8: Resilient Multi-Tab Browser Workflows

이번 묶음은 Jarvis가 여러 Edge 탭과 여러 페이지를 오가며 작업할 때
DOM 참조 만료, 새 탭, 모호한 대상, 중간 실패를 안전하게 처리하도록
개선합니다.

## Step 23.5 — 탭·요소 검색

새 도구:

```text
edge_cdp_find_tabs
edge_cdp_find_element
```

탭은 제목과 URL, 요소는 label·placeholder·href를 기준으로 점수를
계산합니다.

```json
{
  "unique_best": true,
  "best_element_ref": "edge_el_..."
}
```

`unique_best=false`이면 Jarvis는 임의로 첫 번째 결과를 누르지 않습니다.

## Step 23.6 — stale element 자동 복구

기존 `element_ref`가 페이지 변경으로 분리되거나 fingerprint가 달라진 경우:

```text
이전 요소의 안전한 힌트 확인
→ 동일 tab_ref에서 같은 종류 요소 재조회
→ label·href·placeholder·tag 점수 비교
→ 안전 허용 요소만 후보로 유지
→ 최고 후보가 하나로 명확할 때만 새 ref 발급
→ 클릭·입력 직전 controller 안전 검사 재실행
```

두 후보가 비슷하면 자동 복구하지 않고 중단합니다.

```text
The page changed and element recovery is ambiguous.
```

클릭이 이미 시도된 뒤 발생한 불확실한 오류는 중복 동작 위험 때문에
무조건 재클릭하지 않습니다. 자동 복구는 실행 전 stale 상태에만 적용됩니다.

## Step 23.7 — 새 탭 감지·전환

클릭 전후 전체 탭의 `tab_ref`를 비교합니다.

```text
새 탭 0개 → 현재 페이지 검증
새 탭 1개 → 새 tab_ref 발급 후 자동 선택
새 탭 2개 이상 → 자동 선택하지 않고 정확한 탭 재검색
```

클릭 결과에는 다음이 포함됩니다.

```json
{
  "new_tab_count": 1,
  "new_tabs": [],
  "selected_new_tab": {},
  "active_tab_ref": "edge_tab_..."
}
```

## Step 23.8 — 브라우저 작업 상태·전체 검증

새 도구:

```text
edge_cdp_begin_workflow
edge_cdp_get_workflow
edge_cdp_verify_workflow
```

다단계 작업 흐름:

```text
begin_workflow
→ workflow_ref 저장
→ select/click/fill에 workflow_ref 전달
→ 각 행동의 verified·복구·새 탭 증거 저장
→ 마지막 URL·제목·본문·탭 수 조건 검증
→ verified=true일 때만 완료
```

최종 검증 조건:

```text
모든 기록된 행동이 verified=true
URL에 원하는 문자열 포함
제목에 원하는 문자열 포함
본문에 원하는 문자열 포함
최소 탭 수 충족
```

실패하면 workflow 상태는 `verification_failed`가 되고, 성공했다고 말하지
않도록 프롬프트와 도구 설명을 함께 수정했습니다.

## 안전 정책

이전 단계의 차단 정책은 그대로 유지됩니다.

```text
로그인·로그아웃
제출·전송·게시
업로드
구매·결제·주문
예약·확정
삭제·탈퇴
송금·이체
비밀번호·OTP·카드·계좌·신원 필드
```

stale 복구 후에도 controller가 같은 안전 정책과 fingerprint 검사를 다시
수행합니다.

## GPT-5.6 기본 설정 복원

공식 GPT-5.6 모델 ID를 프로젝트 전체 기본값에 반영했습니다.

```toml
[llm]
model = "gpt-5.6-luna"
reasoning = "low"

[model_routing]
balanced_model = "gpt-5.6-terra"
balanced_reasoning = "high"
strong_model = "gpt-5.6-sol"
strong_reasoning = "xhigh"
```

GPT-5.6에서 공식 지원하는 `max` reasoning도 CLI와 설정 검증에
추가했습니다. 예전 `minimal` 값은 호환성을 위해 `low`로 변환합니다.

## 실행

ZIP 내용을 기존 프로젝트에 덮어쓴 뒤:

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

python -m src.main
```

새 도구 목록에서 다음을 확인합니다.

```text
edge_cdp_find_tabs
edge_cdp_find_element
edge_cdp_begin_workflow
edge_cdp_get_workflow
edge_cdp_verify_workflow
```

## 음성 명령 예시

```text
열린 Edge 탭 중 유튜브 탭 찾아줘.
```

```text
현재 페이지에서 GQA라는 링크를 찾아서 열고,
새 탭의 내용에 grouped query attention이 있는지 확인해줘.
```

Jarvis 내부 예상 흐름:

```text
begin_task_plan
→ edge_cdp_begin_workflow
→ edge_cdp_find_element
→ edge_cdp_click_element(workflow_ref)
→ 새 탭 자동 선택
→ edge_cdp_get_page_info
→ edge_cdp_verify_workflow
→ finish_task_plan
```

## 전체 이후 로드맵

### Step 24 — Planner V2
실패 원인 분류, 부분 재계획, 도구 교체, 단계별 재시도 예산.

### Step 25 — Memory V2
프로젝트 진행 상태, 결정 사항, TODO, 사람·서비스 관계를 구조적으로 저장.

### Step 26 — Local RAG
PDF·논문·코드·노트·프로젝트 문서를 로컬 색인으로 검색.

### Step 27 — Vision Agent V2
DOM·UIA·스크린샷을 함께 사용한 팝업 감지와 화면 변화 검증.

### Step 28 — File Agent
안전한 파일 검색·분류·복사·이름 변경과 변경 전후 검증.

### Step 29 — Developer/GitHub Agent
저장소 분석, 테스트 실행, diff 리뷰, 브랜치·PR 작업 승인 흐름.

### Step 30 — Gmail·Calendar Workflow V2
메일과 일정의 교차 조회, 일정 후보 생성, 충돌 검증, 쓰기 승인 강화.

### Step 31 — Multi-Agent
Planner·Researcher·Coder·Reviewer 역할 분리와 결과 교차 검토.

### Step 32 — Proactive Assistant
반복 작업·마감·변경 사항을 조건 기반으로 확인하고 필요한 경우만 알림.

### Step 33 — Voice V2
더 빠른 STT/TTS 파이프라인, 확실한 barge-in, 장치 hot-plug 복구.

### Step 34 — Jarvis GUI
상태, 파형, 계획, 승인 요청, 메모리, 도구 기록을 보여주는 데스크톱 UI.

### Step 35 — Packaging & Reliability
Windows 설치 프로그램, 자동 업데이트, crash recovery, 백업·복원,
권한·비밀 관리, 실제 Windows 통합 테스트.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

새 테스트는 다음을 포함합니다.

```text
탭·요소 점수 검색
stale ref의 유일한 안전 후보 복구
모호한 후보 자동 복구 차단
새 탭 감지 및 자동 선택
workflow 행동 기록
URL·제목·본문·탭 수 전체 검증
GPT-5.6 기본값과 max reasoning
```

## 커밋 메시지

```bash
git commit -m "Add resilient multi-tab Edge workflows"
```
