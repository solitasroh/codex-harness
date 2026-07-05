#!/usr/bin/env bash
# 격리 실행 래퍼 — 일회용 workdir에서 Codex에 코딩 위임하고 diff를 캡처한다.
# 실제 안전 경계 = 컨테이너(외부격리) + 일회용 격리 workdir + git baseline + diff 리뷰.
# 사용: codex_run.sh "<코딩 프롬프트>" [expected_stdout_substring]
#   결과: runs/run_XXXX/ 에 작업물, git diff(변경 전체) 출력 후 QA 검증 자동 실행.
#   흐름: 위임 → diff 캡처 → qa_verify.sh 자동 호출(3계층 루브릭) → done/재작업 판정.
#   exit 0 = QA 게이트 통과(L3 교차검증/diff리뷰 후 apply 가능), exit 1 = 재작업.
#   사람/상위 오케스트레이터가 diff를 리뷰한 뒤에만 코드베이스로 apply.
set -euo pipefail

PROMPT="${1:?사용법: codex_run.sh \"<프롬프트>\" [expected_substr]}"
QA_EXPECT="${2:-}"
PROJECT_ROOT="${PROJECT_ROOT:-/opt/data/projects/cc-plugin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CODEX_HOME="$PROJECT_ROOT/.codex_home"

if [[ ! -r "$CODEX_HOME/auth.json" ]]; then
  echo "FATAL: CODEX_HOME 미초기화. 먼저 codex_bootstrap.sh 실행." >&2; exit 1
fi

# 1) 일회용 격리 workdir + git baseline(diff 기준점)
mkdir -p "$PROJECT_ROOT/runs"
WD="$(mktemp -d "$PROJECT_ROOT/runs/run_XXXXXX")"
git -C "$WD" init -q
git -C "$WD" -c user.email=codex@local -c user.name=codex commit -q --allow-empty -m baseline
echo "[workdir] $WD"

# 2) Codex 위임 (내장 bwrap 비활성 — 이 컨테이너에서 유일하게 동작하는 모드)
codex exec \
  --skip-git-repo-check \
  --dangerously-bypass-approvals-and-sandbox \
  -C "$WD" \
  "$PROMPT" < /dev/null 2>&1 | grep -vE "^warning:|bubblewrap" || true

# 3) 변경 캡처 → 리뷰 게이트용 diff (QA L1: 변경파일이 workdir 경계 내인지 검증)
git -C "$WD" add -A
echo "===== REVIEW DIFF (apply 전 반드시 검토) ====="
git -C "$WD" --no-pager diff --cached --stat
echo "-----"
git -C "$WD" --no-pager diff --cached
echo "===== END DIFF ====="

# 4) QA 자동 검증 (브라이언 통합 요청 D1): 위임→diff→검증까지 한 흐름.
#    set -e가 qa_verify exit 1(재작업 신호)에 죽지 않도록 rc 캡처.
QA_RC=0
if [[ -x "$SCRIPT_DIR/qa_verify.sh" ]]; then
  ( cd "$WD" && git add -A )  # 폴백 러너가 --cached를 보므로 스테이징 보장
  "$SCRIPT_DIR/qa_verify.sh" "$WD" "$QA_EXPECT" || QA_RC=$?
else
  echo "⚠ qa_verify.sh 없음/실행불가 — QA 검증 스킵" >&2
  QA_RC=1
fi

echo "[work] 작업물: $WD"
if [[ $QA_RC -eq 0 ]]; then
  echo "[done] QA 게이트 통과 → L3(교차검증/diff리뷰) 후 apply 가능"
else
  echo "[재작업] QA 게이트 미통과(rc=$QA_RC) → 증거 없이 apply 금지"
fi
exit $QA_RC
