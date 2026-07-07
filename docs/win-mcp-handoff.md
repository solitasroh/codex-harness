# 윈도우 MCP 연동 개선 — 백팀장 인수인계 노트

작성: 자비서(PM) / 2026-07-06 / codex-harness 윈도우 실행 이슈

## 증상
윈도우에서 플러그인 실행 시 **MCP codex 툴이 안 붙음**. `bin/codex_run.sh`(일회용 격리 workdir 파이프라인) 폴백 + PATH의 codex CLI로만 동작. → 정식 MCP 통로(멀티턴 codex-reply 등)가 막힘.

## 근본 원인 (확인 완료)
`plugin/.mcp.json`이 MCP 서버 실행 command로 `${CLAUDE_PLUGIN_ROOT}/bin/codex-mcp.sh`(bash 스크립트)를 지정.
→ 윈도우는 `.sh`를 직접 exec 못 함 → MCP 서버 기동 실패.
그 래퍼의 존재 이유(루트 소유 config 600 트랩 우회 + CODEX_HOME 세팅)는 **리눅스 컨테이너 한정** 문제라, 윈도우엔 애초에 불필요.

## 스코프 A — MCP가 윈도우에서 붙게 (1순위, 핵심 증상 해결)
`.mcp.json`을 셸 래퍼 대신 codex를 직접 부르도록 크로스플랫폼화:
```json
{ "mcpServers": { "codex": {
  "command": "codex", "args": ["mcp-server"],
  "env": { "CODEX_HOME": "${CLAUDE_PLUGIN_ROOT}/.codex_home" }
} } }
```
**단, 결정 필요한 갈림길 — CODEX_HOME 처리 (팀장 실측 후 결정):**
- 리눅스 컨테이너: `/opt/data/.codex/config.toml`이 root:600 → 플러그인 로컬 CODEX_HOME 우회 **필수**. bootstrap이 그 폴더에 auth.json+config.toml 생성해야 mcp-server가 인증됨.
- 윈도우: codex CLI가 이미 기본 CODEX_HOME(`%USERPROFILE%\.codex`)로 로그인돼 있을 가능성 큼(codex_run.sh가 도는 정황). 이 경우 CODEX_HOME을 플러그인 로컬로 고정하면 **빈 폴더를 가리켜 오히려 인증 깨짐**.
- `.mcp.json`은 정적 파일이라 OS 분기 불가. → **팀장이 윈도우에서 codex 로그인/CODEX_HOME 상태를 실측해 방향 결정**.

두 방향:
- **(a)** env로 CODEX_HOME 고정 + 윈도우용 bootstrap(.ps1/.cmd) 신설해 양 OS 모두 그 폴더를 채움. 일관성 최고, 작업량 큼.
- **(b)** CODEX_HOME 미지정(codex 기본 사용) + 리눅스 컨테이너 root 트랩은 다른 방법으로. 윈도우 단순, 리눅스 회귀 위험 있어 회귀 테스트 필수.

## 스코프 B — 안전장치 보전
래퍼가 하던 "auth.json 없으면 조용히 죽지 않고 큰 소리로 실패"(codex-mcp.sh 11~14줄)가 사라짐.
→ `harness-run` SKILL 3단계 선행체크 or `codex_bootstrap` 완료검증으로 이관할지 결정.

## 스코프 C — 전체 윈도우 지원 (별도 스코프, 대공사)
스코프 A만으로 MCP는 붙지만, 나머지 bash 자산은 여전히 유닉스 가정:
- `codex_bootstrap.sh`: auth 소스 `/opt/data/.codex/auth.json` 하드코딩 → 윈도우 경로 분기 필요.
- `codex_run.sh`가 생성하는 `hooks.json`: `/usr/bin/env`, `/usr/bin/python3` 절대경로(48줄) → 윈도우 python 경로로 깨짐.
- 모든 .sh: 윈도우는 git-bash 존재 가정. PowerShell 네이티브 포팅은 대공사 → 별건으로 판단.

## 검증 (완료 기준)
윈도우에서:
```
claude plugin marketplace update
claude mcp list      # plugin:sol-dev:codex ... ✔ Connected 확인이 완료 신호
```

---

# 백팀장 작업 로그 (2026-07-07, 스코프 C 리눅스 착수분)

수장 지시: "1번 — 이 플러그인은 대부분 윈도우 환경에서 사용." → 윈도우/.NET 주력 이식.
아래는 **리눅스 컨테이너에서 실제로 실행·검증까지 끝낸** 부분. 윈도우 실기 실측이 남은 부분은 §마지막.

## 완료 (리눅스에서 실증)
1. **.NET 검사 게이트 신설 (`bin/qa_verify.py`, 크로스플랫폼).**
   - 러너 자동감지: `.sln`/`.csproj`→`dotnet build`+`dotnet test`, 없으면 pytest(부재 시 함수 직접호출 폴백).
   - `qa_verify.sh` 는 `qa_verify.py` 호출 shim 으로 축소(기존 리눅스 호출자 무손상).
   - **실증(4케이스)**: 실제 xUnit 프로젝트로 PASS→exit0 / 고의실패→exit1(테스트 진짜 돌려 FAIL 포착),
     pytest 폴백→exit0, 테스트없음→경고+exit0. dotnet SDK 8.0.422 로컬설치(ICU 없어 INVARIANT=1)로 검증.
2. **가드 훅 크로스플랫폼 지뢰 제거 (`.codex/hooks/pre_tool_use_guard.py`).**
   - 이전엔 패턴파일 폴백이 리눅스 절대경로 하나뿐 → 윈도우선 패턴0개 → fail-closed 로 **안전명령까지 전면 deny**.
   - 수정: 훅이 자기 옆(`HERE/danger_patterns.txt`)을 1순위 자가탐색 + `CLAUDE_PLUGIN_ROOT/lib` 후보 추가.
   - 설치측(`codex_run.sh`·`codex_bootstrap.ps1`)이 훅 복사 시 패턴파일도 동반 복사.
   - **실증**: 격리폴더+env제거(윈도우 재현)에서 안전명령 allow / `rm -rf /` deny / 패턴없으면 fail-closed deny.
   - 회귀 3건 추가(`test_codex_hook.py`), 전체 pytest 62 passed.
3. **경로 이식성 (`codex_run.sh` hooks.json 생성부).**
   - `/usr/bin/env`·`/usr/bin/python3` 하드코딩 → `command -v python3` 로 탐색. 패턴 동반 복사 추가.
4. **`bin/codex_bootstrap.ps1` 에 가드 훅 설치 로직 추가.**
   - 기존엔 auth 만 심고 훅 미설치 → 윈도우 MCP 경로(codex_run.sh 안 거침)엔 가드 통로 없음.
   - config.toml 뒤에 훅+패턴+hooks.json 설치 섹션 신설. python 탐색(py→python→python3), JSON 백슬래시 이스케이프.
   - **실증**: pwsh 7.4.6(리눅스, INVARIANT=1)로 ps1 실제 실행 → auth/config/hooks/패턴 5파일 생성 확인,
     config.toml 윈도우 안전측 정책(on-request/workspace-write)·BOM없음 확인, 설치된 훅 자가탐색 동작 확인.

## ⚠ 윈도우 실기에서만 닫히는 부분 (리눅스에서 증명 불가 — 반드시 실측)
- **[스코프4] CODEX_HOME 갈림길 최종 결정.** `.mcp.json` 은 정적파일이라 OS분기 불가.
  현재 방침: `CODEX_HOME=${CLAUDE_PLUGIN_ROOT}/.codex_home` 고정 + bootstrap.ps1 이 그 폴더를 채움(방향 a).
  윈도우 실기에서 확인할 것:
  1. `codex login status` 로 기존 로그인 위치(`%USERPROFILE%\.codex` 인지) 실측.
  2. bootstrap.ps1 실행 후 `%CLAUDE_PLUGIN_ROOT%\.codex_home\auth.json` 이 실제로 채워지는지.
  3. `claude mcp list` 에서 codex 가 ✔ Connected 인지(=mcp-server 가 그 CODEX_HOME 으로 인증 성공).
  4. 실제 코딩 위임 1건 성공(tools/call 이 조용히 안 죽는지 — 선행체크가 잡는 그 가짜연결 여부).
  → 만약 고정 CODEX_HOME 이 기존 로그인을 못 살리면 방향 b(미지정) 재검토. 단 리눅스 회귀 필수.
- **[스코프4] icacls 권한축소.** ps1 의 icacls 는 리눅스 pwsh 에선 없어서 best-effort 경고만 났다.
  윈도우 실기에서 auth.json 이 현재사용자 전용(R)으로 실제 축소되는지 확인.
- **[.NET 게이트] dotnet 실기 확인.** 윈도우엔 ICU 있으니 INVARIANT 불요. `dotnet test` 가 실제 xUnit
  프로젝트에서 도는지, qa_verify.py 의 러너감지가 윈도우 경로(백슬래시)에서도 정상인지.
- **[python 런처] hooks.json 의 python.** ps1 은 `py`→`python`→`python3` 순 탐색. 윈도우에 py런처만 있고
  python 이 PATH 에 없는 흔한 케이스에서 훅이 실제 실행되는지 확인.

## 윈도우 검증 체크리스트 (완료 기준 = 전부 ✔)
```
1. git pull 후: claude plugin marketplace update
2. (사용자 codex 로그인 상태에서) bin\codex_bootstrap.ps1 실행 → 5파일 생성·경고 없이 완료
3. claude mcp list → codex ✔ Connected
4. harness-run 으로 실제 .NET 기능 코딩 위임 1건 → 성공
5. qa_verify.py <workdir> 가 xUnit 테스트를 진짜 돌려 pass/fail 판정 (fail 시 exit1)
6. 위험 명령 위임 시도 → 가드 훅이 deny (안전명령은 통과)
```
리눅스에서 짠 코드만으론 "완료" 아님. 위 6개가 윈도우 실기에서 ✔ 나야 스코프 C 종료.

## 참고
- skill: `claude-codex-harness-plugin` (플러그인 구조·배포·MCP 배선 전반)
- 마켓플레이스 이름 = `sol-dev`, 플러그인 식별자 = `codex-harness`, 설치 = `claude plugin marketplace add solitasroh/codex-harness` → `claude plugin install codex-harness@sol-dev`
