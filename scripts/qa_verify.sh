#!/usr/bin/env bash
# QA 검증기 — codex_run.sh가 만든 격리 workdir에 3계층 루브릭을 자동 적용한다.
# 작성: 브라이언(QA). codex_run.sh는 "위임+diff캡처"까지, 이 스크립트가 "검증(done 판정)"을 담당.
# 사용: qa_verify.sh <workdir> [expected_stdout_substring]
#   exit 0 = done(전 게이트 통과), exit 1 = 재작업(하나라도 미통과)
# 원칙: 자기보고≠검증. 테스트 파일 존재≠통과. 러너 없으면 함수 직접호출로 폴백해서라도 "실제로 돌린다".
set -uo pipefail

WD="${1:?사용법: qa_verify.sh <workdir> [expected_substr]}"
EXPECT="${2:-}"
cd "$WD" || { echo "FATAL: workdir 없음: $WD" >&2; exit 1; }
FAIL=0
echo "===== QA VERIFY: $WD ====="

# ---- L1 Mechanical: 변경파일이 workdir 경계 내인가 + 문법 ----
echo "[L1] 경계·문법"
OUTSIDE=$(git diff --cached --name-only 2>/dev/null | grep -E '^(/|\.\./)' || true)
if [[ -n "$OUTSIDE" ]]; then echo "  ❌ workdir 밖 변경: $OUTSIDE"; FAIL=1; else echo "  ✅ 변경파일 전부 workdir 경계 내"; fi
for f in $(find . -name '*.py' -not -path './.git/*'); do
  if ! python3 -m py_compile "$f" 2>/dev/null; then echo "  ❌ 문법오류: $f"; FAIL=1; fi
done
[[ $FAIL -eq 0 ]] && echo "  ✅ py 문법 OK"

# ---- L2 Behavioral: 테스트를 실제로 실행 (러너 자동감지 폴백) ----
echo "[L2] 테스트 실행"
TESTS=$(find . -name 'test_*.py' -o -name '*_test.py' 2>/dev/null | grep -v './.git/' || true)
if [[ -z "$TESTS" ]]; then
  echo "  ⚠ 테스트 파일 없음 — L2 미검증(코딩 태스크면 테스트 요구 대상)"
elif python3 -m pytest --version >/dev/null 2>&1; then
  python3 -m pytest -q 2>&1 | tail -5; [[ ${PIPESTATUS[0]} -ne 0 ]] && FAIL=1
  echo "  (runner=pytest)"
else
  # 폴백: pytest 부재 → test_*.py의 test_ 함수를 직접 import·호출
  echo "  (runner=direct: pytest 부재 → 함수 직접호출 폴백)"
  for t in $TESTS; do
    mod=$(basename "$t" .py)
    python3 -c "
import importlib,sys,traceback
m=importlib.import_module('$mod')
fns=[f for f in dir(m) if f.startswith('test_')]
ok=0
for f in fns:
    try: getattr(m,f)(); print('  ✅',f); ok+=1
    except Exception: print('  ❌',f); traceback.print_exc(); sys.exit(1)
print(f'  {ok}/{len(fns)} 통과')
" 2>&1 || FAIL=1
  done
fi

# ---- L2b: expected stdout (지정 시) ----
if [[ -n "$EXPECT" ]]; then
  MAIN=$(find . -maxdepth 1 -name '*.py' -not -name 'test_*' | head -1)
  if [[ -n "$MAIN" ]]; then
    GOT=$(python3 "$MAIN" 2>&1)
    if [[ "$GOT" == *"$EXPECT"* ]]; then echo "  ✅ stdout에 기대문자열 포함: '$EXPECT'"; else echo "  ❌ stdout 불일치: got='$GOT' expect~='$EXPECT'"; FAIL=1; fi
  fi
fi

# ---- 판정 (L3 교차검증은 다른 벤더 리뷰 + diff 리뷰로 별도 수행) ----
echo "===== 판정 ====="
if [[ $FAIL -eq 0 ]]; then echo "✅ L1·L2 PASS → L3(교차검증/diff리뷰) 후 done 가능"; exit 0
else echo "❌ 미통과 → 재작업. 증거 없이 done 금지."; exit 1; fi
