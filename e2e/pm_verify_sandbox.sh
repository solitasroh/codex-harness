#!/usr/bin/env bash
# codex 자체 sandbox(workspace-write) 실측 — 이 환경(userns 제약)에서 실제 격리되나.
# codex sandbox <mode> -- <cmd> 로 명령을 codex 샌드박스 안에서 실행.
set -uo pipefail
cd /opt/data/projects/cc-plugin
export CODEX_HOME="$PWD/.codex_home"
TMP="$(mktemp -d)"; WD="$TMP/wd"; mkdir -p "$WD"
OUTSIDE="$TMP/outside_secret.txt"

echo "=== codex sandbox 모드별 실측 ==="
echo "--- workspace-write: workdir 안 쓰기는 OK, 밖은 차단 기대 ---"

echo "[테스트1] workdir 안 쓰기 (허용 기대)"
codex sandbox -c "sandbox_mode=\"workspace-write\"" -- bash -lc "echo ok > $WD/inside.txt" 2>&1 | grep -viE "warning|bubblewrap" | head -3
[ -f "$WD/inside.txt" ] && echo "  → inside.txt 생성됨 (쓰기 동작)" || echo "  → 쓰기 실패(샌드박스가 막았거나 오류)"

echo "[테스트2] workdir 밖(/tmp) 쓰기 (차단 기대)"
codex sandbox -c "sandbox_mode=\"workspace-write\"" -- bash -lc "echo leak > $OUTSIDE" 2>&1 | grep -viE "^warning|bubblewrap" | head -5
if [ -f "$OUTSIDE" ]; then echo "  → ❌ 밖 쓰기 성공 = 격리 안 됨"; else echo "  → ✅ 밖 쓰기 차단됨 = 격리 작동"; fi

echo
echo "--- read-only: 어디도 못 쓰기 기대 ---"
codex sandbox -c "sandbox_mode=\"read-only\"" -- bash -lc "echo x > $WD/ro.txt" 2>&1 | grep -viE "^warning|bubblewrap" | head -3
[ -f "$WD/ro.txt" ] && echo "  → ❌ read-only인데 썼음" || echo "  → ✅ read-only 쓰기 차단"

rm -rf "$TMP"
echo "=== 끝 ==="
