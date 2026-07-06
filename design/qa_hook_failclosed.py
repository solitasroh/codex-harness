#!/usr/bin/env python3
"""QA 재현 — 훅 회귀 fail-closed + gap_probe 실제 제외 여부.
백팀장 '훅 8/8 + rm_rf 패턴 제거→RED' 주장을 직접 재현. 원본 불변, 훅+테스트만 임시복제 개악."""
import os, shutil, subprocess, tempfile, sys, re

PLUGIN = "/opt/data/projects/cc-plugin/plugin"
PYBIN = sys.executable

# --- 확인A: test_guard_hook.py가 gap_probe를 '실행'하는가, 아니면 주석 언급뿐인가 ---
src = open(os.path.join(PLUGIN, "tests", "test_guard_hook.py")).read()
# 코드 라인(주석/docstring 제외 근사)에서 gap_probe 실행 흔적 탐색
code_refs = [l for l in src.splitlines()
             if "gap_probe" in l and not l.lstrip().startswith("#")
             and "subprocess" in l or ("gap_probe" in l and "run(" in l)]
print("확인A: test_guard_hook.py의 gap_probe 실행 참조:",
      "없음(주석 언급뿐 = 오탐)" if not code_refs else f"있음! {code_refs}")

# --- 재현B: 훅 fail-closed — rm_rf 방어패턴 제거 시 test_block_rm_rf_root RED ---
def run_broken_hook(mutate):
    wd = tempfile.mkdtemp(prefix="qa_hookfc_", dir="/tmp")
    os.makedirs(os.path.join(wd, "hooks")); os.makedirs(os.path.join(wd, "tests"))
    shutil.copy(os.path.join(PLUGIN, "hooks", "guard_dangerous.sh"), os.path.join(wd, "hooks"))
    shutil.copy(os.path.join(PLUGIN, "tests", "test_guard_hook.py"), os.path.join(wd, "tests"))
    mutate(wd)
    r = subprocess.run([PYBIN, os.path.join(wd, "tests", "test_guard_hook.py")],
                       capture_output=True, text=True, timeout=25)
    shutil.rmtree(wd, ignore_errors=True)
    return r.returncode, r.stdout + r.stderr

def drop_rm_rf(wd):
    p = os.path.join(wd, "hooks", "guard_dangerous.sh")
    txt = open(p).read()
    # rm -rf 방어 패턴 라인 제거
    txt2 = re.sub(r"^\s*'rm\[\[:space:\]\]\+-rf.*$\n", "", txt, flags=re.M)
    assert txt2 != txt, "rm_rf 패턴 라인 매칭 실패"
    open(p, "w").write(txt2)

def drop_curl(wd):
    p = os.path.join(wd, "hooks", "guard_dangerous.sh")
    txt = open(p).read()
    txt2 = re.sub(r"^\s*'curl\[\^\|\]\*.*$\n", "", txt, flags=re.M)
    assert txt2 != txt, "curl 패턴 라인 매칭 실패"
    open(p, "w").write(txt2)

print("\n재현B: 훅 fail-closed (방어패턴 제거 시 RED 나야 정상)")
verdict = []
for name, mut, why in [("drop_rm_rf", drop_rm_rf, "rm -rf 방어 제거"),
                        ("drop_curl", drop_curl, "curl|sh 방어 제거")]:
    rc, log = run_broken_hook(mut)
    caught = rc != 0
    verdict.append(caught)
    fails = [l.strip() for l in log.splitlines() if l.strip().startswith("FAIL")]
    print(f"  [{name}] {why}: exit={rc} → {'✅ RED(포착)' if caught else '❌ 놓침'}", 
          ("| "+fails[0] if fails else ""))

print("\n" + "="*50)
ok = (not code_refs) and all(verdict)
print("✅ 훅 회귀 fail-closed 성립 + gap_probe 실행참조 없음" if ok else "❌ 문제 있음")
sys.exit(0 if ok else 1)
