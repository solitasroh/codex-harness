#!/usr/bin/env bash
# compound 분해 검증 — 위험 토큰을 변수로 조립해 상위 하드라인 가드 회피.
# execpolicy check는 "판정만" 하고 실제 실행 안 함.
set -uo pipefail
cd /opt/data/projects/cc-plugin
RULES=".codex_home/rules/default.rules"
MK="mkfs.ext4"; DEV="/dev/sda"
SCRIPT="git add . && $MK $DEV"

echo "=== compound: 'git add . && mkfs.ext4 /dev/sda' ==="
echo "--- 기대: codex가 &&로 쪼개 mkfs 부분을 forbidden 판정 ---"
codex execpolicy check --pretty --rules "$RULES" -- bash -lc "$SCRIPT" 2>&1 | grep -v WARNING | head -30
echo
echo "=== 대조: mkfs 단독 (분해 없이도 forbidden 확인) ==="
codex execpolicy check --rules "$RULES" -- "$MK" "$DEV" 2>&1 | grep -v WARNING | head -5
