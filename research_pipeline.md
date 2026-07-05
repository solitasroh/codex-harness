# 리서치: Claude로 설계(Grill me + ADR) → Codex로 코딩 파이프라인

작성: 자비서 | 근거: 영상 2편 + 실물 GitHub 저장소/공식 문서 교차검증
목적: "클로드 코드로 Grill me 설계 → ADR 체크 → 코덱스에 코딩 위임"을 실제로 구현하기 위한 방안 리서치

---

## 0. 우리 환경 (실측 완료)

| 항목 | 상태 |
|------|------|
| codex CLI | ✅ `/usr/local/bin/codex` v0.142.3 |
| claude CLI | ✅ `/usr/local/bin/claude` v2.1.185 |
| codex 인증 | ✅ `~/.codex/auth.json` 존재 |
| node / npm | ✅ v22.22.3 / 11.17.0 |

→ 영상에서 쓴 도구(claude + codex CLI)가 이 서버에 이미 다 깔려 있고 인증도 됨. 바로 실험 가능.

---

## 1. 영상이 제시한 파이프라인 (요약)

### 영상 1 "루프 엔지니어링" — 1인 파이프라인
```
Grill me(면접관) → PRD 확정 → 수동설계와 병합 → 하네스로 phase·step 분해
   → executor.py 자율루프(Plan→Execute→Verify) → 훅(TDD가드) → 완성
   ※ 계획=Claude, 코딩=Codex(claude -p → codex exec로 "코덱스화")
```

### 영상 2 "하네스 멀티에이전트 2.0" — 벤더독립 멀티에이전트
```
플러그인 1회 설치 → "멀티에이전트 시스템 구성해줘" 한 줄
   → 오케스트레이터(켜는 벤더에 따라 Opus/GPT/Gemini) + 워커들
   → 팬아웃/팬인, 크리틱은 항상 다른 벤더가 검수
   → 상태 전부 파일(task.md/brief.md/result.md/context.md/learnings.md)
```

**우리가 조준할 부분**: 사용자 지시 = "Claude로 설계(Grill me+ADR) → Codex로 코딩". 
즉 영상 1의 핵심 파이프라인. 멀티에이전트 오케스트레이션(영상 2)은 나중에 얹을 수 있는 확장.

---

## 2. 실물 도구 리서치 결과 (교차검증 완료)

### 2-1. Grill me 스킬 — RobMitt/grill-me-skill (92★) ✅ 실물 확인
- 영상 속 스킬과 **정확히 일치**. 설명·설치법 동일.
- 설치: `~/.claude/skills/grill-me/SKILL.md` (또는 폴더 통째로)
- 트리거: "grill me" 또는 "이 계획 압박테스트해줘"
- **핵심 메커니즘** (SKILL.md 전문 확보):
  - `AskUserQuestion` 툴로만 질문 (평문 금지) → 객관식 팝업
  - **한 번에 하나씩**, 답 받고 다음 질문
  - 각 질문에 2~4개 구체적 선택지(+Other) → 결정 피로 최소화
  - 코드베이스로 답할 수 있으면 사용자에게 안 묻고 직접 탐색
  - 결정 트리 모든 갈래 해소될 때까지 → 끝나면 전체 결정 요약
- 로직/스크립트 없는 **순수 프롬프트 한 장**. (영상에서 "3~4줄"이라 한 것과 일치)

### 2-2. max4c/skills (6★) — 우리 프로젝트의 사실상 참조 아키텍처 ✅✅
"아이디어 → 검증된 코드"로 만드는 **spec-first 워크플로 플러그인**. 
Matt Pocock 스킬 + Ouroboros + Superpowers에서 영감. **완성형 클로드 코드 플러그인**(`.claude-plugin/` 매니페스트 보유).

수록 스킬(우리 목적과 직결되는 것 굵게):
| 스킬 | 역할 |
|------|------|
| **grill-me** | 5차원 모호성 리포트+게이트(Goals/Acceptance/Boundaries/Alternatives/Assumptions) |
| **grill-with-docs** | 도메인 인지 그릴링 — CONTEXT.md 용어집 + **ADR**에 대조, 결정 나면 문서 인라인 갱신 |
| **cookoff** | **Claude↔Codex를 심문자/응답자로 자동 그릴링** (openai-codex 플러그인 필요) |
| **write-prd** | 모호한 아이디어 → 근거 있는 PRD (코드탐색+소크라테스식 인터뷰+grill 게이트) |
| **tech-spec** | PRD → 기술 구현 스펙(모듈 분해, tracer-bullet 시퀀싱, grill 게이트) |
| **tdd** | red-green-refactor + vertical-slice tracer bullet |
| **verify-before-done** | 3단계 증거 루브릭(Mechanical/Behavioral/Consensus) |
| **release-plugin** | 클로드 코드 플러그인 배포(버전범프/CHANGELOG/머지) |
| handoff | 대화를 자체완결 인수인계 문서로 압축(세션 교체 대비) |

**합성 패턴**(README 명시):
```
caller → write-prd → grill-me → 모호성 리포트 → PRD 반환
                        ↓  (grill-me는 서브루틴으로 재사용)
```
철학: 합성>중복, 근거기반(메모리 아닌 실제 코드 읽기), 주장 전 증거, 능동 심문>수동 리뷰.

### 2-3. cookoff 스킬 — "코덱스화"의 실물 구현 ✅✅✅
사용자 지시("Codex에 코딩 진행")와 가장 직접 맞닿는 실제 코드. 전문 확보.
- **목적**: grill-me 인터뷰를 사용자 대신 AI끼리 시켜, 쉬운 80%는 자동 해소(`[CONSENSUS]`), 진짜 판단만 `[NEEDS MAX]`로 사용자에게.
- **2가지 모드**:
  - **relay**: Claude가 질문 생성 → Codex가 저자 역할로 답 → Claude 평가 → 반복(최대 10라운드, 차원당 3라운드)
  - **parallel**: Claude·Codex가 역할 바꿔 각자 전체 질문셋 → 병합(합의/충돌 태깅)
- **Codex 호출 방법**(핵심 발견):
  ```bash
  # openai-codex 플러그인 캐시의 companion 스크립트를 동적 resolve
  CODEX_SCRIPT=$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | sort -V | tail -1)
  node "$CODEX_SCRIPT" task --fresh "<prompt>"        # 새 대화
  node "$CODEX_SCRIPT" task --resume-last "<prompt>"  # 같은 스레드 이어가기
  ```
- 규칙: `--model`/`--effort`는 사용자 지정 없으면 미설정, cookoff는 read/analyze라 `--write` 안 씀, Codex가 에러/빈응답이면 **날조 금지·중단·보고**.

---

## 3. 클로드 코드 플러그인 시스템 (공식 문서 확인)

플러그인 = 자체완결 디렉토리 + `.claude-plugin/plugin.json` 매니페스트.

```
my-plugin/
├── .claude-plugin/
│   └── plugin.json         # name(네임스페이스), description, version, author
├── skills/<name>/SKILL.md   # 모델이 자동 호출 (task 문맥 기반)
├── commands/*.md            # 슬래시 커맨드(flat) — 신규는 skills/ 권장
├── agents/                  # 커스텀 서브에이전트
├── hooks/hooks.json         # 이벤트 훅(TDD 가드 등)
├── .mcp.json                # MCP 서버
├── .lsp.json                # LSP 서버
├── monitors/monitors.json   # 백그라운드 모니터(MAT 같은 상태추적)
├── bin/                     # 활성화 중 Bash PATH에 추가되는 실행파일
└── settings.json            # 기본 설정(agent 지정 가능)
```
- **주의**: commands/agents/skills/hooks는 `.claude-plugin/` 안에 넣으면 안 됨(루트에).
- 스킬 하나뿐이면 루트에 SKILL.md 직접 배치 가능.
- 테스트: `claude --plugin-dir ./my-plugin` (설치 없이 로드) → `/reload-plugins`로 핫리로드. **영상 2와 정확히 일치**.
- 배포: 마켓플레이스(`/plugin marketplace add <user>/<repo>` → `/plugin install <name>@<marketplace>`).
- 훅 타입 8종 중 우리에 유용: PostToolUse(포맷/린트), PreToolUse(위험명령 차단, exit 2=block), Stop(완료로깅), SessionStart(git status 로드).

---

## 4. 코덱스 위임(코딩) — 실행 옵션 3가지

| 방식 | 커맨드 | 용도 |
|------|--------|------|
| **A. companion 스크립트** (cookoff 방식) | `node codex-companion.mjs task --fresh/--resume-last` | Claude 세션 안에서 Codex를 대화형 스레드로. 그릴링·검수에 최적 |
| **B. codex exec 직접** (영상 1 방식) | `codex exec --full-auto "<task>"` | executor 루프에서 코딩 위임. 헤드리스 자율실행 |
| **C. delegate_task (Hermes)** | 자비서가 subagent로 | 우리 게이트웨이 안에서 병렬 위임 |

우리 환경 caveat(codex 스킬 문서): 게이트웨이 컨텍스트에서 bubblewrap 샌드박스가 깨질 수 있음 → 필요시 `codex exec --sandbox danger-full-access`, 안전은 프로세스 경계(workdir/git clean/좁은 프롬프트/diff리뷰)로.

---

## 5. 제안하는 우리 파이프라인 (사용자 지시 구현)

```
[1] 설계    Claude Code + grill-me      → 결정 트리 완주, 요약
[2] 근거화  Claude Code + write-prd     → 코드탐색 기반 PRD
[3] ADR     grill-with-docs (또는 자체) → CONTEXT.md 용어집 + ADR 기록/체크
[4] 스펙    tech-spec                   → PRD를 모듈 단위 구현스펙 + phase/step
[5] 위임    Codex (A 또는 B)            → 코딩. Claude는 크리틱/검수(다른 벤더가 검수)
[6] 검증    verify-before-done + tdd    → 증거 루브릭 통과해야 done
```
- **자기부트스트랩 가능**: max4c/skills를 참조로 우리만의 얇은 플러그인을 만들거나, 그대로 설치해 검증부터.
- **핵심 원칙 이식**: 상태를 파일로, 승인 게이트, AI 자기보고 불신·교차검증(우리 메모리 원칙과도 일치).

---

## 6. 다음 액션 후보 (사용자 결정 필요)

- **(가) 검증 먼저**: max4c/skills + grill-me + openai-codex 플러그인을 이 서버에 실제 설치 → 작은 아이디어로 [1]~[5] 한 바퀴 돌려 실측
- **(나) 자체 플러그인**: 우리 워크플로(자비서Studio) 맞춤 얇은 하네스 플러그인 신규 제작
- **(다) 영상 1 executor 재현**: Grill me→스펙→codex exec 자율루프 스크립트를 직접 구현

권장: **(가)** — 이미 검증된 오픈소스로 파이프라인을 눈으로 확인한 뒤, 부족한 부분만 (나)/(다)로 커스터마이즈. 리스크 최소.
