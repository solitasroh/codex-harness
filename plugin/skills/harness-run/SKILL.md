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
- **★ 설치 직후 자가진단(권장, fail-loud의 자동화판).** 새 환경(특히 윈도우 실기)에서 처음 쓸 땐
  `bin/doctor.ps1`(윈도우) / `bin/doctor.sh`(리눅스·맥)를 1회 실행해 6항목을 **실동작**으로 검증한다.
  - 6항목: ①codex CLI ②CODEX_HOME/auth.json ③**실제 MCP tools/call 성공(phantom 아님)** ④.NET 게이트
    (임시 xUnit self-test) ⑤가드훅 패턴 자가탐색 ⑥CODEX_HOME 갈림길 리포트(읽기전용).
  - 각 항목 PASS/FAIL/SKIP + 근거 한 줄. FAIL 있으면 exit 1. SKIP(실기 조건 불충족, 예: dotnet 미설치)은 FAIL과 구분.
  - ③이 핵심: `tools/call` 응답의 `structuredContent.threadId`는 **인증이 깨져도(isError=True/401) 들어온다**
    (실측). doctor는 threadId 유무만 보지 않고 `isError`·401까지 파싱해 진짜 위임 성공만 PASS로 친다.
- **★ 선행체크(fail-loud, 필수).** MCP `codex` 툴을 처음 호출하기 전에 `CODEX_HOME` 초기화 상태를
  반드시 확인한다. 배경: `.mcp.json`은 정적 파일이라 인증 체크를 못 하고, `codex mcp-server`는
  **auth.json이 없어도 `initialize`에는 성공**한다(그래서 `claude mcp list`엔 ✔ Connected로 뜸).
  그러나 실제 `tools/call`에서 인증이 깨진다 — "연결은 됐는데 코딩만 조용히 실패"하는 가짜 연결.
  (구 `bin/codex-mcp.sh` 래퍼가 하던 "auth.json 없으면 큰 소리로 실패"를 여기로 이관한 것.)
  - 확인: `${CLAUDE_PLUGIN_ROOT}/.codex_home/auth.json`이 존재·읽기 가능한가.
  - 없으면 **코딩 위임을 시작하지 말고** 사용자에게 알린다: "Codex 미초기화 → 먼저
    `bin/codex_bootstrap.sh`(윈도우: `bin/codex_bootstrap.ps1`) 실행 필요." (조용한 실패 방지, fail-closed)
- 코딩 실행기는 **MCP `codex` 툴**을 우선 사용(멀티턴은 `codex-reply`, threadId 유지).
  - 인자: `prompt`(확정 스펙), `sandbox`(danger-full-access — 이 컨테이너는 내장 bwrap 불가),
    `approval-policy`(never), `cwd`(격리 workdir), `config.skip_git_repo_check=true`.
- 대량 배치/헤드리스가 필요하면 보조로 `bin/codex_run.sh "<스펙>" [expected]` 호출.
  - 이 스크립트가 일회용 격리 workdir + git baseline + 위임 + diff 캡처 + 검사까지 한 흐름.

## 4단계 — 검사 (3단계 게이트, fail-closed)
- `bin/qa_verify.py <workdir> [expected]` 실행(크로스플랫폼). exit 0=통과 / exit 1=재작업 / exit 2=사용법·환경오류.
  - 리눅스 호환 `bin/qa_verify.sh` 는 이제 `qa_verify.py` 를 부르는 얇은 shim(기존 호출자 무손상).
  - **러너 자동감지**: `.sln`/`.csproj` 있으면 `dotnet build`+`dotnet test`(xUnit 등 .NET),
    없고 `test_*.py`/`*_test.py` 있으면 pytest(부재 시 함수 직접호출 폴백), 둘 다 없으면 L2 미검증 경고.
  - G1 문법·경계: 변경파일 workdir 경계 내(git diff) + (파이썬 있으면)문법 + 요구 파일 실제 생성.
  - G2 행위적: 테스트 **실제 실행** + 회귀 0. (.NET=dotnet test / py=pytest·직접호출. 자기보고·파일존재≠통과.)
  - G3 교차검증: **너(Claude)가 diff를 읽고** 프롬프트 의도 일치·보안/로직 판정(자기검토 무효).
- `완료 = G1 ∧ G2 ∧ G3`. 하나라도 미통과면 재작업. 증거 없이 "완료" 선언 금지.
- ⚠ .NET 환경: `dotnet` 이 PATH 에 있어야 G2 가 돈다. ICU 없는 리눅스 컨테이너는
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` 필요(윈도우 실기는 불요). qa_verify.py 가 자동 설정.

## 사람 승인 지점 (자동화 절대 금지: P1·P2)
- **P1 코드베이스 apply 전** — 격리 workdir diff를 사람이 승인해야 apply. 자동 apply 금지.
- **P2 위험 패턴 강행** — `hooks/guard_dangerous.sh`(PreToolUse, exit 2)가 차단. 사람이 명시 해제해야.
- P3 위험 플래그 / P4 설계상 진짜 갈리는 결정 / P5 2회 재작업 후 미통과 → 에스컬레이션.
