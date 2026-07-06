#!/usr/bin/env python3
"""QA fail-closed 재현 — 플러그인 위험 스캐너 회귀 테스트가 '진짜 검사하는지' 확인.
백팀장 '10/10 통과'는 봤다. 이제 결함을 심어 테스트가 RED가 되는지 본다.
원본 plugin/ 불변: 임시 복제 후 패턴/스캐너를 개악하고 테스트 실행."""
import os, shutil, subprocess, tempfile, sys

PLUGIN = "/opt/data/projects/cc-plugin/plugin"
PYBIN = sys.executable

def run_broken(name, mutate):
    # 가벼운 복제: 테스트가 참조하는 3파일(test, scanner, patterns)만 복제
    wd = tempfile.mkdtemp(prefix=f"qa_pfc_{name}_", dir="/tmp")
    dst = os.path.join(wd, "plugin")
    for sub in ("tests", "bin", "lib"):
        os.makedirs(os.path.join(dst, sub))
    shutil.copy(os.path.join(PLUGIN, "tests", "test_scan_danger.py"), os.path.join(dst, "tests"))
    shutil.copy(os.path.join(PLUGIN, "bin", "scan_danger.py"), os.path.join(dst, "bin"))
    shutil.copy(os.path.join(PLUGIN, "lib", "danger_patterns.txt"), os.path.join(dst, "lib"))
    mutate(dst)
    r = subprocess.run([PYBIN, os.path.join(dst, "tests", "test_scan_danger.py")],
                       capture_output=True, text=True, timeout=25)
    shutil.rmtree(wd, ignore_errors=True)
    return r.returncode, r.stdout + r.stderr

def mut_drop_remote_exec(dst):
    # D-Q2 방어선 제거: remote_exec 패턴 라인 삭제 → curl|sh 미탐 재발해야 함
    p = os.path.join(dst, "lib", "danger_patterns.txt")
    lines = [l for l in open(p) if not l.startswith("remote_exec")]
    open(p, "w").writelines(lines)

def mut_break_subprocess_to_bare(dst):
    # D-Q1 회귀: subprocess 패턴을 'bare subprocess'로 되돌림 → 정상 import 오탐 재발해야 함
    p = os.path.join(dst, "lib", "danger_patterns.txt")
    txt = open(p).read().replace(
        r"subprocess_call \bsubprocess\.(run|call|Popen|check_output|check_call)\s*\(",
        r"subprocess_call \bsubprocess")
    open(p, "w").write(txt)

def mut_scanner_always_zero(dst):
    # 스캐너가 무조건 exit 0 (아무것도 안 막음) → 모든 위험 테스트가 RED 돼야 함
    p = os.path.join(dst, "bin", "scan_danger.py")
    txt = open(p).read().replace("sys.exit(2)", "sys.exit(0)")
    open(p, "w").write(txt)

print("="*62); print("QA fail-closed 재현 — 결함 주입 시 회귀 테스트가 RED 나야 정상"); print("="*62)
cases = [
    ("drop_remote", mut_drop_remote_exec,  "remote_exec 패턴 삭제(D-Q2 방어선 제거)"),
    ("dq1_regress", mut_break_subprocess_to_bare, "subprocess 패턴을 bare로 되돌림(D-Q1 오탐 재발)"),
    ("scanner_noop", mut_scanner_always_zero, "스캐너 무력화(--strict도 exit0)"),
]
verdict = []
for name, mut, why in cases:
    rc, log = run_broken(name, mut)
    caught = rc != 0   # 테스트가 실패(RED)해야 = 결함을 잡음
    verdict.append(caught)
    fails = [l.strip() for l in log.splitlines() if l.strip().startswith("FAIL")]
    print(f"\n--- 결함[{name}]: {why} ---")
    for f in fails[:4]: print("   ", f)
    print(f"   >>> 테스트 exit={rc} → {'✅ 결함 포착(RED)' if caught else '❌ 결함 놓침(테스트가 무의미)'}")

print("\n" + "="*62)
if all(verdict):
    print("✅ 회귀 테스트 fail-closed 성립: 방어선 제거·스캐너 무력화 전부 RED로 포착")
    sys.exit(0)
else:
    print("❌ 일부 결함을 테스트가 못 잡음 — 회귀 스위트 신뢰불가")
    sys.exit(1)
