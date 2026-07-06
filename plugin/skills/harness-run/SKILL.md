---
name: harness-run
description: 설계(grill-me)→ADR 확인→Codex 코딩(MCP)→3단계 검사 파이프라인을 실행한다. 사용자가 "이 기능 만들어줘", "코덱스로 구현해줘", "설계부터 코딩까지 돌려줘"라고 할 때 사용.
---

# codex-harness: 설계→ADR→코딩→검사 오케스트레이터

너(Claude)는 오케스트레이터다. 코딩은 직접 하지 말고 **Codex에 위임**하고, 너는 설계·검수를 맡는다.
자기보고를 믿지 말고 매 단계 **증거로 검증**한다.

## 1단계 — 설계 (grill-me)
→ **`design-grill` 스킬을 로드해 그 지침을 따른다.** (AskUserQuestion 규칙, 5차원 모호성
  해소 루프, DX 원칙, 확정 스펙 산출 포맷은 그 스킬이 소유한다.)
- 요지만: 평문 질문 금지·1문1답·2~4선택지, 코드로 답할 수 있으면 직접 탐색, 모호성 해소 전엔
  다음 단계로 넘어가지 않는다(게이트). 끝나면 확정 스펙을 adr-check로 넘긴다.

## 2단계 — ADR 확인
→ **`adr-check` 스킬을 로드해 그 지침을 따른다.** (ADR 포맷, 충돌 감지, 인라인 갱신 소유.)
- 요지만: 새 결정을 기존 승인 ADR·CONTEXT.md 용어집과 대조. **충돌 발견 시 자동 진행 금지**,
  사용자에게 알리고 해소 후에만 코딩 단계로.

## 3단계 — Codex 코딩 위임 (MCP 주력)
- 코딩 실행기는 **MCP `codex` 툴**을 우선 사용(멀티턴은 `codex-reply`, threadId 유지).
  - 인자: `prompt`(확정 스펙), `sandbox`(danger-full-access — 이 컨테이너는 내장 bwrap 불가),
    `approval-policy`(never), `cwd`(격리 workdir), `config.skip_git_repo_check=true`.
- 대량 배치/헤드리스가 필요하면 보조로 `bin/codex_run.sh "<스펙>" [expected]` 호출.
  - 이 스크립트가 일회용 격리 workdir + git baseline + 위임 + diff 캡처 + 검사까지 한 흐름.

## 4단계 — 검사 (3단계 게이트, fail-closed)
- `bin/qa_verify.sh <workdir> [expected]` 실행. exit 0=통과 / exit 1=재작업.
  - G1 문법·경계: 변경파일 workdir 경계 내 + 문법 + 요구 파일 실제 생성.
  - G2 행위적: 테스트 실제 실행(pytest 우선, 없으면 함수 직접호출 폴백) + 회귀 0.
  - G3 교차검증: **너(Claude)가 diff를 읽고** 프롬프트 의도 일치·보안/로직 판정(자기검토 무효).
- `완료 = G1 ∧ G2 ∧ G3`. 하나라도 미통과면 재작업. 증거 없이 "완료" 선언 금지.

## 사람 승인 지점 (자동화 절대 금지: P1·P2)
- **P1 코드베이스 apply 전** — 격리 workdir diff를 사람이 승인해야 apply. 자동 apply 금지.
- **P2 위험 패턴 강행** — `hooks/guard_dangerous.sh`(PreToolUse, exit 2)가 차단. 사람이 명시 해제해야.
- P3 위험 플래그 / P4 설계상 진짜 갈리는 결정 / P5 2회 재작업 후 미통과 → 에스컬레이션.
