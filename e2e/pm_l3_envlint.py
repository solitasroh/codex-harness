#!/usr/bin/env python3
"""PM L3 교차검증 — 코덱스가 만든 envlint를 독립 입력으로 실동작 확인."""
import subprocess, sys, os, json, tempfile

RUN = "/opt/data/projects/cc-plugin/runs/run_enqEF6"
ENVLINT = os.path.join(RUN, "envlint.py")
fails = []

def run(args, stdin=None):
    p = subprocess.run([sys.executable, ENVLINT] + args, input=stdin,
                       capture_output=True, text=True)
    return p.stdout, p.stderr, p.returncode

def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond: fails.append(name)

# 0) 코덱스 자체 테스트 먼저
print("=== 코덱스 test_envlint.py 실행 ===")
p = subprocess.run([sys.executable, "-m", "unittest", "test_envlint", "-v"],
                   cwd=RUN, capture_output=True, text=True)
print((p.stderr or p.stdout).strip()[-600:])
print(f"  unittest exit={p.returncode}")
if p.returncode != 0: fails.append("코덱스 자체 테스트 실패")

# 1) PM 독립 입력 — 깨끗한 .env (stdin)
print("\n=== PM 독립 입력 검증 ===")
out, err, rc = run(["-"], stdin="FOO=bar\nBAZ=qux\n")
check("깨끗한 env → ok/exit0", rc == 0 and "ok" in out.lower())

# 2) 형식 오류 (= 없음)
out, err, rc = run(["-"], stdin="GOOD=1\nBADLINE\n")
check("형식오류(=없음) → exit1", rc == 1)

# 3) 중복 키
out, err, rc = run(["-"], stdin="K=1\nK=2\n")
check("중복키 → exit1", rc == 1)

# 4) 빈 값: 기본 통과, --strict 실패
out0, _, rc0 = run(["-"], stdin="K=\n")
out1, _, rc1 = run(["-", "--strict"], stdin="K=\n")
check("빈값 기본 exit0", rc0 == 0)
check("빈값 --strict exit1", rc1 == 1)

# 5) export 접두 + 따옴표 값
out, err, rc = run(["-"], stdin='export K="a b"\n')
check("export+따옴표 → ok/exit0", rc == 0 and "ok" in out.lower())

# 6) 주석·빈줄 무시
out, err, rc = run(["-"], stdin="# comment\n\nK=1\n")
check("주석/빈줄 무시 → exit0", rc == 0)

# 7) --json 유효성
out, err, rc = run(["-", "--json"], stdin="BADLINE\n")
try:
    d = json.loads(out); check("--json 유효+ok=false", d.get("ok") is False and len(d.get("issues",[]))>=1)
except Exception as e:
    check(f"--json 파싱({e})", False)

# 8) 스키마 필수키 누락
with tempfile.TemporaryDirectory() as td:
    envf = os.path.join(td, ".env"); schf = os.path.join(td, "req.txt")
    open(envf,"w").write("A=1\n"); open(schf,"w").write("A\nB\n")
    out, err, rc = run([envf, "--schema", schf])
    check("스키마 누락(B) → exit1", rc == 1 and "B" in out)

# 9) 파일 없음 → 사용법오류 exit2
out, err, rc = run(["/nonexistent/.env"])
check("파일없음 → exit2", rc == 2)

# 10) 빈 파일 → ok
out, err, rc = run(["-"], stdin="")
check("빈 입력 → ok/exit0", rc == 0)

print("\n" + ("✅ L3 전체 PASS" if not fails else f"❌ 실패 {len(fails)}: {fails}"))
sys.exit(0 if not fails else 1)
