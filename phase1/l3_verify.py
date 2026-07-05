#!/usr/bin/env python3
"""L3 독립 교차검증 — PM(Claude)이 Codex 산출물을 검증. Codex가 만든 테스트가 아닌 독립 입력 사용."""
import json, subprocess, sys, os

WD = "/opt/data/projects/cc-plugin/runs/run_Oz3JuL"
DIFF = "/opt/data/projects/cc-plugin/phase1/l3_test.diff"
os.chdir(WD)
fails = []

def run(args):
    p = subprocess.run([sys.executable, "diff_digest.py", DIFF] + args,
                       capture_output=True, text=True)
    return p.stdout, p.returncode

# L3-a: 텍스트 출력 + 파일별 통계
out, rc = run([])
print("=== L3-a 텍스트 ===")
print(out)
print("exit:", rc)

# L3-b: --strict → 위험 있으니 exit 2
_, rc_strict = run(["--strict"])
ok = rc_strict == 2
print(f"\n=== L3-b --strict exit={rc_strict} (기대 2) {'PASS' if ok else 'FAIL'}")
if not ok: fails.append("strict exit != 2")

# L3-c: --json 유효성 + 핵심 로직(추가eval 잡고 삭제eval 안잡음)
out_json, _ = run(["--json"])
d = json.loads(out_json)  # 유효 JSON 아니면 여기서 예외
snippets = [r["snippet"] for r in d["risks"]]
patterns_hit = {r["pattern"] for r in d["risks"]}

checks = {
    "json has files/risks": ("files" in d and "risks" in d),
    "removed-eval NOT leaked": not any("this_is_removed" in s for s in snippets),
    "added-eval caught": any("user_input" in s for s in snippets),
    "rm-rf caught": any("rm -rf" in s for s in snippets),
    "os.system caught": any("os.system" in s or "os\\.system" in p for s,p in [(s,p) for s in snippets for p in patterns_hit]) or any("os.system" in s for s in snippets),
    "SECRET caught": any("SECRET" in s for s in snippets),
    # 파일별 통계: safe.py +2/-1, danger.py +3/-1
    "safe.py stats": any(f["path"]=="safe.py" and f["added"]==2 and f["removed"]==1 for f in d["files"]),
    "danger.py stats": any(f["path"]=="danger.py" and f["added"]==3 and f["removed"]==1 for f in d["files"]),
}
print("\n=== L3-c 로직 검증 ===")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if not v: fails.append(k)

print("\n=== files 실제값 ===")
for f in d["files"]: print(" ", f)
print("=== risk patterns hit ===", patterns_hit)

print("\n" + ("✅ L3 전체 PASS" if not fails else f"❌ L3 실패: {fails}"))
sys.exit(0 if not fails else 1)
