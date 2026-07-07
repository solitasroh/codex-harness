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

# 1) 위임 전 프롬프트 사전 스캔 (가드 1선: 위험 지시가 담긴 요청 자체를 거부)
if [[ -x "$SCRIPT_DIR/scan_danger.py" ]]; then
  if ! printf '%s\n' "$PROMPT" | python3 "$SCRIPT_DIR/scan_danger.py" --strict >/dev/null 2>&1; then
    echo "🔴 위임 거부: 프롬프트에 위험 지시 포함 (scan_danger --strict)" >&2
    printf '%s\n' "$PROMPT" | python3 "$SCRIPT_DIR/scan_danger.py" --strict >&2 || true
    exit 3
  fi
fi

# 1-b) ★ codex 네이티브 PreToolUse 훅 설치 (수장 아이디어 2026-07-05: claude 가드를 codex에 이식)
#     실증: codex는 셸/apply_patch 실행 '직전' 이 훅을 호출한다. 위험 패턴이면 deny로 실행 전 차단.
#     사후 로그 감사(두더지잡기)와 달리 "실행 전 차단" — codex_run이 매 실행마다 CODEX_HOME에 동기화.
#     한계(문서): PreToolUse는 완전 강제경계가 아닌 가드레일(단순 셸만 가로챔). 근본 차단은 컨테이너 격리.
HOOK_SRC="$SCRIPT_DIR/../.codex/hooks/pre_tool_use_guard.py"
if [[ -f "$HOOK_SRC" ]]; then
  mkdir -p "$CODEX_HOME/hooks"
  cp -f "$HOOK_SRC" "$CODEX_HOME/hooks/pre_tool_use_guard.py"
  # ★ 패턴 파일도 훅과 같은 폴더에 동반 복사(백팀장 2026-07-07): 훅의 _resolve_pat()이
  #   HERE/danger_patterns.txt 를 1순위로 찾으므로, DANGER_PATTERNS env·절대경로에 의존하지
  #   않고 OS 무관하게 패턴을 로드한다. (윈도우 fail-closed 전면차단 지뢰의 근본 차단.)
  cp -f "$SCRIPT_DIR/../lib/danger_patterns.txt" "$CODEX_HOME/hooks/danger_patterns.txt"
  # 패턴 파일 절대경로도 계속 전달(중복 안전망: env override 최우선).
  export DANGER_PATTERNS="$SCRIPT_DIR/../lib/danger_patterns.txt"
  # 훅 실행 명령: PATH 의 python3 를 쓰되(하드코딩 /usr/bin 제거), 패턴은 훅 옆 사본으로 자가탐색.
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

# 2) 일회용 격리 workdir + git baseline(diff 기준점)
#    ⚠ 실측(2026-07-05): -C $WD 는 diff 캡처 범위일 뿐 파일시스템 경계가 아니다.
#    codex는 절대경로로 workdir 밖도 쓸 수 있다(exec·MCP 동일). 아래 3-b가 사후 탐지.
mkdir -p "$PROJECT_ROOT/runs"
WD="$(mktemp -d "$PROJECT_ROOT/runs/run_XXXXXX")"
git -C "$WD" init -q
git -C "$WD" -c user.email=codex@local -c user.name=codex commit -q --allow-empty -m baseline
echo "[workdir] $WD"

# 3) Codex 위임 (내장 bwrap 비활성 — 이 컨테이너에서 유일하게 동작하는 모드)
#    위임 시작 시각 기록 → 이후 생성된 rollout 로그만 감사(다른 세션 로그 제외).
DELEGATE_START=$(date +%s)
codex exec \
  --skip-git-repo-check \
  --dangerously-bypass-approvals-and-sandbox \
  --dangerously-bypass-hook-trust \
  -C "$WD" \
  "$PROMPT" < /dev/null 2>&1 | grep -vE "^warning:|bubblewrap" || true

# 3) 변경 캡처 → 리뷰 게이트용 diff (QA L1: 변경파일이 workdir 경계 내인지 검증)
git -C "$WD" add -A
echo "===== REVIEW DIFF (apply 전 반드시 검토) ====="
git -C "$WD" --no-pager diff --cached --stat
echo "-----"
git -C "$WD" --no-pager diff --cached
echo "===== END DIFF ====="

# 3-b) 실행 중 행위 감사 (브라이언 (b)): rollout 로그의 exec_command를 위험/escape 패턴 대조.
#      diff는 "무엇이 남았나", 로그는 "무엇을 했나". -C는 경계가 아니므로(실측) 이게 사후 포착 수단.
#      audit exit 계약(FN5 수정): 0=이상없음 / 2=escape·위험 → 하드차단 / 3=opaque → 리뷰플래그(차단 아님).
AUDIT_RC=0
if [[ -x "$SCRIPT_DIR/audit_codex_log.py" ]]; then
  CODEX_HOME="$CODEX_HOME" python3 "$SCRIPT_DIR/audit_codex_log.py" \
    --session-after "$DELEGATE_START" --workdir "$WD" --delegated >&2 || AUDIT_RC=$?
fi

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
# audit exit code 구분 처리(FN5): opaque(3)와 escape(2)를 !=0 하나로 뭉개지 않는다.
REVIEW_FLAG=""
if [[ $AUDIT_RC -eq 2 ]]; then
  # escape·위험 행위 = 하드차단(사후검사 모델 구멍 방어). QA 통과 여부 무관.
  echo "[차단] ESCAPE/위험 행위 탐지 → apply 절대 금지(사람 검토, exit 4)"
  exit 4
elif [[ $AUDIT_RC -eq 3 ]]; then
  # opaque = "자동 GREEN 금지"이지 "run 실패"가 아님. 진행하되 P1 리뷰 대기 표시.
  REVIEW_FLAG="⚠ OPAQUE: 로그로 행위판정 불가한 실행 있음 → apply 전 P1 사람검토 필수(자동 apply 금지)"
elif [[ $AUDIT_RC -ne 0 ]]; then
  # 알 수 없는 audit 실패는 안전측 차단.
  echo "[차단] 로그 감사 비정상 종료(rc=$AUDIT_RC) → 안전측 차단(exit 4)"
  exit 4
fi

if [[ $QA_RC -eq 0 ]]; then
  echo "[done] QA 게이트 통과 → L3(교차검증/diff리뷰) 후 apply 가능"
  [[ -n "$REVIEW_FLAG" ]] && echo "$REVIEW_FLAG"
else
  echo "[재작업] QA 게이트 미통과(rc=$QA_RC) → 증거 없이 apply 금지"
  [[ -n "$REVIEW_FLAG" ]] && echo "$REVIEW_FLAG"
fi
exit $QA_RC
