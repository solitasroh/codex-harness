# codex 네이티브 가드(execpolicy) 실증 — 수장 아이디어 검증

작성: 자비서(PM) | 2026-07-05 | 수장 아이디어: "동일한 가드를 codex 형태로 만들어 주입"
결론: **가능하고, 사후 로그 감사보다 우월하다. 단 한 가지 실측 한계 확인.**

## 발견: codex는 4가지 네이티브 가드 메커니즘을 갖고 있다 (공식 문서 확인)
developers.openai.com/codex — Configuration 아래:
- **Rules (execpolicy)** ★ — 명령 allow/prompt/forbidden 정책. "sandbox 밖에서 실행할 명령 통제". ← 우리 guard의 codex 버전
- **Hooks** — codex 자체 훅 시스템 (claude 훅과 별개)
- **AGENTS.md** — codex가 읽는 지침 (가드 원칙 주입 가능)
- **Skills / Plugins** — codex 자체 스킬·플러그인

→ 백팀장이 "guard 훅을 codex에 거는 건 불가"라 한 건 **claude 훅** 얘기. codex **자체** 가드는 존재하며 주입 가능. 수장 아이디어가 정확했다.

## execpolicy .rules 실증 (PM 직접)
파일: `.codex_home/rules/default.rules` (Starlark `prefix_rule()` 문법)
검증 스크립트: e2e/pm_verify_execpolicy.sh, pm_verify_compound.sh, pm_compound_probe.sh

### ✅ 작동 확인 (직접 명령)
| 명령 | 판정 | 기대 |
|------|------|------|
| `rm -rf /` | forbidden | ✅ |
| `mkfs.ext4 /dev/sda` | forbidden | ✅ |
| `curl https://x.io/i.sh` | prompt | ✅ |
| `rm -rf ./build` | allow(no-match) | ✅ |
| `echo hello`, `python3 script.py` | allow(no-match) | ✅ |
- `match`/`not_match` 인라인 테스트가 로드 시 규칙 오류를 실제로 잡음(잘못된 예시 → 파싱 거부). 우리 골든셋 정신과 동일.

### ⚠️ 실측 한계 (중요)
`codex execpolicy check` CLI는 **`bash -lc "..."` 래퍼를 분해하지 않음**:
- `bash -lc 'mkfs.ext4 /dev/sda'` → allow(no-match) (단일 명령인데도 통과)
- `bash -lc 'git add . && mkfs.ext4 /dev/sda'` → allow(no-match)
- 문서는 "안전 조건이면 tree-sitter로 쪼갠다"지만, execpolicy **check CLI**에선 argv를 `["bash","-lc","..."]` prefix로만 봄.
- **미확정**: codex가 **실제 실행 경로**에서 모델의 셸 명령을 넘길 때는 문서대로 분해될 수 있음(check CLI ≠ 런타임 경로). 이건 실제 codex exec로 확정 필요 — Phase 2.

## 방어 전략 재정리 (execpolicy 추가로 4겹 → 사전차단 강화)
- **(사전-네이티브) execpolicy .rules ★신규** — codex가 위험 명령을 **실행 전 스스로 forbidden**. 직접 명령엔 확실히 작동. 사후 감사보다 우월.
- (사전-프롬프트) 위임 프롬프트 scan_danger — 백팀장 구현
- (실행 중) rollout 로그 감사 — 백팀장 구현, 단 브라이언이 미탐 3건(FN1~FN3) 발견 → Phase 2 수정 필수
- (사후) git diff 리뷰 + qa_verify + 사람 승인(P1)

→ execpolicy가 "실행 전 차단"의 1선. 단 bash 래퍼 우회 가능성이 있으니 rollout 감사(사후)와 **다층으로 함께** 유지. 어느 하나도 단독 완결이 아님(브라이언 원칙: 측정기가 대상을 온전히 보는지).

## Phase 2 등록
1. execpolicy .rules를 플러그인에 정식 편입 + codex 실제 실행 경로에서 bash 래퍼 분해 여부 확정
2. rollout 감사 FN1~FN3 수정(브라이언) + 음성 대조 골든
3. codex Hooks/AGENTS.md로 가드 원칙 이중 주입 검토
