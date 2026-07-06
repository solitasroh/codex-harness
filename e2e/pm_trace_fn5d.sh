#!/usr/bin/env bash
# Traceback 원인 격리 — 위험문자열(cp /etc/passwd) 대신 mkfs 없는 안전 escape(tee /outside)로.
set -uo pipefail
cd /opt/data/projects/cc-plugin
TMP="$(mktemp -d)"; WD="$TMP/wd"; mkdir -p "$WD"
export CODEX_HOME="$TMP/ch"; mkdir -p "$CODEX_HOME/sessions/2026/07/06"
LOG="$CODEX_HOME/sessions/2026/07/06/r.jsonl"

# cwd 불일치 + escape_write (tee로 workdir 밖 쓰기) — 위험 키워드 없이 escape 유발
python3 - "$LOG" <<'PY'
import json,sys
log=sys.argv[1]
lines=[
  {"timestamp":"t","type":"session_meta","payload":{"cwd":"/some/other/path"}},
  {"timestamp":"t","type":"response_item","payload":{"type":"function_call","name":"exec_command",
     "arguments":json.dumps({"command":["bash","-lc","echo x | tee /outside_dir/leak.txt"]})}},
]
open(log,"w").write("\n".join(json.dumps(l) for l in lines)+"\n")
PY

echo "=== Traceback 전문 (matched 0건 + unmatched 1건 경로) ==="
python3 plugin/bin/audit_codex_log.py --session-after 0 --workdir "$WD" 2>&1 | tail -20
echo "exit=$?"
rm -rf "$TMP"
