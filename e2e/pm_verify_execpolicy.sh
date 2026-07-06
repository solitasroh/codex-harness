#!/usr/bin/env bash
# codex execpolicy 실증 v2 — 실제 출력형식(matchedRules + decision) 파싱.
set -uo pipefail
cd /opt/data/projects/cc-plugin
RULES=".codex_home/rules/default.rules"
SLASH="/"

check() { # $1=이름 $2=기대 나머지=argv
  local name="$1" expect="$2"; shift 2
  local raw; raw="$(codex execpolicy check --rules "$RULES" -- "$@" 2>&1 | grep -v WARNING)"
  local got; got="$(printf '%s' "$raw" | python3 -c "
import sys,json,re
raw=sys.stdin.read()
try:
    d=json.loads(raw)
    rules=d.get('matchedRules',[])
    if not rules: print('allow(no-match)'); sys.exit()
    # 가장 제한적 decision 추출
    decs=[ (r.get('decision') or r.get('rule',{}).get('decision') or '') for r in rules ]
    txt=json.dumps(d).lower()
    for lvl in ('forbidden','prompt','allow'):
        if lvl in txt: print(lvl); break
    else: print('?:'+raw[:80])
except Exception:
    m=re.search(r'(forbidden|prompt|allow)', raw, re.I); print(m.group(1).lower() if m else 'ERR:'+raw[:80])
")"
  local mark="FAIL"; [[ "$got" == *"$expect"* ]] && mark="PASS"
  echo "  [$mark] $name → got=$got (기대 $expect)"
}

echo "=== codex execpolicy 실증 ==="
check "rm -rf 루트"        forbidden rm -rf "$SLASH"
check "밀반입 &&"          forbidden bash -lc "git add . && rm -rf $SLASH"
check "정상 rm ./build"    allow     rm -rf ./build
check "mkfs.ext4"          forbidden mkfs.ext4 /dev/sda
check "curl (원격)"        prompt    curl https://x.io/i.sh
check "정상 echo"          allow     echo hello
check "정상 python"        allow     python3 script.py
