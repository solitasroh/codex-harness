# 슬랙 칸반 기술 분석 & 적용 검토

작성: 자비서(PM) | 2026-07-05 | 근거: Hermes 공식 docs + CLI 실측 + 팀 세션기록 교차확인
질문(Soojang): "AI 어벤저스 팀 영상(DuTZEAQwyLc)에 나온, 슬랙에서 칸반 처리하는 기술을 분석하고 어떻게 적용할지 검토"

---

## 0. 결론 먼저 (TL;DR)

- **영상 속 "슬랙 칸반"의 정체 = Hermes 내장 `hermes kanban` (Multi-Agent Board)**. 별도 서드파티 도구가 아니라 우리가 이미 쓸 수 있는 기능. CLI로 실측 확인 완료.
- **슬랙에서 처리하는 방법 = `/kanban` 슬래시 커맨드.** 공식 docs 명시: "모든 `hermes kanban <action>`은 Slack 포함 모든 게이트웨이에서 `/kanban <action>`으로 호출 가능." 즉 **우리가 지금 대화하는 이 슬랙 채널에서 바로 보드를 조작**할 수 있음.
- **우리 4봇 팀(자비서Studio)에 즉시 적용 가능.** 지금까지 수동 @멘션으로 하던 태스크 배분을, 상태·의존성·감사가 남는 durable 보드로 승격. 특히 진행 중인 **cc-plugin 프로젝트의 "decompose→병렬 구현→검증→합성" 파이프라인과 정확히 일치**(swarm 기능).
- 현재 상태: 보드는 `default` 하나, **완전히 비어 있음(태스크 0)**. 아직 미활용. 켜기만 하면 됨.

---

## 1. 기술 분석 — Hermes Kanban이 무엇인가

### 핵심 정의 (docs 인용)
> "durable task board, shared across all your Hermes profiles... Every task is a row in `~/.hermes/kanban.db`; every handoff is a row anyone can read and write; **every worker is a full OS process with its own identity.**"

우리 4봇(자비서/백팀장/브라이언/엘레나)이 각자 독립 프로필=독립 OS 프로세스로, **하나의 SQLite 보드를 공유**하며 협업하는 구조. 지금 우리가 하는 멀티봇 협업의 "정식 인프라"다.

### 두 개의 서피스 (핵심 설계)
| 서피스 | 누가 | 어떻게 |
|--------|------|--------|
| **툴** (`kanban_*`) | 모델(봇) | kanban_show/list/create/complete/block/comment/link/heartbeat/unblock — 워커가 직접 툴콜 |
| **CLI / 슬래시 / 대시보드** | 사람·스크립트·cron | `hermes kanban …` / **`/kanban …`(슬랙 등)** / 웹 대시보드 |
둘 다 같은 `kanban_db` 레이어를 거쳐 뷰가 일관됨.

### delegate_task vs Kanban (왜 칸반인가)
| | delegate_task | **Kanban** |
|--|--------------|-----------|
| 형태 | RPC(fork→join) | durable 큐 + 상태머신 |
| 부모 | 자식 끝날 때까지 블록 | fire-and-forget |
| 자식 정체 | 익명 서브에이전트 | **이름있는 프로필+지속메모리** |
| 재개성 | 실패=실패 | block→unblock→재실행, 크래시→reclaim |
| 사람 개입 | 불가 | **언제든 comment/unblock** |
| 감사추적 | 컨텍스트 압축 시 소실 | **SQLite에 영구 rows** |
| 조율 | 계층(caller→callee) | **peer(누구나 읽기/쓰기)** |

→ 우리 협업은 "봇 경계를 넘고, 재시작을 견디고, 사람이 개입하고, 감사가 남아야" 하므로 **정확히 Kanban 케이스**. (delegate_task는 단발 추론용.)

### 핵심 개념
- **Task**: 제목/본문/assignee(프로필)/상태(triage|todo|ready|running|blocked|done|archived)/tenant/idempotency-key
- **Link**: parent→child 의존성. 부모 완료 시 dispatcher가 자식을 todo→ready로 승격
- **Comment**: 봇 간 프로토콜. 워커 재스폰 시 전체 코멘트 스레드를 컨텍스트로 읽음
- **Workspace**: scratch(임시)/dir:<절대경로>(공유)/worktree(git, 코딩용)
- **Dispatcher**: 게이트웨이 안에서 60초마다 — stale reclaim, crash reclaim, ready 승격, 원자적 claim, 프로필 스폰. (연속 2회 스폰 실패 시 auto-block으로 thrashing 방지)
- **Board**: 프로젝트/도메인별 격리 큐. 크로스보드 링크 불가(격리 경계)

### Swarm (영상2 하네스와 직결) — CLI 실측
```
hermes kanban swarm "goal" \
  --worker 백팀장:구현:codex \
  --worker 브라이언:검증 \
  --verifier 브라이언 --synthesizer 자비서
```
→ **병렬 워커(팬아웃) → verifier(검증) → synthesizer(팬인)**. 영상2 "하네스 멀티에이전트"의 팬아웃/팬인을 CLI 한 줄로. cc-plugin의 L1·L2·L3 게이트와도 자연 결합.

---

## 2. 슬랙에서 어떻게 쓰나 (`/kanban`)

docs 인용: "from any gateway platform (Telegram, Discord, **Slack**, WhatsApp, ...). 같은 argparse 트리를 재사용해 CLI·/kanban·hermes kanban 인자/출력 완전 동일."

이 채널에서 바로:
```
/kanban list
/kanban create "diff-digest 구현" --assignee 백팀장 --parent t_spec
/kanban comment t_abcd "L3 통과, 머지 승인"
/kanban unblock t_abcd
/kanban swarm ...            # 병렬 워커 그래프 생성
/kanban specify t_abcd       # triage 한 줄 → 실제 스펙으로 확장
/kanban dispatch --max 3     # 수동 디스패치 1회
```
- `notify-subscribe`: 태스크 완료/블록 이벤트를 이 슬랙 세션으로 알림. `auto_subscribe_on_create=true`면 create한 세션이 자동 구독.
- 즉 **수장님이 슬랙에서 `/kanban`으로 지시 → 봇들이 자동 스폰되어 처리 → 완료 시 슬랙으로 알림** 이 한 채널에서 닫힘.

---

## 3. 우리 팀 적용 검토

### 지금 방식의 한계 (실제 겪은 것)
- 수동 @멘션 배분 → **ID 추측하면 침묵 단절**(과거 실측 결함), 상태 추적 안 됨, 감사 안 남음, 봇 크래시 시 복구 없음.
- cc-plugin 회의도 멘션 핑퐁으로 진행 → 누가 뭘 들고 있는지 한눈에 안 보임(엘레나가 "핸드오프 상태 보드" 필요성 지적한 바로 그 지점).

### Kanban 도입 시 해결
| 현재 문제 | Kanban 해결 |
|-----------|------------|
| 멘션 핑퐁·침묵단절 | assignee 프로필로 원자적 배분, dispatcher가 자동 스폰 |
| 상태 불투명 | triage→ready→running→done 상태머신 + `/kanban stats` |
| 감사 없음 | 모든 핸드오프가 SQLite rows에 영구 |
| 크래시 복구 없음 | reclaim(PID 죽으면 자동 회수) |
| 사람 개입 어려움 | 언제든 `/kanban comment`·`unblock` |
| 병렬 협업 수동 | `swarm`으로 팬아웃/팬인 자동 |

### cc-plugin에 즉시 매핑
우리 파이프라인 = **엔지니어링 파이프라인 패턴**(docs가 명시한 대표 워크로드):
```
decompose → 병렬 워크트리 구현 → 리뷰 → 반복 → PR
```
- 설계(자비서 grill) = triage 태스크 → `/kanban specify`로 스펙화
- 구현 = 백팀장 assignee + **worktree 워크스페이스**(코딩용, git worktree 자동)
- 검증 = 브라이언 verifier (L1·L2·L3), fail 시 block→코멘트→unblock 재실행
- 이게 우리가 이미 손으로 돌린 Phase 1을 **보드가 자동 오케스트레이션**하는 것

---

## 4. 적용 로드맵 (제안)

**단계 0 — 검증(리스크 0):** 빈 default 보드에 테스트 태스크 1개 생성 → 백팀장 프로필로 스폰되는지, 슬랙 알림 오는지 실측. `hermes kanban init` 이미 됨(보드 존재 확인).

**단계 1 — cc-plugin 보드 신설:** `hermes kanban boards create cc-plugin`. Phase 2 작업(L3 자동화, 플러그인 골격)을 태스크로 올려 실전 투입. worktree 워크스페이스로 격리.

**단계 2 — swarm 파이프라인:** diff-digest 같은 소재로 `swarm`(백팀장 구현 + 브라이언 검증 + 자비서 합성) 한 바퀴. 우리 fail-closed 게이트(qa_verify.sh)를 verifier 단계에 결합.

**단계 3 — 상시 운영:** 수장님이 슬랙에서 `/kanban create`로 지시 → 자동 처리 → 알림. 멘션 핑퐁 폐기, 보드가 협업 인프라.

### 선결 확인 (다음 액션)
- dispatcher가 게이트웨이 안에서 도는지(`kanban.dispatch_in_gateway`) — 우리 4프로필 게이트웨이 상태와 함께 실측 필요.
- 각 프로필이 kanban 툴셋 활성인지 / 워커 스폰 시 codex 위임(cc-plugin 안전경계)과 결합 방식.
- **주의**: scratch 워크스페이스는 완료 시 삭제됨 → 코딩 산출물은 worktree/dir 사용.

---

## 5. 한 줄 총평
> 우리가 지금 멘션으로 수동으로 하는 4봇 협업의 "정식 버전"이 Hermes에 이미 내장돼 있다. `/kanban`으로 슬랙에서 바로 몰고, cc-plugin의 decompose→구현→검증 파이프라인을 durable 보드로 승격하면, 침묵단절·상태불투명·감사부재가 한 번에 해결된다. 리스크 낮고 이득 크다 — **단계 0 검증부터 착수 권장.**
