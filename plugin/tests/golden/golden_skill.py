#!/usr/bin/env python3
"""스킬 골든셋 회귀 하네스 (일반화) — 브라이언 QA §L3 권고 구현.

스킬은 프롬프트(확률적)라 코드처럼 "결함주입→RED"가 안 된다. 골든 시나리오를 고정해두고
스킬 수정 시마다 재실행해 게이트가 무너지지 않았는지 표본 확인한다.

golden_adr.py를 일반화: 스킬별 마커/기대값/프롬프트를 fixture(suite JSON)에 담아 한 하네스로
여러 스킬(adr-check, design-grill, ...)을 돌린다. 단일 소스 — PM 옵션(a).

사용:
  golden_skill.py                      # tests/golden/*.golden.json 전부 실행
  golden_skill.py adr_golden.json      # 특정 suite만
  golden_skill.py --list               # suite 목록

suite JSON 스키마:
{
  "suite": "adr-check",
  "marker": "VERDICT",                 # 응답에서 파싱할 마커 이름
  "verdicts": ["CONFLICT", "OK"],      # 허용 판정값(정규식 대안)
  "prompt": "Use the {skill} skill. Read {files}. {task}\\nReply with a final line 'MARKER: ...'",
  "cases": [
    {"id","kind","expect","files":[{"path","body"}], "task":"...", "match":"CONFLICT"}
  ]
}
- files: 각 케이스가 임시 workdir에 기록할 파일들(상대경로).
- expect: 이 케이스의 기대 판정값(marker 뒤 토큰과 대조). kind=core & 충돌계열 미탐 = 치명.

운영 메모: HOME=/opt/data 필수(claude credentials), --permission-mode bypassPermissions 필수(파일접근).
없으면 인증실패/타임아웃(exit 124)로 오진.
"""
import json, os, subprocess, sys, tempfile, re, glob

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.abspath(os.path.join(HERE, "..", ".."))
CLAUDE_HOME = os.environ.get("CLAUDE_HOME_OVERRIDE", "/opt/data")
TIMEOUT = int(os.environ.get("GOLDEN_TIMEOUT", "150"))

def run_case(suite, c):
    wd = tempfile.mkdtemp(prefix="golden_")
    written = []
    for f in c.get("files", []):
        p = os.path.join(wd, f["path"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f["body"])
        written.append(p)
    files_str = ", ".join(written) if written else "(no files)"
    marker = suite["marker"]
    prompt = suite["prompt"].format(
        skill=suite["suite"], files=files_str, task=c.get("task", ""), marker=marker,
    )
    env = dict(os.environ, HOME=CLAUDE_HOME)
    try:
        r = subprocess.run(
            ["claude", "--plugin-dir", PLUGIN,
             "--permission-mode", "bypassPermissions", "-p", prompt],
            env=env, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    verds = "|".join(re.escape(v) for v in suite["verdicts"])
    m = re.search(rf"{re.escape(marker)}:\s*({verds})", out, re.I)
    got = m.group(1).upper() if m else None
    return got, out.strip()[-300:]

def run_suite(path):
    suite = json.load(open(path, encoding="utf-8"))
    cases = suite["cases"]
    fails, criticals = 0, 0
    print(f"=== [{suite['suite']}] 골든셋 회귀 ({len(cases)} 케이스, marker={suite['marker']}) ===")
    for c in cases:
        got, tail = run_case(suite, c)
        exp = c["expect"].upper()
        ok = (got == exp)
        crit = (not ok and c.get("kind") == "core")
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark} {c['id']} (expect={exp} got={got})" + (" [CRITICAL]" if crit else ""))
        if not ok:
            fails += 1
            criticals += 1 if crit else 0
            print(f"     tail: {tail!r}")
    print(f"  → {len(cases)-fails}/{len(cases)} 통과, 치명 {criticals}건")
    return fails, criticals

def main():
    args = sys.argv[1:]
    suites = sorted(glob.glob(os.path.join(HERE, "*.golden.json")))
    if args and args[0] == "--list":
        for s in suites:
            print(os.path.basename(s))
        return
    if args:
        suites = [os.path.join(HERE, a) if not os.path.isabs(a) else a for a in args]
    total_fail = total_crit = 0
    for s in suites:
        f, cr = run_suite(s)
        total_fail += f; total_crit += cr
    print(f"=== 전체: 실패 {total_fail}건, 치명 {total_crit}건 ===")
    sys.exit(1 if total_fail else 0)

if __name__ == "__main__":
    main()
