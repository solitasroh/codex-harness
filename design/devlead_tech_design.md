# 기술 설계 — codex-harness 플러그인 (DevLead 파트)

작성: 백팀장(DevLead) | 2026-07-05 | 회의 파트: 3-3(코딩) + 4(구조) + 5(안전장치 기술부)
근거: 실제 스켈레톤 제작 + 이 서버 실측. 말이 아니라 만들어서 돌려본 결과.
위치: `/opt/data/projects/cc-plugin/plugin/`

---

## 0. 한 줄
Claude가 오케스트레이터로 설계·검수하고, 코딩은 Codex(MCP)에 위임하는 하네스를
**클로드 코드 플러그인 한 벌**로 패키징. 기존 검증된 3스크립트 + 신규 스캐너/훅/스킬을 편입.

---

## 1. 플러그인 파일 구조 (실제 제작·검증 완료)

```
plugin/
├── .claude-plugin/
│   └── plugin.json         # name=codex-harness, version, description (JSON 유효성 ✅)
├── .mcp.json               # codex를 MCP 서버로 등록. command=bin/codex-mcp.sh
├── skills/
│   └── harness-run/SKILL.md # 4단계 오케스트레이터 지침(모델이 자동 트리거)
├── hooks/
│   ├── hooks.json          # PreToolUse(Bash)=guard_dangerous.sh
│   └── guard_dangerous.sh  # 위험명령 차단(exit 2). 실측: 차단2/통과0 ✅
├── bin/
│   ├── codex-mcp.sh        # codex mcp-server 래퍼. CODEX_HOME 자동세팅+친절실패 ✅
│   ├── codex_bootstrap.sh  # CODEX_HOME 표준화(root:600 우회)
│   ├── codex_run.sh        # 격리 workdir+위임+diff+검사 한 흐름
│   ├── qa_verify.sh        # G1·G2 자동 게이트(QA 실물)
│   └── scan_danger.py      # 위험패턴 스캐너(데이터 분리, --strict opt-in)
├── lib/
│   └── danger_patterns.txt # 위험패턴 데이터(QA 운영규칙 #3: 코드서 분리)
└── tests/
    └── test_scan_danger.py # 위험패턴 회귀(D-Q1 오탐/D-Q2 미탐). 10/10 통과 ✅
```
- 규약 준수: skills/hooks/commands는 루트에(`.claude-plugin/` 안에 넣지 않음).
- `${CLAUDE_PLUGIN_ROOT}` 치환으로 설치 위치 무관하게 경로 resolve(.mcp.json·hooks.json).

## 2. Codex를 MCP로 호출하는 법 (실측 완료)

**핵심 문제와 해법**: 실제 codex 홈 `/opt/data/.codex/config.toml`이 root:600 → hermes가
못 읽어 codex 기동 실패. root/sudo 없어 권한조정 불가 → **CODEX_HOME 우회가 유일 경로.**

`.mcp.json`이 `codex mcp-server`를 직접 부르지 않고 **래퍼(codex-mcp.sh)**를 부른다:
```
codex-mcp.sh:  export CODEX_HOME=${CODEX_HARNESS_CODEX_HOME:-$PLUGIN_ROOT/.codex_home}
               auth.json 없으면 부트스트랩 안내 후 exit 1 (조용한 실패 방지)
               exec codex mcp-server
```
- 노출 툴 2개(실측): `codex`(prompt+approval-policy+sandbox+cwd+config→{threadId,content}),
  `codex-reply`(threadId+prompt로 멀티턴).
- 코딩 위임 인자: sandbox=`danger-full-access`(이 컨테이너는 내장 bwrap 물리적 불가),
  approval-policy=`never`, cwd=격리 workdir, config.skip_git_repo_check=true.
- **실측**: 래퍼로 기동 → initialize 응답 `codex-mcp-server` 확인. tools/call로 파일 실제 생성 확인.
- 모델 함정: config에 `gpt-5-codex` 명시 금지(ChatGPT계정 400) → 미지정=계정기본(gpt-5.5).

## 3. 4단계를 코드로 엮는 법

```
[1] 설계   skills/harness-run  → Claude가 AskUserQuestion으로 grill-me (평문금지, 1문1답)
[2] ADR    같은 스킬 지침       → docs/adr·CONTEXT.md 대조·기록
[3] 코딩   MCP codex 툴(주력)   → 격리 workdir에 위임. 배치는 bin/codex_run.sh(보조)
[4] 검사   bin/qa_verify.sh     → G1·G2 자동(exit 0/1). G3(교차검토)는 Claude 스텝
```
- codex_run.sh 내부: mktemp 일회용 workdir → git baseline → codex 위임 → `git diff --cached`
  캡처(=P1 승인 자료) → qa_verify.sh 자동 호출 → exit=검사 판정. (앞선 회의서 통합·실증)
- **브라이언 연결점 반영**:
  - G1·G2 = qa_verify.sh (bin/ 편입 완료)
  - P1(apply 전 diff) = codex_run.sh의 diff 캡처가 승인 자료
  - P2·P3(위험 차단) = hooks/guard_dangerous.sh (PreToolUse, exit 2)
  - G3(교차검토) = Phase 2에서 오케스트레이터 스텝 자동화(합격기준=QA G3표)

## 4. 안전장치 기술부 (실측)
- 4겹 경계: 컨테이너 외부격리 + 일회용 workdir + diff 리뷰(P1) + fail-closed 게이트.
- 위험 스캐너: 패턴을 `lib/danger_patterns.txt`로 분리(QA #3). 기본 정보성, `--strict`서 차단(QA #4).
- **브라이언 QA 조건 이행(첫 작업)**: D-Q1(정상 import subprocess 오탐 방지)·D-Q2(wget|sh·
  curl|sudo bash 공백변형 미탐 방지)를 `tests/test_scan_danger.py`에 **고정 등록. 10/10 통과 실증.**
  → 이후 패턴 건드릴 때 조용한 재발 차단.

## 5. 검증 상태 (정직 보고)
| 항목 | 상태 |
|------|------|
| plugin.json/.mcp.json/hooks.json JSON 유효성 | ✅ 파싱 통과 |
| PreToolUse 훅 차단/통과 | ✅ 위험2=exit2, 정상2=exit0 |
| MCP 래퍼 기동 | ✅ codex-mcp-server initialize 응답 |
| 위험패턴 회귀 테스트 | ✅ pytest 10/10 + 폴백 10/10 |
| `claude --plugin-dir` 런타임 로드 | ⚠ **보류** — claude CLI 미로그인(`Not logged in`) |

**⚠ 미해결 1건**: claude CLI가 이 세션 HOME에 미인증이라 `--plugin-dir` 런타임 로드는
아직 확인 못 함. codex와 동일한 인증 격리 문제로 보임(실제 인증은 root 소유 위치 추정).
구조·개별 컴포넌트는 전부 실측 통과했으나, 통합 로드는 claude 인증 해결 후 재검증 필요.
→ 수장/PM께: claude CLI 로그인(또는 ANTHROPIC_API_KEY) 경로 확인 요청.
