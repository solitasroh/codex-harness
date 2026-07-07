#!/usr/bin/env python3
"""훅 계층 패리티 회귀 — 3계층 판정 일치를 상시 고정 (병합 정본).

배경(QA 브라이언 실측, 검증·가드 딥다이브):
  danger_patterns.txt 단일원본화가 처음엔 python훅+스캐너만 적용돼, claude bash훅
  (guard_dangerous.sh)이 code:계층(os.system/subprocess/eval/--yolo)을 놓쳐 발산했다.
  이 테스트는 동일 명령 세트를 bash훅·python훅 두 실행경로에 넣어 판정이 일치하는지
  검증한다 — 불일치 자체가 실패. 세 계층 중 하나만 고쳐도 발산을 즉시 잡는다.

병합 이력(자비서 명세 2026-07-07): test_hook_parity.py(백팀장) + test_bash_hook_parity.py
  (브라이언)이 같은 목적으로 중복 → 하나로 통합. 브라이언 파일의 이중 assert 진단 메시지
  (py먼저 확인=회귀, bash=패리티)를 흡수. 정상케이스 3종(오탐 패리티)은 백팀장 것 유지.
  + bash훅 fail-closed 케이스 추가(자비서 권고).

위험 문자열은 무해 인자로 조립(실행 아님, 훅 판정만).
pytest 없어도 `python3 test_hook_parity.py`로 직접 실행 가능(폴백 러너 호환).
"""
import json, subprocess, sys, os, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASH_HOOK = os.path.join(HERE, "..", "hooks", "guard_dangerous.sh")
PY_HOOK   = os.path.join(HERE, "..", ".codex", "hooks", "pre_tool_use_guard.py")

def bash_blocks(cmd, extra_env=None):
    """bash 훅에 stdin JSON 주입 → 차단(exit 2)이면 True."""
    payload = json.dumps({"tool_input": {"command": cmd}})
    env = dict(os.environ, **(extra_env or {}))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write(payload); p = f.name
    try:
        with open(p) as fin:
            r = subprocess.run(["bash", BASH_HOOK], stdin=fin, capture_output=True, text=True, env=env)
        return r.returncode == 2
    finally:
        os.unlink(p)

def py_blocks(cmd, extra_env=None):
    """python 훅에 stdin JSON 주입 → permissionDecision=deny이면 True."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    env = dict(os.environ, **(extra_env or {}))
    r = subprocess.run([sys.executable, PY_HOOK], input=payload, capture_output=True, text=True, env=env)
    if not r.stdout.strip():
        return False
    try:
        return json.loads(r.stdout).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    except Exception:
        return False

# ── 두 훅이 동일하게 '차단'해야 하는 code: 계층 위험(실측 발산 지점) ──
# 브라이언 흡수: py를 먼저 단언(못 잡으면 그 자체가 회귀) → bash를 단언(패리티).
_DANGER = [
    ("os_system",  "python3 -c \"import os; os." + "system('id')\""),
    ("subprocess", "python3 -c \"import subprocess; subprocess." + "run(['id'])\""),
    ("eval",       "python3 -c \"" + "eval('1+1')\""),
    ("danger_flag","some-cli --yolo do-thing"),
]
# ── 오탐 방지: 정상 명령은 둘 다 통과(패리티) ──
_SAFE = ["git status && ls -la", "python3 build.py", "pip install pytest"]

def _mk_danger(name, cmd):
    def t():
        pb = py_blocks(cmd)
        assert pb, f"[{name}] python 훅이 위험을 못 잡음 — 그 자체가 회귀 :: {cmd!r}"
        bb = bash_blocks(cmd)
        assert bb, (f"[{name}] PARITY FAIL: python은 deny인데 bash는 allow. "
                    f"guard_dangerous.sh가 danger_patterns.txt code:계층을 안 읽음 :: {cmd!r}")
    return t

def _mk_safe(cmd):
    def t():
        bb, pb = bash_blocks(cmd), py_blocks(cmd)
        assert not bb, f"정상 명령을 bash 훅이 오차단 :: {cmd!r}"
        assert not pb, f"정상 명령을 python 훅이 오차단 :: {cmd!r}"
    return t

_g = globals()
for name, c in _DANGER:
    _g[f"test_parity_danger_{name}"] = _mk_danger(name, c)
for i, c in enumerate(_SAFE):
    _g[f"test_parity_safe_{i}"] = _mk_safe(c)

# ── fail-closed 패리티(자비서 권고): 패턴 원본 0개면 두 훅 다 차단해야 함 ──
def test_parity_failclosed_empty_source():
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("# empty, no patterns\n"); empty = f.name
    try:
        env = {"DANGER_PATTERNS": empty}
        # 정상 명령이라도 원본이 비면 '판단 불가'→둘 다 deny(fail-closed).
        bb = bash_blocks("echo hi", extra_env=env)
        pb = py_blocks("echo hi", extra_env=env)
        assert bb, "bash 훅이 빈 원본에서 fail-open(allow) — exit 2로 차단해야"
        assert pb, "python 훅이 빈 원본에서 fail-open(allow) — deny해야"
    finally:
        os.unlink(empty)

if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    ok = 0; fails = []
    for n, f in fns:
        try:
            f(); ok += 1; print(f"  PASS {n}")
        except AssertionError as e:
            fails.append(n); print(f"  FAIL {n}: {e}")
        except Exception as e:
            fails.append(n); print(f"  ERROR {n}: {e}")
    print(f"{ok}/{len(fns)} 통과")
    sys.exit(1 if fails else 0)
