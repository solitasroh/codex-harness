#!/usr/bin/env python3
"""codex PreToolUse 훅 — claude guard_dangerous 로직을 codex 네이티브로 이식.

수장 지시(2026-07-05): 사후 로그 감사(FN 릴레이) 대신 codex에 가드를 직접 심어
"실행 전 차단"한다. codex는 claude 훅/스킬을 못 읽지만 자체 PreToolUse 훅이 있다.

동작:
- stdin: codex가 주는 JSON {tool_name, tool_input:{command}, ...}
- Bash/apply_patch의 command(또는 patch 본문)를 위험 패턴과 대조
- 위험하면 stdout에 permissionDecision=deny JSON → codex가 실행 전 차단
- 안전하면 exit 0 무출력 → 통과

한계(문서 명시): PreToolUse는 "완전한 강제 경계"가 아니라 가드레일 —
단순 셸만 가로채고 unified_exec 등은 불완전. 근본 차단은 컨테이너 격리.
그래도 "실행 전 거부"라 사후 로그 감사보다 우월(두더지잡기 탈피).
"""
import sys, os, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
# 패턴 파일 위치: 훅이 plugin/.codex/hooks/ 또는 $CODEX_HOME/hooks/ 어디에 설치돼도 찾도록
# 여러 후보 + 환경변수 override(DANGER_PATTERNS)를 순서대로 탐색.
def _resolve_pat():
    env = os.environ.get("DANGER_PATTERNS")
    if env and os.path.exists(env):
        return env
    cands = [
        os.path.join(HERE, "..", "..", "lib", "danger_patterns.txt"),   # plugin/.codex/hooks → plugin/lib
        os.path.join(HERE, "..", "lib", "danger_patterns.txt"),
        "/opt/data/projects/cc-plugin/plugin/lib/danger_patterns.txt",  # 절대경로 fallback
    ]
    for c in cands:
        c = os.path.normpath(c)
        if os.path.exists(c):
            return c
    return cands[0]
PAT_FILE = _resolve_pat()

def load_patterns():
    pats = []
    try:
        for line in open(PAT_FILE, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                tag, rx = parts
                try:
                    pats.append((tag, re.compile(rx)))
                except re.error:
                    pass
    except FileNotFoundError:
        pass
    # 훅 전용 추가 방어(셸 실행 시점에만 의미 있는 것 — 스캐너와 중복 무해)
    extra = [
        ("rm_rf_abs", re.compile(r'\brm\s+(-[a-zA-Z]*\s+)*-?[rf]{1,2}[a-zA-Z]*\s+(/|\$HOME|~)(\s|/|$)')),
        ("mkfs", re.compile(r'\bmkfs\b')),
        ("dd_disk", re.compile(r'\bdd\b[^\n]*\bof=/dev/')),
        ("fork_bomb", re.compile(r':\(\)[[:space:]]*\{.*&[[:space:]]*\}[[:space:]]*;[[:space:]]*:')),
        ("chmod_root", re.compile(r'\bchmod\s+-R\s+777\s+/')),
    ]
    return pats + extra

def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)   # 출력이 차단을 표현. 프로세스 자체는 정상 종료.

def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # 입력 파싱 실패 = 판단 불가 → fail-closed로 차단(안전측).
        deny("훅 입력 JSON 파싱 실패 — 안전측 차단(fail-closed)")
        return

    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {})
    # Bash·apply_patch 모두 tool_input.command 사용(문서). 문자열/리스트 모두 커버.
    cmd = ""
    if isinstance(ti, dict):
        c = ti.get("command", "")
        cmd = c if isinstance(c, str) else " ".join(map(str, c)) if isinstance(c, list) else str(c)
    elif isinstance(ti, str):
        cmd = ti
    if not cmd:
        cmd = json.dumps(ti, ensure_ascii=False)   # MCP 등 — 인자 전체를 텍스트로 대조

    for tag, rx in load_patterns():
        if rx.search(cmd):
            deny(f"위험 패턴 '{tag}' 감지 → 실행 전 차단. 명령: {cmd[:120]}")

    # 안전: 무출력 exit 0 = 통과
    sys.exit(0)

if __name__ == "__main__":
    main()
