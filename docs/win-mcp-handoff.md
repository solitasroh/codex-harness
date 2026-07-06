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

## 참고
- skill: `claude-codex-harness-plugin` (플러그인 구조·배포·MCP 배선 전반)
- 마켓플레이스 이름 = `sol-dev`, 플러그인 식별자 = `codex-harness`, 설치 = `claude plugin marketplace add solitasroh/codex-harness` → `claude plugin install codex-harness@sol-dev`
