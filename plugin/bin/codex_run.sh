#!/usr/bin/env bash
# 격리 실행 래퍼 (A안: 사본 기반 위임) — 대상 repo의 일회용 사본에서 Codex에 코딩 위임하고
# diff를 캡처한다. 원본은 P1 사람 승인 전까지 불가침.
#
# 사용:
#   codex_run.sh "<코딩 프롬프트>" [expected_stdout_substring] [--target <repo_or_dir>]
#     --target 지정: 그 repo/폴더의 사본(git이면 worktree, 비-git이면 복제)에서 위임.
#                    → 기존 파일 수정 시나리오 지원(사본에 실제 코드가 있음). [A안 주 경로]
#     --target 생략: 빈 폴더 baseline(그린필드) — 신규 파일 생성 전용. [하위호환]
#
# 흐름: 사본생성 → (사본 안에서만)bypass 위임 → git diff 캡처 → rollout audit(escape) →
#       QA 검증 → [P1] 사람 diff 승인 안내 → (사람이 승인해야)원본 apply. 자동 apply 절대 금지.
# exit: 0=QA통과(P1 승인 후 apply 가능) / 1=재작업 / 3=프롬프트 거부 / 4=escape·audit 차단.
#
# ★ 안전 경계(설계문서 §1·§3-A): bypass(danger-full-access)는 "쓰기 되는 유일 경로"이나 위험하다.
#   진짜 경계는 codex sandbox 가 아니라 우리가 세운다:
#     (1) 일회용 사본 디렉터리 한정 실행(원본 불가침)
#     (2) 위임 후 git diff = 리뷰 아티팩트
#     (3) rollout 로그 audit = 사본 밖 절대경로 쓰기(escape) 사후 탐지
#     (4) ★P1 = 사람이 diff 승인해야만 원본 apply (이 스크립트는 apply 를 자동으로 하지 않는다)
#   ⚠ 리눅스 컨테이너는 외부격리라 bypass 가 정당화되지만, 윈도우 실기엔 컨테이너 외벽이 없다.
#     윈도우 등가물(codex_run.ps1)은 이 점 때문에 apply 를 절대 자동화하지 않고 P1 을 강제한다.
set -euo pipefail

# ── 인자 파싱 ──
PROMPT=""; QA_EXPECT=""; TARGET=""
_pos=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:?--target 에 repo/폴더 경로 필요}"; shift 2;;
    --target=*) TARGET="${1#--target=}"; shift;;
    *) _pos+=("$1"); shift;;
  esac
done
PROMPT="${_pos[0]:?사용법: codex_run.sh \"<프롬프트>\" [expected_substr] [--target <repo_or_dir>]}"
QA_EXPECT="${_pos[1]:-}"

# ── 경로 확정 (리눅스 하드코딩 제거 — Issue 2) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# PROJECT_ROOT: runs/ 산출물 저장 위치. 우선순위 env > CLAUDE_PLUGIN_ROOT > 플러그인 루트(스크립트 상위)
if [[ -n "${PROJECT_ROOT:-}" ]]; then
  :
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  PROJECT_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"   # bin/ 의 상위 = 플러그인 루트
fi
# CODEX_HOME: env 우선, 없으면 PROJECT_ROOT/.codex_home
export CODEX_HOME="${CODEX_HOME:-$PROJECT_ROOT/.codex_home}"

if [[ ! -r "$CODEX_HOME/auth.json" ]]; then
  echo "FATAL: CODEX_HOME 미초기화($CODEX_HOME). 먼저 codex_bootstrap.sh(.ps1) 실행." >&2; exit 1
fi

# ── 1) 위임 전 프롬프트 사전 스캔 (가드 1선) ──
if [[ -x "$SCRIPT_DIR/scan_danger.py" ]]; then
  if ! printf '%s\n' "$PROMPT" | python3 "$SCRIPT_DIR/scan_danger.py" --strict >/dev/null 2>&1; then
    echo "🔴 위임 거부: 프롬프트에 위험 지시 포함 (scan_danger --strict)" >&2
    printf '%s\n' "$PROMPT" | python3 "$SCRIPT_DIR/scan_danger.py" --strict >&2 || true
    exit 3
  fi
fi

# ── 1-b) codex PreToolUse 훅 설치 (P2: 위험패턴 실행 전 차단) ──
HOOK_SRC="$SCRIPT_DIR/../.codex/hooks/pre_tool_use_guard.py"
if [[ -f "$HOOK_SRC" ]]; then
  mkdir -p "$CODEX_HOME/hooks"
  cp -f "$HOOK_SRC" "$CODEX_HOME/hooks/pre_tool_use_guard.py"
  cp -f "$SCRIPT_DIR/../lib/danger_patterns.txt" "$CODEX_HOME/hooks/danger_patterns.txt"
  export DANGER_PATTERNS="$SCRIPT_DIR/../lib/danger_patterns.txt"
  PYBIN="$(command -v python3 || command -v python || echo /usr/bin/python3)"
  cat > "$CODEX_HOME/hooks.json" <<JSON
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|apply_patch|Edit|Write",
        "hooks": [
          { "type": "command",
            "command": "$PYBIN \"$CODEX_HOME/hooks/pre_tool_use_guard.py\"",
            "timeout": 20,
            "statusMessage": "위험 명령 검사(codex 이식 가드)" }
        ]
      }
    ]
  }
}
JSON
fi

# ── 2) 일회용 사본 생성 (A안 핵심) ──
#    git repo면 worktree, 비-git이면 복제. 사본 안에 실제 코드가 있어 "기존 파일 수정"이 diff로 잡힌다.
mkdir -p "$PROJECT_ROOT/runs"
WD="$(mktemp -d "$PROJECT_ROOT/runs/run_XXXXXX")"
COPY_MODE=""; WT_ORIGIN=""
cleanup() {
  # 사본 정리: worktree면 git worktree remove, 복제/그린필드면 그냥 rm.
  if [[ "$COPY_MODE" == "worktree" && -n "$WT_ORIGIN" ]]; then
    git -C "$WT_ORIGIN" worktree remove --force "$WD" 2>/dev/null || rm -rf "$WD"
  fi
  # (복제/그린필드는 호출측 판단에 맡겨 남겨둠 — diff/apply 후 사람이 확인. 필요시 rm.)
}

if [[ -n "$TARGET" ]]; then
  TARGET="$(cd "$TARGET" 2>/dev/null && pwd || true)"
  [[ -z "$TARGET" || ! -d "$TARGET" ]] && { echo "FATAL: --target 경로 없음/디렉터리 아님" >&2; rm -rf "$WD"; exit 1; }
  if git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # git repo → worktree (원본 커밋 HEAD 기준 사본). rm 로 만든 빈 WD 는 worktree add 가 거부하므로 제거 후 add.
    WT_ORIGIN="$(git -C "$TARGET" rev-parse --show-toplevel)"
    rm -rf "$WD"
    if git -C "$WT_ORIGIN" worktree add -q --detach "$WD" HEAD 2>/dev/null; then
      COPY_MODE="worktree"
      echo "[copy] git worktree: $WT_ORIGIN → $WD (HEAD detached)"
    else
      # worktree 실패(예: bare/이상상태) → 복제 폴백
      mkdir -p "$WD"; cp -a "$TARGET/." "$WD/"; rm -rf "$WD/.git"
      git -C "$WD" init -q; git -C "$WD" -c user.email=codex@local -c user.name=codex add -A
      git -C "$WD" -c user.email=codex@local -c user.name=codex commit -q -m baseline || true
      COPY_MODE="clone"; echo "[copy] worktree 실패 → 복제 폴백: $TARGET → $WD"
    fi
  else
    # 비-git → 복제 후 git init baseline
    cp -a "$TARGET/." "$WD/" 2>/dev/null || true
    git -C "$WD" init -q
    git -C "$WD" -c user.email=codex@local -c user.name=codex add -A
    git -C "$WD" -c user.email=codex@local -c user.name=codex commit -q -m baseline --allow-empty
    COPY_MODE="clone"; echo "[copy] 비-git 복제: $TARGET → $WD"
  fi
else
  # 하위호환: 그린필드(빈 폴더) baseline — 신규 파일 생성 전용
  git -C "$WD" init -q
  git -C "$WD" -c user.email=codex@local -c user.name=codex commit -q --allow-empty -m baseline
  COPY_MODE="greenfield"; echo "[workdir] 그린필드: $WD"
fi

# ── 3) Codex 위임 (사본 안에서만 bypass — 이 컨테이너에서 유일 동작 모드) ──
DELEGATE_START=$(date +%s)
codex exec \
  --skip-git-repo-check \
  --dangerously-bypass-approvals-and-sandbox \
  --dangerously-bypass-hook-trust \
  -C "$WD" \
  "$PROMPT" < /dev/null 2>&1 | grep -vE "^warning:|bubblewrap" || true

# ── 3) 변경 캡처 → 리뷰 게이트용 diff ──
git -C "$WD" add -A
echo "===== REVIEW DIFF (P1: 사람 승인 전 반드시 검토) ====="
git -C "$WD" --no-pager diff --cached --stat
echo "-----"
git -C "$WD" --no-pager diff --cached
echo "===== END DIFF ====="

# ── 3-b) rollout 로그 audit (escape 탐지). --workdir=사본이므로 사본 밖 쓰기가 escape. ──
AUDIT_RC=0
if [[ -x "$SCRIPT_DIR/audit_codex_log.py" ]]; then
  CODEX_HOME="$CODEX_HOME" python3 "$SCRIPT_DIR/audit_codex_log.py" \
    --session-after "$DELEGATE_START" --workdir "$WD" --delegated >&2 || AUDIT_RC=$?
fi

# ── 4) QA 자동 검증 ──
QA_RC=0
if [[ -x "$SCRIPT_DIR/qa_verify.sh" ]]; then
  ( cd "$WD" && git add -A )
  "$SCRIPT_DIR/qa_verify.sh" "$WD" "$QA_EXPECT" || QA_RC=$?
else
  echo "⚠ qa_verify.sh 없음/실행불가 — QA 검증 스킵" >&2
  QA_RC=1
fi

echo "[work] 작업물(사본): $WD"
[[ "$COPY_MODE" == "worktree" ]] && echo "[apply] 승인 후: 원본=$WT_ORIGIN 에 diff 적용. 정리: git -C \"$WT_ORIGIN\" worktree remove --force \"$WD\""

# ── audit exit code 구분 처리(FN5) ──
REVIEW_FLAG=""
if [[ $AUDIT_RC -eq 2 ]]; then
  echo "[차단] ESCAPE/위험 행위 탐지 → apply 절대 금지(사람 검토, exit 4)"
  cleanup; exit 4
elif [[ $AUDIT_RC -eq 3 ]]; then
  REVIEW_FLAG="⚠ OPAQUE: 로그로 행위판정 불가한 실행 있음 → apply 전 P1 사람검토 필수(자동 apply 금지)"
elif [[ $AUDIT_RC -ne 0 ]]; then
  echo "[차단] 로그 감사 비정상 종료(rc=$AUDIT_RC) → 안전측 차단(exit 4)"
  cleanup; exit 4
fi

# ── ★ P1 사람 승인 게이트 (자동 apply 절대 금지) ──
echo "===== [P1] 사람 승인 필요 ====="
if [[ $QA_RC -eq 0 ]]; then
  echo "[done] QA 게이트 통과. ★ 위 diff 를 사람이 검토·승인해야만 원본에 apply. 이 스크립트는 apply 하지 않음."
  [[ -n "$REVIEW_FLAG" ]] && echo "$REVIEW_FLAG"
else
  echo "[재작업] QA 게이트 미통과(rc=$QA_RC) → 증거 없이 apply 금지"
  [[ -n "$REVIEW_FLAG" ]] && echo "$REVIEW_FLAG"
fi
exit $QA_RC
