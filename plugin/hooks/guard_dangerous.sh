#!/usr/bin/env bash
# PreToolUse 훅(Bash) — 위험 명령 차단. exit 2 = block(Claude Code 규약).
# stdin으로 툴 입력 JSON이 들어옴: {"tool_input":{"command":"..."}}
#
# ★ 단일 원본화(2026-07-07, 백팀장 / 브라이언 검증딥다이브 ②):
#   이전엔 자체 BLOCK_PATTERNS 배열을 하드코딩해 scan_danger.py·codex python훅과 발산했다
#   (실측: os.system/subprocess/eval/--yolo를 bash훅만 놓침). 이제 이 훅도 lib/danger_patterns.txt
#   단일 원본을 읽는다. shell:+code: 계층을 로드(셸 명령엔 코드 패턴도 나타나므로 code 포함).
#   접두어 없는 구형 라인은 code 계층으로 간주(하위호환).
set -uo pipefail

INPUT="$(cat)"
CMD="$(printf '%s' "$INPUT" | python3 -c 'import sys,json;
try: print(json.load(sys.stdin).get("tool_input",{}).get("command",""))
except Exception: print("")' 2>/dev/null)"

# 패턴 원본 위치 해석: DANGER_PATTERNS(env) > 훅 상대경로 > 절대경로 폴백
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAT_FILE="${DANGER_PATTERNS:-}"
if [[ -z "$PAT_FILE" || ! -r "$PAT_FILE" ]]; then
  for c in "$HERE/../lib/danger_patterns.txt" "/opt/data/projects/cc-plugin/plugin/lib/danger_patterns.txt"; do
    [[ -r "$c" ]] && { PAT_FILE="$c"; break; }
  done
fi

# shell:/code: 계층 패턴만 추출(주석·빈 줄 제외), 정규식 본문만 배열로.
mapfile -t BLOCK_PATTERNS < <(
  grep -E '^(shell|code):' "$PAT_FILE" 2>/dev/null | sed -E 's/^[^ ]+ //'
)

# ★ fail-closed(브라이언 철학): 패턴 0개 = 원본 로드 실패 = 판단 불가 → 안전측 차단.
#   조용히 통과(fail-open) 금지. python 훅과 동일 계약.
if [[ "${#BLOCK_PATTERNS[@]}" -eq 0 ]]; then
  echo "codex-harness guard: 위험 패턴 원본 로드 실패(0개) — 안전측 차단(fail-closed)" >&2
  exit 2
fi

for pat in "${BLOCK_PATTERNS[@]}"; do
  # -e 필수: '--yolo' 같이 '--'로 시작하는 패턴을 grep이 옵션으로 오해하는 것 방지(실측 발산 원인).
  if printf '%s' "$CMD" | grep -Eq -e "$pat"; then
    echo "codex-harness guard: 위험 명령 차단 (pattern: $pat)" >&2
    echo "차단된 명령: $CMD" >&2
    exit 2
  fi
done

exit 0
