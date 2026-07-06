#!/usr/bin/env python3
"""PM 검증: rollout 로그에서 codex가 실행한 셸 명령을 실제로 추출할 수 있나.
브라이언 (b) 로그 스캔 방어책의 실현 가능성 확인."""
import json, os, glob, sys

SESS = "/opt/data/projects/cc-plugin/.codex_home/sessions"
logs = sorted(glob.glob(os.path.join(SESS, "**", "rollout-*.jsonl"), recursive=True))
print(f"로그 파일 {len(logs)}개")

def extract_cmds(path):
    """function_call 중 shell/exec 계열의 command 인자를 뽑는다."""
    cmds = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except: continue
        p = d.get("payload", {})
        if p.get("type") == "function_call":
            name = p.get("name", "")
            args = p.get("arguments", "")
            # arguments는 JSON 문자열인 경우가 많음
            try:
                a = json.loads(args) if isinstance(args, str) else args
            except:
                a = {"_raw": args}
            # shell/exec 계열에서 command 추출
            cmd = None
            if isinstance(a, dict):
                cmd = a.get("command") or a.get("cmd") or a.get("script")
                if isinstance(cmd, list): cmd = " ".join(map(str, cmd))
            cmds.append((name, cmd if cmd else str(a)[:120]))
    return cmds

# 가장 최근 로그 2개 상세
total_cmds = 0
for path in logs[-3:]:
    cmds = extract_cmds(path)
    shell_cmds = [(n,c) for n,c in cmds if c and ("shell" in n.lower() or "exec" in n.lower() or any(k in (c or "") for k in ["python","git","ls","cat","echo","mkdir","rm","curl"]))]
    total_cmds += len(shell_cmds)
    print(f"\n=== {os.path.basename(path)[:40]} ===")
    print(f"  function_call {len(cmds)}건, 셸명령 후보 {len(shell_cmds)}건")
    for n, c in shell_cmds[:5]:
        print(f"    [{n}] {(c or '')[:100]}")

print(f"\n총 셸명령 추출: {total_cmds}건")
print("→ 로그에서 codex 실행 명령 추출 " + ("가능(방어책 실현 가능)" if total_cmds>0 else "불가"))
