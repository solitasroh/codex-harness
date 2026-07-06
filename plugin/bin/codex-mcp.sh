#!/usr/bin/env bash
# codex mcp-server 래퍼 — 플러그인이 CODEX_HOME을 자동 세팅해 root:600 config trap을 우회.
# .mcp.json에서 이 스크립트를 command로 지정. CLAUDE_PLUGIN_ROOT는 Claude Code가 주입.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# 프로젝트별 CODEX_HOME: 우선순위 = 환경변수 > 플러그인 로컬 .codex_home
export CODEX_HOME="${CODEX_HARNESS_CODEX_HOME:-$PLUGIN_ROOT/.codex_home}"

# 부트스트랩 미완이면 안내 후 종료(조용한 실패 방지)
if [[ ! -r "$CODEX_HOME/auth.json" ]]; then
  echo "codex-harness: CODEX_HOME 미초기화($CODEX_HOME). 먼저 bin/codex_bootstrap.sh 실행." >&2
  exit 1
fi

exec codex mcp-server
