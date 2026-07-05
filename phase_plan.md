# Phase 계획 — Claude 설계(Grill me+ADR) → Codex 코딩 하네스 플러그인

작성: 백팀장(DevLead) | 근거: 회의 실무검증 수렴(DevLead·QA) + 리서치 2편 | 2026-07-05
프로젝트 목적(수장 지시): "Claude Code로 grill-me 설계 → ADR 체크 → Codex에 코딩 위임"
장기 비전: 한 번 설치하면 어느 프로젝트/벤더에서든 기획→스펙분해→자율실행→다중모델검수를 돌리는 하네스 플러그인.

---

## Phase 0 — 실행기·안전경계 확정 [실무 완료 / 수장 승인 1건 대기]

이미 실측·구현·검증 완료. 산출물:
- 실행기: **B(codex mcp-server) 주력 + C(codex exec) 배치 보조**. 둘 다 실동작 확인.
- `codex_bootstrap.sh` — CODEX_HOME 표준화(root:600 config 우회, auth 600 복사).
- `codex_run.sh` — 일회용 격리 workdir + git baseline + 위임 + diff + QA 자동검증(exit 0/1).
- `qa_verify.sh`(QA) — 3계층 루브릭, pytest/폴백 양경로, fail-closed 양방향 실증.

**⛔ 수장 결정 필요(유일한 블로커):** codex 내장 샌드박스(bwrap)가 이 컨테이너에서 물리적으로
작동 불가(unprivileged userns 비활성 + root 없음) → `danger-full-access`로 끌 수밖에 없음.
그 리스크를 **4겹 경계**(컨테이너 외부격리 + 일회용 workdir + diff 리뷰 + QA fail-closed 게이트)로
상쇄. DevLead·QA 모두 승인 가능 판정. → 이 안전경계 인정 여부만 결정하면 Phase 1 착수.

---

## Phase 1 — 파이프라인 종단 검증 (검증 먼저, 리스크 최소)

목표: 작은 실제 아이디어 하나로 [설계→ADR→스펙→코딩→검증]을 한 바퀴 돌려 눈으로 확인.
- 1-1. grill-me(설계 심문) — Claude가 AskUserQuestion으로 모호성 해소, 결정 요약.
- 1-2. write-prd → tech-spec — 코드탐색 기반 PRD → 모듈 분해 + phase/step 스펙.
- 1-3. ADR 체크 — grill-with-docs로 CONTEXT.md 용어집 + ADR 대조·기록.
- 1-4. Codex 위임 — 확정 스펙을 codex_run.sh로 넘겨 격리 workdir에서 코딩.
- 1-5. 검증 — qa_verify.sh 자동(L1·L2) + Claude 교차검증(L3) 수동 1회.
- **DoD**: 실제 산출 코드가 QA 게이트 exit 0 통과 + diff 리뷰 완료 + 코드베이스 apply.
- 검증 대상 후보: 작고 자기완결적인 것(예: 유틸 CLI, 파서). 수장/PM이 소재 지정.
- max4c/skills 설치는 **참조·검증 1회용**으로만(QA 조건: 버전핀+감사+격리 workdir).

## Phase 2 — L3 교차검증 자동화 + 우리 플러그인 골격

- 2-1. L3 스텝 구현 — 코딩=Codex → 검수=Claude(다른 벤더) + diff가 프롬프트 의도와 일치하는지
  오케스트레이터가 판정. **합격 기준은 브라이언(QA)이 정의**(회의 합의).
- 2-2. 플러그인 패키징 — `.claude-plugin/plugin.json` 매니페스트 + skills/ + hooks/(TDD가드
  PreToolUse) + bin/(bootstrap·run·verify 3스크립트). commands/agents/skills/hooks는 루트에.
- 2-3. `claude --plugin-dir ./`로 설치 없이 로드 테스트 → `/reload-plugins` 핫리로드.
- **DoD**: 플러그인 형태로 로드되어 [1]~[5]가 슬래시/스킬 트리거로 동작.

## Phase 3 — 자율 실행 루프 (영상 1 executor 이식)

- 3-1. Plan→Execute→Verify 루프 — 스펙의 step 단위로 codex_run 반복, QA 게이트로 게이팅.
- 3-2. 상태 파일화 — task.md/brief.md/result.md/context.md/learnings.md (영상 2 원칙).
- 3-3. 위험명령 차단 — PreToolUse 훅(exit 2=block)으로 파괴적 명령 게이트(QA 정책).
- **DoD**: 스펙 하나를 무인으로 다단계 진행, 각 step이 fail-closed 게이트 통과.

## Phase 4 — 일반화·배포

- 4-1. 프로젝트/벤더 독립성 — CODEX_HOME·workdir를 인자화, 어느 repo에서든 부트스트랩.
- 4-2. 멀티에이전트 확장(영상 2) — 오케스트레이터+워커 팬아웃/팬인(선택, 후순위).
- 4-3. release-plugin — 버전범프/CHANGELOG/마켓플레이스 배포.

---

## 운영 주의(회의 기록 — 코드/문서에 반영 유지)
- **모델**: config에 `gpt-5-codex` 명시 금지(ChatGPT계정 400). model 미지정=계정기본(gpt-5.5).
- **git**: workdir가 repo 아니면 `--skip-git-repo-check` / `skip_git_repo_check=true`.
- **pytest 격리**(QA): 항상 workdir 기준 수집(현재 qa_verify는 `cd $WD`로 이미 격리됨). 상위에
  pytest.ini 있으면 `--rootdir=$WD` 방어 권고 — qa_verify 소관(QA).
- **폴백 러너 한계**(QA): `test_` 함수 직접호출이라 fixture/parametrize 미지원 → 회귀 스위트는
  표준 pytest 고정(.venv/bin/pytest 9.1.1 준비됨).
- **비공식 플러그인(A)**: 실행기 채택 안 함. 검증 1회용만, 버전핀+감사+격리 workdir 조건.

## 역할 분담
- DevLead(백): 실행기·격리 파이프라인·플러그인 골격·자율루프 구현.
- QA(브라이언): 3계층 루브릭·L3 합격기준·위험명령 정책·회귀 스위트.
- DesignLead(엘레나): grill-me 대화 UX·개발자 DX(슬래시/스킬 트리거 자연스러움).
- PM(자비서): 수장 결정 라우팅·phase 게이트 관리·소재 지정.
