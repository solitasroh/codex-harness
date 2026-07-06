#!/usr/bin/env bash
set -uo pipefail
cd /opt/data/projects/cc-plugin
RULES=".codex_home/rules/default.rules"
MK="mkfs.ext4"; DEV="/dev/sda"

dec() { codex execpolicy check --rules "$RULES" -- "$@" 2>&1 | grep -v WARNING | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('decision','allow(no-match)'))" 2>/dev/null || echo "parse-err"; }

echo "=== compound 분해 조건 탐색 ==="
echo -n "1) bash -lc 'echo hi && mkfs.ext4 /dev/sda' : "; dec bash -lc "echo hi && $MK $DEV"
echo -n "2) sh -c 'mkfs.ext4 /dev/sda'              : "; dec sh -c "$MK $DEV"
echo -n "3) bash -lc 'mkfs.ext4 /dev/sda'           : "; dec bash -lc "$MK $DEV"
echo -n "4) bash -lc 'git add . && mkfs.ext4 /dev/sda': "; dec bash -lc "git add . && $MK $DEV"
