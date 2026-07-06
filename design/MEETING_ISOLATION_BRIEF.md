# 회의 브리프 — "claude의 hook·skill·스크립트가 codex 코딩으로 넘어갈 때 어떻게 동작하나"

소집: 수장 지시 | 작성: 자비서(PM) | 2026-07-05
질문(원문): "claude 내 hook과 skill 또는 스크립트들이 codex 코딩으로 이전될 때 어떻게 동작할까?"

## PM 선제 실측 (추측 아님, 코드/설정 직접 확인)

### 핵심 답: claude의 안전장치는 codex에 "자동으로는" 적용되지 않는다
codex는 claude와 **완전히 분리된 별도 프로세스**다. 실측 근거:

| 항목 | claude 쪽 | codex 쪽 (코딩 시) |
|------|-----------|-------------------|
| 훅(hooks.json) | PreToolUse matcher=**Bash** — claude가 Bash 툴 쓸 때만 발동 | codex는 claude 툴이 아님 → **훅 안 걸림** |
| 스킬(SKILL.md) | claude 세션이 로드해 claude 행동 지침 | codex는 claude 스킬 안 읽음 → **적용 안 됨** |
| codex 자체 정책 | — | `approval_policy=never`, `sandbox_mode=danger-full-access` → **codex 내부 안전장치 전부 OFF** |

### 그럼 무엇이 codex를 통제하나 — "사전 차단"이 아니라 "사후 검사"
codex_run.sh 실측 흐름:
```
격리 workdir 생성 → git baseline commit
  → codex exec --dangerously-bypass-approvals-and-sandbox (codex 자유 실행)
  → git diff 캡처 (변경 전체)
  → qa_verify.sh 게이트 (L1 경계+문법 / L2 테스트 / L3 교차검토)
  → 사람/PM이 diff 승인해야 실제 코드베이스로 apply (P1)
```
즉 **codex는 격리 workdir 안에서는 자유롭게 코딩**하고, 그 결과물을 **claude/사람이 검사·승인하는 단계에서** claude의 안전 원칙이 적용된다. hook이 "실행 순간"을 막는 게 아니라, 게이트가 "결과물"을 막는다.

### 왜 이 구조인가 (이미 확정된 사실)
- 이 컨테이너는 codex 내장 샌드박스(bwrap) 불가 → codex 자체 격리는 못 씀.
- 대신 4겹 경계: 컨테이너 외부격리 + 일회용 workdir + git diff 리뷰 + qa_verify 게이트.
- codex의 위험 행위 방어선 = "실행 중 차단"이 아니라 "workdir 격리 + 사후 diff 검사".

## 회의에서 답할 질문 (팀 배분)

### 개발(백팀장) — 실행 경계 실측
1. codex가 격리 workdir **밖**을 건드릴 수 있나? (`-C $WD`로 cwd 고정하지만 절대경로 rm 등은?)
   → qa_verify L1 "변경파일 경계 내" 검사가 **사후**인데, 실행 **중** 경계 밖 파괴는 못 막는 것 아닌가?
2. claude의 guard_dangerous.sh(위험명령 차단 훅)를 codex 실행에도 걸 방법이 있나?
   (codex를 claude Bash 툴로 감싸면 훅이 걸리나? 아니면 codex_run.sh 안에서 프롬프트/명령 사전 스캔?)
3. MCP 경로(codex mcp-server)로 코딩할 때와 exec 경로일 때 안전 경계가 같은가 다른가?

### QA(브라이언) — 검사 모델의 구멍
1. "사후 검사" 모델의 근본 위험: codex가 실행 **중** 이미 파괴적 부작용(외부 네트워크, workdir 밖 쓰기)을 내면 사후 diff로는 못 잡는다. 이걸 어떻게 검증/방어하나?
2. 방금 네 메타검증 교훈(측정기가 대상을 측정하나) 연장: qa_verify가 "codex가 실제 한 일"을 측정하나, 아니면 "diff에 남은 것"만 측정하나? diff에 안 남는 부작용은?

### 디자인(엘레나) — 이 구조를 HTML 설계서 §5(안전장치)에 명확히
"claude 안전장치 ≠ codex 자동 적용, 대신 격리+사후검사" 모델을 사람이 오해 없이 이해하도록 다이어그램/표.

## 브라이언 골든셋 메타검증 소견 (접수, 별건)
- adr-check 스킬 자체는 PASS. 골든셋 하네스는 "구조 통과 + 케이스 강화" Phase 2 항목 등록.
- 이유: 현 4케이스가 너무 명백해 스킬 무력화해도 claude 상식으로 통과 → "스킬 작동"이 아니라 "claude가 모순을 아는지"를 측정 중. gap_probe 교훈과 동일 계열.
- design-grill 골든셋도 같은 함정 주의(명백하면 무의미).
