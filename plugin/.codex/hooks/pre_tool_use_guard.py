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
#
# ★ 크로스플랫폼 지뢰 수정(백팀장, 2026-07-07): 이전엔 마지막 폴백이 리눅스 절대경로
#   (/opt/data/.../danger_patterns.txt) 하나뿐이었다. 윈도우에선 그 경로가 없고
#   DANGER_PATTERNS env 주입도 없어(그 주입은 codex_run.sh=bash 경로 전용) → 패턴 0개 →
#   fail-closed 가 발동해 '안전한 명령까지 전부 deny'되는 사실상 전면 코딩 차단이 재현됐다.
#   해결: (1) 훅과 같은 디렉터리(HERE/danger_patterns.txt)를 최우선 후보로 추가하고,
#   설치측(codex_run.sh / bootstrap.ps1)이 훅을 CODEX_HOME/hooks/ 로 복사할 때 패턴 파일도
#   같은 폴더에 함께 복사한다. 이러면 env·절대경로 없이도 OS 무관하게 자기 옆에서 찾는다.
#   (2) CLAUDE_PLUGIN_ROOT 기반 후보를 추가해 플러그인 설치 위치가 어디든 lib/ 를 찾는다.
def _resolve_pat():
    env = os.environ.get("DANGER_PATTERNS")
    if env and os.path.exists(env):
        return env
    cands = [
        os.path.join(HERE, "danger_patterns.txt"),                      # ★ 훅과 동일 폴더(설치 시 함께 복사) — OS 무관 1순위
        os.path.join(HERE, "..", "..", "lib", "danger_patterns.txt"),   # plugin/.codex/hooks → plugin/lib (개발 트리)
        os.path.join(HERE, "..", "lib", "danger_patterns.txt"),
    ]
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        cands.append(os.path.join(plugin_root, "lib", "danger_patterns.txt"))
    for c in cands:
        c = os.path.normpath(c)
        if os.path.exists(c):
            return c
    return os.path.normpath(cands[0])
PAT_FILE = _resolve_pat()

def load_patterns():
    """단일 원본(danger_patterns.txt)에서 로드. 형식 'layer:tag regex'.
    ★ 자비서 구멍 ①: 이전엔 셸 가드 패턴(fork_bomb 등)을 여기 하드코딩해 스캐너와 발산했다.
    ★ 3계층 필터(2026-07-08): 이 codex 훅(셸 실행 직전 가드)은 shell(셸 전용) + both(코드·셸 공용)만
      읽는다. code 순수계층(danger_flag=--dangerously/--yolo, secret_literal)은 제외 — 정식 위임
      'codex exec --dangerously-bypass-approvals-and-sandbox' 오탐 차단 버그 해결. curl|sh·os.system·
      subprocess·eval·rm_rf 는 both 로 재분류돼 여기서도 그대로 차단(fail-open 방지). fork_bomb 정규식
      버그([[:space:]]→\\s)도 파일에서 수정됨.
    접두어 없는 구형 라인은 code 계층으로 간주(=셸 가드 제외, 하위호환)."""
    pats = []
    try:
        for line in open(PAT_FILE, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tok, _, rx = line.partition(" ")
            if not rx:
                continue
            layer, sep, tag = tok.partition(":")
            if not sep:
                layer, tag = "code", tok
            if layer not in ("shell", "both"):
                continue
            try:
                pats.append((tag, re.compile(rx)))
            except re.error:
                pass
    except FileNotFoundError:
        pass
    return pats

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

    patterns = load_patterns()
    # ★ fail-closed(브라이언 검증·가드딥다이브): 단일원본화의 새 실패모드 — 패턴 원본을 못 읽어
    #   0개면 "위험 없음"이 아니라 "판단 불가"다. 조용히 통과(fail-open) 금지. JSON 파싱 실패를
    #   deny하는 것과 같은 논리. 실측 재현: 빈 원본 주면 포크폭탄이 allow로 샜다 → 여기서 봉인.
    if not patterns:
        deny("위험 패턴 원본 로드 실패(0개) — 판단 불가로 안전측 차단(fail-closed)")
        return

    for tag, rx in patterns:
        if rx.search(cmd):
            deny(f"위험 패턴 '{tag}' 감지 → 실행 전 차단. 명령: {cmd[:120]}")

    # 안전: 무출력 exit 0 = 통과
    sys.exit(0)

if __name__ == "__main__":
    main()
