#!/usr/bin/env bash
# codex-harness 자가진단 (doctor) — Linux/macOS 판. doctor.ps1 의 등가물.
#
# 목적: 설치 직후 1회 실행 → 이 환경에서 하네스 6항목이 실제로 동작하는지 자동 판정.
# 설계 원칙(팀 기준): 각 항목 PASS/FAIL/SKIP + 근거 한 줄. "존재 확인"이 아니라 "실제로 돌려서".
#   3·4·5 는 반드시 실동작(MCP tools/call / xUnit self-test / 훅 fixture). SKIP≠FAIL.
# ★ 3번 함정(baek 실측 2026-07-07): tools/call 응답의 structuredContent.threadId 는 가짜/만료
#   auth 여도 들어온다(isError=True 인데도). threadId 만 보면 phantom 통과. 그래서 id=2 응답을
#   파싱해 isError!=true AND content 에 401/Unauthorized 없음 까지 봐야 진짜 통과.
set -uo pipefail

# ── 결과 집계 ──
PASS_N=0; FAIL_N=0; SKIP_N=0
declare -a LINES
c_green=$'\033[32m'; c_red=$'\033[31m'; c_yellow=$'\033[33m'; c_cyan=$'\033[36m'; c_gray=$'\033[90m'; c_off=$'\033[0m'

add_result() { # $1=번호 $2=제목 $3=PASS|FAIL|SKIP $4=근거
  local n="$1" name="$2" st="$3" reason="$4" col
  case "$st" in
    PASS) col="$c_green"; PASS_N=$((PASS_N+1));;
    FAIL) col="$c_red";   FAIL_N=$((FAIL_N+1));;
    SKIP) col="$c_yellow";SKIP_N=$((SKIP_N+1));;
  esac
  printf '  %s[%s]%s %s. %s — %s\n' "$col" "$st" "$c_off" "$n" "$name" "$reason"
}

have() { command -v "$1" >/dev/null 2>&1; }
PYBIN="$(command -v python3 || command -v python || true)"

# ── 플러그인 루트 확정 (CLAUDE_PLUGIN_ROOT 우선, 없으면 bin/ 상위) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"; else PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"; fi
CODEX_HOME_DIR="$PLUGIN_ROOT/.codex_home"
AUTH_PATH="$CODEX_HOME_DIR/auth.json"

echo ""
echo "${c_cyan}===== codex-harness doctor (Linux/macOS) =====${c_off}"
echo "플러그인 루트: $PLUGIN_ROOT"
echo "CODEX_HOME   : $CODEX_HOME_DIR"
echo ""

# ── 1. codex CLI ──
if have codex; then
  add_result 1 'codex CLI' PASS "PATH 에서 발견: $(codex --version 2>&1 | head -1)"
else
  add_result 1 'codex CLI' FAIL "codex 가 PATH 에 없음 — Codex CLI 설치 후 PATH 등록 필요"
fi

# ── 2. auth.json 존재·읽기 ──
AUTH_OK=0
if [[ -f "$AUTH_PATH" ]]; then
  if [[ -r "$AUTH_PATH" && -s "$AUTH_PATH" ]]; then
    AUTH_OK=1
    add_result 2 'auth.json' PASS "존재·읽기 가능 ($(wc -c <"$AUTH_PATH" | tr -d ' ') bytes): $AUTH_PATH"
  elif [[ ! -s "$AUTH_PATH" ]]; then
    add_result 2 'auth.json' FAIL "파일은 있으나 비어 있음 → bin/codex_bootstrap.sh 재실행"
  else
    add_result 2 'auth.json' FAIL "존재하나 읽기 불가 — 권한 확인"
  fi
else
  add_result 2 'auth.json' FAIL "없음: $AUTH_PATH → 먼저 bin/codex_bootstrap.sh 실행"
fi

# ── 3. MCP tools/call 실동작 (phantom 방지: isError/401 파싱) ──
if ! have codex; then
  add_result 3 'MCP tools/call' SKIP "codex CLI 없어 probe 불가(1번 먼저)"
elif [[ $AUTH_OK -ne 1 ]]; then
  add_result 3 'MCP tools/call' SKIP "auth.json 미비로 probe 불가(2번 먼저)"
elif [[ -z "$PYBIN" ]]; then
  add_result 3 'MCP tools/call' SKIP "python 없어 응답 파싱 불가"
else
  WD="$(mktemp -d "${TMPDIR:-/tmp}/doctor_mcp_XXXXXX")"
  git -C "$WD" init -q 2>/dev/null; git -C "$WD" commit -q --allow-empty -m baseline 2>/dev/null
  # 리눅스 컨테이너는 내장 샌드박스 불가 → danger-full-access. (윈도우는 ps1 이 workspace-write)
  REQ_INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"doctor","version":"1.0"}}}'
  REQ_NOTIF='{"jsonrpc":"2.0","method":"notifications/initialized"}'
  REQ_CALL="{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"codex\",\"arguments\":{\"prompt\":\"Reply with exactly the single word PONG and nothing else.\",\"sandbox\":\"danger-full-access\",\"approval-policy\":\"never\",\"cwd\":\"$WD\",\"config\":{\"skip_git_repo_check\":true}}}}"
  OUT="$(printf '%s\n%s\n%s\n' "$REQ_INIT" "$REQ_NOTIF" "$REQ_CALL" | CODEX_HOME="$CODEX_HOME_DIR" timeout 180 codex mcp-server 2>/dev/null)"
  rm -rf "$WD"
  # id=2 응답 파싱: PASS/FAIL/사유 를 한 줄로 emit
  VERDICT="$(printf '%s' "$OUT" | "$PYBIN" -c '
import sys, json
id2=None
for line in sys.stdin:
    line=line.strip()
    if not line.startswith("{"): continue
    try: m=json.loads(line)
    except Exception: continue
    if m.get("id")==2: id2=m; break
if id2 is None:
    print("FAIL\tid=2 응답 없음 — tools/call 실패(네트워크/인증/타임아웃)"); sys.exit(0)
if "error" in id2:
    print("FAIL\tJSON-RPC error: %s" % str(id2["error"])[:140]); sys.exit(0)
r=id2.get("result",{})
sc=r.get("structuredContent",{}) or {}
tid=sc.get("threadId")
iserr=r.get("isError")
ct=r.get("content") or []
try: text=" ".join(x.get("text","") for x in ct if isinstance(x,dict))
except Exception: text=json.dumps(ct)[:200]
import re
broken=bool(re.search(r"401|Unauthorized|Missing bearer|invalid_?api_?key|expired", text))
if tid and iserr is not True and not broken:
    print("PASS\t실제 tools/call 성공 — threadId=%s, isError=false" % tid)
elif broken:
    print("FAIL\t인증 실패 — threadId 는 왔지만 isError/401(phantom). codex login 후 bin/codex_bootstrap. 응답: %s" % text[:120])
elif iserr is True:
    if "not supported when using Codex with a ChatGPT account" in text:
        print("FAIL\t모델 미지원(gpt-5-codex ChatGPT계정) — config.toml model 라인 제거")
    else:
        print("FAIL\ttools/call isError=True — 위임 실패. 응답: %s" % text[:120])
else:
    print("FAIL\tthreadId 없음 — tools/call 실패")
')"
  ST="${VERDICT%%$'\t'*}"; RS="${VERDICT#*$'\t'}"
  [[ "$ST" == "PASS" ]] && add_result 3 'MCP tools/call' PASS "$RS" || add_result 3 'MCP tools/call' FAIL "$RS"
fi

# ── 4. dotnet + qa_verify.py 가 xUnit 실제로 돌리는지 (임시 self-test) ──
QA_PY="$PLUGIN_ROOT/bin/qa_verify.py"
if ! have dotnet; then
  add_result 4 '.NET 게이트' SKIP "dotnet 이 PATH 에 없음 — .NET 쓸 계획이면 SDK 설치(안 쓰면 무시 가능)"
elif [[ -z "$PYBIN" ]]; then
  add_result 4 '.NET 게이트' FAIL "python 없어 qa_verify.py 실행 불가"
elif [[ ! -f "$QA_PY" ]]; then
  add_result 4 '.NET 게이트' FAIL "qa_verify.py 없음: $QA_PY"
else
  TP="$(mktemp -d "${TMPDIR:-/tmp}/doctor_xunit_XXXXXX")"
  ( cd "$TP" && dotnet new xunit -n DoctorSelfTest >/dev/null 2>&1 )
  if [[ -d "$TP/DoctorSelfTest" ]]; then
    "$PYBIN" "$QA_PY" "$TP/DoctorSelfTest" >/dev/null 2>&1; RC=$?
    if [[ $RC -eq 0 ]]; then
      add_result 4 '.NET 게이트' PASS "dotnet $(dotnet --version 2>/dev/null) + qa_verify.py 가 임시 xUnit 을 실제로 빌드·테스트해 exit 0"
    else
      add_result 4 '.NET 게이트' FAIL "qa_verify.py 가 정상 xUnit 에 exit $RC — 러너감지/dotnet test 경로 점검"
    fi
  else
    add_result 4 '.NET 게이트' FAIL "dotnet new xunit 실패 — SDK 는 있으나 템플릿/복원 문제"
  fi
  rm -rf "$TP"
fi

# ── 5. 가드훅 패턴 자가탐색 (안전 통과 / 위험 차단, env 제거) ──
HOOK_PATH="$CODEX_HOME_DIR/hooks/pre_tool_use_guard.py"
if [[ -z "$PYBIN" ]]; then
  add_result 5 '가드훅 자가탐색' FAIL "python 없어 훅 실행 불가"
elif [[ ! -f "$HOOK_PATH" ]]; then
  add_result 5 '가드훅 자가탐색' FAIL "훅 미설치: $HOOK_PATH → bin/codex_bootstrap.sh 재실행(리눅스는 codex_run.sh 도 심음)"
else
  SAFE_OUT="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"echo hello safe"}}' | env -u DANGER_PATTERNS -u CLAUDE_PLUGIN_ROOT "$PYBIN" "$HOOK_PATH" 2>/dev/null)"
  DANGER_OUT="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | env -u DANGER_PATTERNS -u CLAUDE_PLUGIN_ROOT "$PYBIN" "$HOOK_PATH" 2>/dev/null)"
  SAFE_ALLOW=0; [[ -z "${SAFE_OUT// }" ]] && SAFE_ALLOW=1
  DANGER_DENY=0; [[ "$DANGER_OUT" == *'"permissionDecision": "deny"'* || "$DANGER_OUT" == *'"permissionDecision":"deny"'* ]] && DANGER_DENY=1
  if [[ $SAFE_ALLOW -eq 1 && $DANGER_DENY -eq 1 ]]; then
    add_result 5 '가드훅 자가탐색' PASS "env 없이 안전명령 통과 / 위험명령(rm -rf /) 차단 — 패턴 자가탐색 정상"
  elif [[ $SAFE_ALLOW -eq 0 && $DANGER_DENY -eq 1 ]]; then
    add_result 5 '가드훅 자가탐색' FAIL "안전명령까지 차단됨 — 패턴 자가탐색 실패(fail-closed 전면차단 지뢰). 패턴이 훅 옆에 복사됐는지 확인"
  elif [[ $SAFE_ALLOW -eq 1 && $DANGER_DENY -eq 0 ]]; then
    add_result 5 '가드훅 자가탐색' FAIL "위험명령이 차단 안 됨(fail-open) — 심각. 훅/패턴 무결성 확인"
  else
    add_result 5 '가드훅 자가탐색' FAIL "안전 통과·위험 차단 모두 실패 — 훅 동작 이상"
  fi
fi

# ── 6. CODEX_HOME 갈림길 리포트 (읽기 전용, 사람 판단) ──
add_result 6 'CODEX_HOME 리포트' SKIP "리포트 전용(사람 판단). 아래 상세 참조"
USER_CODEX="${HOME:-}/.codex/auth.json"
[[ -f "$USER_CODEX" ]] && u="있음" || u="없음"
[[ -f "$AUTH_PATH" ]] && p="있음(bootstrap 완료)" || p="없음(bootstrap 필요)"
printf '       %s· 기본 홈 ~/.codex/auth.json: %s%s\n' "$c_gray" "$u" "$c_off"
printf '       %s· 플러그인 CODEX_HOME/auth.json: %s%s\n' "$c_gray" "$p" "$c_off"
if have codex; then
  st="$(CODEX_HOME="$CODEX_HOME_DIR" codex login status 2>&1 | head -1)"
  printf '       %s· codex login status (CODEX_HOME=플러그인): %s%s\n' "$c_gray" "$st" "$c_off"
fi

# ── 요약 + 종료코드 ──
TOTAL=$((PASS_N+FAIL_N+SKIP_N))
echo ""
echo "${c_cyan}===== 요약 =====${c_off}"
if [[ $FAIL_N -gt 0 ]]; then
  echo "${c_red}PASS $PASS_N / FAIL $FAIL_N / SKIP $SKIP_N  (총 $TOTAL 항목)${c_off}"
  echo "${c_yellow}→ FAIL 항목을 근거대로 해결 후 재실행. (SKIP 은 실기 조건 불충족 — FAIL 아님)${c_off}"
  exit 1
else
  echo "${c_green}PASS $PASS_N / FAIL $FAIL_N / SKIP $SKIP_N  (총 $TOTAL 항목)${c_off}"
  [[ $SKIP_N -gt 0 ]] && echo "${c_yellow}→ FAIL 없음. SKIP 은 해당 기능 안 쓰면 무시 가능(예: .NET 미사용 시 dotnet SKIP).${c_off}" \
                      || echo "${c_green}→ 전 항목 통과. 하네스가 이 환경에서 실동작함이 확인됐습니다.${c_off}"
  exit 0
fi
