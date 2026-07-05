# PM 브리프: Codex 코딩 위임 — "플러그인" vs "MCP" 정확한 비교

작성: 자비서(PM) | 근거: 이 서버 실물 검증 + 공식문서 + 오픈소스 교차확인
질문(Soojang): "1번(검증 먼저)으로 가되, openai-codex 플러그인을 쓰는 게 맞는지 vs MCP로 코드 구현시키는 게 맞는지 정확히 체크"

---

## TL;DR (결론 먼저)

**둘은 대립 개념이 아니라 "레이어가 다른" 선택지다. 정확히는 3가지 경로가 있다.**

| 경로 | 무엇인가 | 우리 상황 적합도 |
|------|---------|----------------|
| **A. openai-codex 클로드코드 플러그인** | Claude Code에 설치하는 서드파티 플러그인. 내부적으로 `codex-companion.mjs`(node 스크립트)로 Codex CLI를 감싸 호출 | △ 편하지만 출처·유지보수 불확실(비공식) |
| **B. Codex를 MCP 서버로 붙임** (`codex mcp-server`) | Codex 자신이 MCP 서버가 되어 `codex`/`codex-reply` 툴 2개를 노출. Claude가 MCP 클라이언트로 호출 | ◎ 공식기능·표준규격·검증 완료 |
| **C. codex exec 직접 호출** (영상 1 방식) | 셸에서 `codex exec "..."` 헤드리스 실행. Claude 훅/스크립트가 부름 | ○ 가장 단순·자율루프에 최적 |

**핵심 사실: B(MCP)는 Codex CLI에 이미 내장된 공식 기능이고, 이 서버에서 실제로 작동함을 방금 확인했다. A(플러그인)는 결국 내부에서 CLI를 감싸는 래퍼일 뿐이다.**

---

## 검증 실측 결과 (이 서버, 2026-07-05)

### 환경
- codex CLI `0.142.3` (`/usr/local/bin/codex`), 인증 `~/.codex/auth.json` ✅
- claude CLI `2.1.185` ✅ / node v22.22.3 ✅
- 현재 클로드코드에 등록된 MCP 서버: **없음** (`claude mcp list` → none)
- 현재 설치된 클로드코드 플러그인 캐시: **없음** (`~/.claude/plugins/cache` 부재)

### codex 서브커맨드에서 밝혀진 결정적 구분
- `codex mcp` = Codex가 **외부** MCP서버를 소비하도록 관리 (우리 목적 아님, 혼동 주의)
- `codex mcp-server` = **Codex 자신을 MCP 서버(stdio)로 기동** ← MCP 경로의 실체
- `codex plugin` = Codex **자체** 플러그인 시스템(별개 생태계)
- `codex exec` = 헤드리스 1회 실행

### codex mcp-server 직접 프로브 결과 (JSON-RPC 실측)
- serverInfo: `{"name":"codex-mcp-server","title":"Codex","version":"0.142.3"}`
- **노출 툴 딱 2개:**
  1. **`codex`** — Codex 세션 시작. 입력: `prompt`(필수) + `approval-policy`(untrusted/on-failure/on-request/never) + `sandbox`(read-only/workspace-write/danger-full-access) + `model`/`cwd`/`base-instructions`/`developer-instructions`. 출력: `{threadId, content}`
  2. **`codex-reply`** — `threadId`로 대화 이어가기. 입력: `prompt`+`threadId`. 출력: `{threadId, content}`
- 함의: MCP 경로는 "Claude가 codex 툴을 호출 → Codex가 자기 샌드박스에서 코딩 → threadId로 멀티턴" 구조. 승인정책·샌드박스를 **호출 인자로 세밀 제어** 가능.

### 권한 이슈 (실무 주의점 — 발견 & 우회 완료)
- `~/.codex/config.toml`이 root:root 600 소유 → hermes 유저가 못 읽어 `codex mcp-server`가 config 로드 실패.
- 우회: `CODEX_HOME=/tmp/codex_probe`에 auth.json 복사 + 최소 config.toml 작성 → 정상 작동 확인.
- → **실전 배포 시 CODEX_HOME 지정 또는 config.toml 권한 조정 필요.** (인프라 항목)

### openai-codex 플러그인(A)의 정체
- Anthropic 공식 저장소(anthropics/claude-code/plugins)에는 **없음** (공식은 feature-dev, code-review, plugin-dev 등만).
- cookoff 스킬이 참조하는 경로: `~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs`
- 즉 **서드파티 마켓플레이스 플러그인**이며, 내부적으로 node 래퍼로 Codex CLI를 호출. 기능적으로는 C(codex exec/세션)를 예쁘게 포장한 것.

---

## 세 경로 상세 비교

### A. openai-codex 플러그인
- **장점**: Claude Code 안에서 슬래시/스킬로 자연스럽게 호출, cookoff 같은 상위 스킬이 바로 물림, 설치 한 줄.
- **단점**: 비공식·출처 불명(유지보수/보안 감사 부담), 내부 동작이 블랙박스(node 래퍼), 버전 디렉토리 변동으로 경로 동적 resolve 필요, 우리가 통제 못 하는 의존성.
- **적합**: max4c/skills(cookoff 등)를 "그대로" 검증할 때.

### B. Codex MCP 서버 (`codex mcp-server`)
- **장점**: **공식 기능**, MCP 표준 규격(다른 MCP 클라이언트와도 호환), 승인정책·샌드박스를 인자로 정밀 제어, threadId 멀티턴 네이티브, `claude mcp add`로 등록하면 Claude가 표준 툴로 인식. 투명함.
- **단점**: 초기 설정(등록 + CODEX_HOME/권한) 필요, MCP 툴 결과가 큰 diff일 때 컨텍스트 관리 필요, "codex 툴" 1개라 워크플로 로직(그릴링/검수 순서)은 우리가 스킬로 짜야 함.
- **적합**: 장기적으로 우리 플러그인이 Codex를 안정적으로 부리는 표준 백엔드.

### C. codex exec 직접 (영상 1)
- **장점**: 가장 단순, 자율 실행 루프(executor)에 자연스러움, 훅으로 TDD가드 결합 쉬움, 완전 통제.
- **단점**: 멀티턴 상태는 우리가 세션관리(resume) 해야, MCP 같은 표준 인터페이스 아님(스크립트 접착제 필요).
- **적합**: "Grill me→스펙→codex exec 자율루프" 재현(영상 1 그대로).

---

## PM 예비 판단 (회의 안건)

> **표면적 답: "MCP가 더 정석이다."** Codex를 코딩 실행기로 붙이는 표준·공식·투명한 방법은 B(codex mcp-server)다. A(플러그인)는 결국 CLI 래퍼이므로, 통제·보안·유지보수 관점에선 B가 우월.
>
> **단, 목적이 "1번=검증 먼저"임을 감안하면:** 검증 단계에선 A(cookoff 포함 max4c/skills)를 그대로 깔아 파이프라인을 눈으로 확인하는 게 빠르고, 확인 후 우리 플러그인의 코딩 백엔드는 B(MCP)로 표준화하는 하이브리드가 합리적.

**회의에서 확정할 것:**
1. 검증 단계 백엔드를 A로 할지, 처음부터 B로 갈지
2. 최종 아키텍처의 코딩 실행기를 B(MCP) vs C(exec) 중 무엇으로
3. CODEX_HOME/권한 등 인프라 선결과제 처리 방식
4. 보안(비공식 플러그인 사용 여부, 샌드박스 정책 기본값)
