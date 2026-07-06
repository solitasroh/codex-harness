#!/usr/bin/env bash
# PreToolUse 훅(Bash) — 위험 명령 차단. exit 2 = block(Claude Code 규약).
# QA 소관 정책의 DevLead측 골격. 실제 차단 규칙 세부는 브라이언(QA)이 확정.
# stdin으로 툴 입력 JSON이 들어옴: {"tool_input":{"command":"..."}}
set -uo pipefail

INPUT="$(cat)"
CMD="$(printf '%s' "$INPUT" | python3 -c 'import sys,json;
try: print(json.load(sys.stdin).get("tool_input",{}).get("command",""))
except Exception: print("")' 2>/dev/null)"

# 파괴적/유출 패턴 (초안 — QA가 확정)
BLOCK_PATTERNS=(
  'rm[[:space:]]+-rf[[:space:]]+/'
  'curl[^|]*\|[[:space:]]*(sudo[[:space:]]+)?(ba)?sh'
  'wget[^|]*\|[[:space:]]*(ba)?sh'
  ':\(\)[[:space:]]*\{.*&[[:space:]]*\}[[:space:]]*;[[:space:]]*:'          # fork bomb (공백 변형 포괄)
  'mkfs\.'
  'dd[[:space:]]+if=.*of=/dev/'
  '>[[:space:]]*/dev/sd'
  'chmod[[:space:]]+-R[[:space:]]+777[[:space:]]+/'
)

for pat in "${BLOCK_PATTERNS[@]}"; do
  if printf '%s' "$CMD" | grep -Eq "$pat"; then
    echo "codex-harness guard: 위험 명령 차단 (pattern: $pat)" >&2
    echo "차단된 명령: $CMD" >&2
    exit 2
  fi
done

exit 0
