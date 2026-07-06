# codex-harness — Claude Code 플러그인

Claude로 **설계를 압박 테스트(grill me)** → **결정을 ADR로 기록** → **Codex에 코딩 위임** →
**3단계 게이트로 검사**하는 자율 파이프라인. 사람은 정말 갈리는 결정과 반영 승인에만 개입한다.

> 핵심 철학: **코딩(Codex)과 검토(Claude)는 다른 벤더가 맡는다.** AI의 자기보고는 믿지 않고
> 실제 증거로 완료를 판정한다. 위험한 순간엔 반드시 사람이 확인한다.

---

## 무엇을 하나 (4단계 파이프라인)

| 단계 | 스킬/도구 | 하는 일 |
|------|----------|---------|
| 1. 설계 | `design-grill` | Claude가 면접관처럼 5차원(목적·완료기준·범위·대안·가정)을 캐물어 요구사항 확정. 하나라도 미해소면 "완료" 선언 차단 |
| 2. ADR | `adr-check` | 결정을 ADR로 기록하고 기존 결정·용어집(CONTEXT.md)과 충돌 대조. 충돌 시 코딩 진입 차단 |
| 3. 코딩 | `codex_run.sh` → Codex | 일회용 격리 workdir에서 Codex가 코딩, 결과를 diff로 회수 |
| 4. 검사 | `qa_verify.sh` (G1·G2·G3) | 문법·경계 → 실제 동작(회귀 0) → 교차검토. 세 관문 통과해야 "완료" |

오케스트레이터 스킬 `harness-run`이 위 흐름을 묶는다.

---

## 설치·사용

### 1) 설치 — 마켓플레이스 (권장)

이 리포 자체가 `jabiseo-studio` 마켓플레이스다. 두 줄로 설치·자동업데이트가 붙는다.

```bash
# 마켓플레이스 등록 → 플러그인 설치
claude plugin marketplace add solitasroh/codex-harness
claude plugin install codex-harness@jabiseo-studio

# 최신 반영 (카탈로그 갱신 후)
claude plugin marketplace update
claude plugin update codex-harness@jabiseo-studio   # 재시작 후 적용
```

설치하면 스킬이 **플러그인명으로 네임스페이스**되어 노출된다:

```
/codex-harness:harness-run      # 설계→ADR→코딩→검사 오케스트레이터
/codex-harness:design-grill     # 설계 압박(grill-me)
/codex-harness:adr-check        # ADR 기록·충돌 대조
```

### 2) 개발자용 — 로컬 로드 (`--plugin-dir`)

리포를 clone해 고치면서 바로 돌릴 때. 설치 없이 세션 한정 로드.

```bash
claude --plugin-dir ./plugin
```

### 3) Codex 실행 (설치 방식 공통)

```bash
# Codex 인증 초기화 (최초 1회)
bash plugin/bin/codex_bootstrap.sh

# 코딩 위임 (설계·ADR 확정 후)
bash plugin/bin/codex_run.sh "<코딩 프롬프트>" [expected_stdout_substring]
#   → runs/run_XXXX/ 에 작업물 + diff + 자동 QA. exit 0=게이트 통과, !=0=재작업/차단
```

- 코딩 실행기: **codex mcp-server 주력 + codex exec 보조** (`.mcp.json`)
- 상태는 전부 파일로, 승인은 게이트로, 완료는 증거로 판정.

> **로컬(`--plugin-dir`) = 개발, 마켓플레이스 = 배포.** 대립이 아니라 단계 차이다. 고칠 땐 로컬로 빠르게, 배포는 마켓플레이스로.

---

## 안전 경계 (5겹 다층 방어)

codex는 claude와 **별도 프로세스**라 claude의 훅/스킬이 자동 적용되지 않는다.
그래서 다층으로 막는다. **어느 하나도 단독 완결이 아니다.**

| 겹 | 방어 | 시점 | 근거 |
|----|------|------|------|
| 1 | **codex PreToolUse 가드 훅** (claude 가드 이식) | 실행 **직전** 차단 | `plugin/.codex/hooks/` |
| 2 | 위임 프롬프트 사전 스캔 (`scan_danger`) | 위임 전 거부 | `bin/scan_danger.py` |
| 3 | 실행 중 rollout 로그 감사 (escape/opaque) | 실행 후 탐지·표면화 | `bin/audit_codex_log.py` |
| 4 | git diff + qa_verify + **사람 승인(P1)** | 결과물 게이트 | `bin/qa_verify.sh` |
| 근본 | **컨테이너 네트워크/FS 격리** | 물리 차단 | 호스트 작업 (아래) |

### 정직한 한계
- codex PreToolUse 훅·로그 감사는 **"명령 텍스트" 기반**이라, 인터프리터 내부 유출
  (`python3 -c 'open(...).write(...)'`) 같은 변형은 못 잡는다(정규식의 근본 상한).
- 즉 위 1~4겹은 강력한 **탐지·사전차단**이지 **완전 차단막이 아니다.**
- **완전 무인 자동화의 유일한 근본 경계 = 컨테이너 격리.** 그 전까지는 **사람 검토(P1) 전제 반자동**으로 안전하게 운영 가능.

### 컨테이너 격리 (완전 자동화 시 남은 1건 — 호스트 root 작업)
이 컨테이너 내부에선 격리 불가(userns/seccomp/apparmor + CapEff=0, 실측 확인). 호스트에서:
- **A.** codex 전용 컨테이너를 `--network none` + 읽기전용 마운트 + workdir만 rw로 실행 (권장)
- **B.** 호스트 `apparmor_restrict_unprivileged_userns=0` + seccomp/apparmor 완화 → codex 내장 샌드박스 복원
- 상세: `design/HOST_KERNEL_SETUP.md`, `design/CODEX_SAFETY_FINAL.md`

---

## 검증 상태 (전부 실측)

- **코드 회귀 48/48**: scan_danger 10 + guard_hook 8 + audit_escape 20 + codex_hook 10
- **스킬 골든셋**: adr-check(충돌/무충돌) + design-grill(게이트 HELD) 라이브 재현
- **e2e 실전**: `envlint`(.env 검증기)를 설계→ADR→Codex코딩→검사 전 과정으로 생산, 13+11 독립검증 통과 (`e2e/`)
- **측정기 신뢰성**: 방어 무력화 시 테스트가 RED 나는지 확인(빈 껍데기 아님)

```bash
# 전체 회귀 실행
for t in scan_danger guard_hook audit_escape codex_hook; do
  python3 plugin/tests/test_$t.py
done
```

---

## 디렉토리

```
plugin/
  .claude-plugin/plugin.json   # 매니페스트 (name: codex-harness)
  .mcp.json                    # codex mcp-server 연결
  skills/                      # design-grill · adr-check · harness-run
  bin/                         # codex_run · qa_verify · scan_danger · audit_codex_log · codex_bootstrap · codex-mcp
  hooks/                       # claude PreToolUse 가드 (guard_dangerous.sh)
  .codex/hooks/                # codex PreToolUse 가드 (이식본)
  lib/danger_patterns.txt      # claude·codex 공유 위험 패턴 (단일 소스)
  tests/                       # 회귀 48 + 골든셋
design/                        # 설계서·회의기록·안전 실측 (31개 문서)
e2e/                           # 실전 테스트 산출물 (envlint)
```

## 설계 근거 문서 (design/)
- `design_doc.html` — 8섹션 통합 설계서 (렌더 확인)
- `CODEX_GUARD_TRANSPLANT.md` — 훅 이식(사전 차단) 실증
- `CODEX_SAFETY_FINAL.md` — 안전 종합 + 격리 선택지
- `qa_*` / `devlead_*` — QA·개발 실측 기록 (FN1~FN5-D 결함 소거 이력)

---

## Phase 2 (미결·선택)
- 컨테이너 격리 도입 (완전 자동화 시) — 수장 결정
- codex execpolicy `.rules` 병행 (이중 사전 차단, 이미 실증)
- 골든셋 케이스 강화 (스킬 없이는 틀리는 난이도)
- FN4 인터프리터 one-liner 완화 (근본은 격리)
