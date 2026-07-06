#!/usr/bin/env python3
"""adr-check 골든셋 회귀 하네스 — 브라이언 QA §L3 권고 구현.

스킬은 프롬프트(확률적)라 코드처럼 "결함주입→RED"가 안 된다. 대신 골든 시나리오를
고정해두고 스킬 수정 시마다 재실행해 게이트가 무너지지 않았는지 표본 확인한다.

동작: tests/golden/adr_golden.json 의 각 케이스마다
  1) 임시 workdir에 docs/adr/<file> + CONTEXT.md 기록
  2) HOME=/opt/data claude --plugin-dir <plugin> --permission-mode bypassPermissions 로
     adr-check 스킬을 태워 new_decision이 충돌하는지 판정 요청
  3) 응답에서 VERDICT(CONFLICT|OK) 파싱 → expect와 대조
판정: core 케이스 미탐 = 치명. 전 케이스 일치해야 exit 0.

주의(운영 메모): HOME=/opt/data 필수(credentials 위치), bypassPermissions 필수(파일접근).
없으면 인증실패/타임아웃(exit 124)로 오진.
"""
import json, os, subprocess, sys, tempfile, re

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.abspath(os.path.join(HERE, "..", ".."))
GOLDEN = os.path.join(HERE, "adr_golden.json")
CLAUDE_HOME = os.environ.get("CLAUDE_HOME_OVERRIDE", "/opt/data")
TIMEOUT = int(os.environ.get("GOLDEN_TIMEOUT", "150"))

PROMPT_TMPL = (
    "Use the adr-check skill. Read {adr_path} and {ctx_path}. "
    "New decision: {decision}\n"
    "Does this new decision conflict with any approved ADR or violate CONTEXT.md? "
    "Reply with a final line exactly in the form 'VERDICT: CONFLICT <adr-number>' "
    "or 'VERDICT: OK' and nothing after it."
)

def run_case(c):
    wd = tempfile.mkdtemp(prefix="adr_golden_")
    adr_dir = os.path.join(wd, "docs", "adr")
    os.makedirs(adr_dir, exist_ok=True)
    adr_path = os.path.join(adr_dir, c["adr_file"])
    ctx_path = os.path.join(wd, "CONTEXT.md")
    with open(adr_path, "w", encoding="utf-8") as f:
        f.write(c["adr_body"])
    with open(ctx_path, "w", encoding="utf-8") as f:
        f.write(c["context_body"])

    prompt = PROMPT_TMPL.format(adr_path=adr_path, ctx_path=ctx_path, decision=c["new_decision"])
    env = dict(os.environ, HOME=CLAUDE_HOME)
    try:
        r = subprocess.run(
            ["claude", "--plugin-dir", PLUGIN,
             "--permission-mode", "bypassPermissions", "-p", prompt],
            env=env, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    out = r.stdout + "\n" + r.stderr
    m = re.search(r"VERDICT:\s*(CONFLICT|OK)", out, re.I)
    verdict = m.group(1).upper() if m else None
    return verdict, out.strip()[-300:]

def main():
    data = json.load(open(GOLDEN, encoding="utf-8"))
    cases = data["cases"]
    fails, criticals = 0, 0
    print(f"=== adr-check 골든셋 회귀 ({len(cases)} 케이스) ===")
    for c in cases:
        verdict, tail = run_case(c)
        ok = (verdict == c["expect"])
        mark = "PASS" if ok else "FAIL"
        crit = " [CRITICAL 미탐]" if (not ok and c["kind"] == "core" and c["expect"] == "CONFLICT") else ""
        print(f"  {mark} {c['id']} (expect={c['expect']} got={verdict}){crit}")
        if not ok:
            fails += 1
            if crit:
                criticals += 1
            print(f"     tail: {tail!r}")
    print(f"=== 결과: {len(cases)-fails}/{len(cases)} 통과, 치명 미탐 {criticals}건 ===")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
