#!/usr/bin/env python3
"""QA fail-closed 재현 — 브라이언. diff_digest에 의도적 결함을 심어 QA 게이트가 '실패를 실패로' 잡는지 확인.
'통과만 보는 건 반쪽 검증' — 결함 주입 후 테스트가 RED가 되는지 실증한다.
원본 diff_digest.py는 건드리지 않는다: 임시 workdir에 복사→개악→qa_verify 실행."""
import os, shutil, subprocess, tempfile, sys

SRC = "/opt/data/projects/cc-plugin/runs/run_Oz3JuL"
QA_VERIFY = "/opt/data/projects/cc-plugin/scripts/qa_verify.sh"
PYBIN = sys.executable

def make_broken(mutation_name, mutate_fn):
    wd = tempfile.mkdtemp(prefix=f"qa_fc_{mutation_name}_", dir="/opt/data/projects/cc-plugin/runs")
    for fn in ("diff_digest.py", "test_diff_digest.py"):
        shutil.copy(os.path.join(SRC, fn), os.path.join(wd, fn))
    # 결함 주입
    p = os.path.join(wd, "diff_digest.py")
    with open(p) as f: code = f.read()
    code2 = mutate_fn(code)
    assert code2 != code, f"{mutation_name}: 결함 주입 실패(패턴 불일치)"
    with open(p, "w") as f: f.write(code2)
    # git init(qa_verify 폴백러너가 --cached 참조)
    subprocess.run(["git","init","-q"], cwd=wd)
    subprocess.run(["git","add","-A"], cwd=wd)
    subprocess.run(["git","-c","user.email=q@l","-c","user.name=q","commit","-q","-m","broken"], cwd=wd)
    # QA 게이트 실행 (폴백 러너 = 시스템 python3)
    r = subprocess.run(["bash", QA_VERIFY, wd], capture_output=True, text=True, timeout=40)
    shutil.rmtree(wd, ignore_errors=True)
    return r.returncode, r.stdout + r.stderr

# 결함 1: scan_risks가 삭제(-)라인도 잡도록 개악 (PM이 예시로 든 바로 그 결함)
def mut_removed_leak(code):
    return code.replace(
        '        if line.startswith("+") and not line.startswith("+++ "):\n            snippet = line[1:]',
        '        if (line.startswith("+") and not line.startswith("+++ ")) or line.startswith("-"):\n            snippet = line[1:]')

# 결함 2: parse_diff 통계 오산 — added 를 2배로
def mut_stat_wrong(code):
    return code.replace('            current["added"] += 1', '            current["added"] += 2')

print("="*60); print("QA fail-closed 재현 — 결함 주입 → 게이트가 RED 내야 정상"); print("="*60)
verdict = []
for name, mut, why in [
    ("removed_leak", mut_removed_leak, "scan_risks가 삭제라인도 포착(AC2b 위반)"),
    ("stat_x2",      mut_stat_wrong,   "parse_diff added 통계 2배 오산(AC1 위반)"),
]:
    rc, log = make_broken(name, mut)
    caught = rc != 0
    verdict.append(caught)
    print(f"\n--- 결함[{name}]: {why} ---")
    # 로그에서 판정/실패라인만 발췌
    for ln in log.splitlines():
        if any(k in ln for k in ("PASS","FAIL","❌","✅","판정","assert","Error","test_")):
            print("   ", ln.strip())
    print(f"   >>> qa_verify exit={rc} → {'✅ 결함 포착(RED)' if caught else '❌ 결함 놓침(게이트 무력)'}")

print("\n" + "="*60)
if all(verdict):
    print("✅ fail-closed 성립: 주입한 결함 전부 게이트가 RED로 포착")
    sys.exit(0)
else:
    print("❌ fail-closed 결함: 일부 결함을 게이트가 놓침 — 게이트 신뢰불가")
    sys.exit(1)
