#!/usr/bin/env python3
"""codex rollout 로그 감사기 — 브라이언 QA (b) '실행 중 행위' 감사.

diff는 "무엇이 남았나"만 보고, codex가 실행 중 한 셸 명령(create-then-delete, curl|sh,
workdir 밖 절대경로 쓰기, 외부 접속)은 diff에 안 남는다. 하지만 codex는 자기 rollout 로그
(.codex_home/sessions/**/rollout-*.jsonl)의 function_call name=exec_command 에 실제 실행한
모든 셸 명령(arguments.cmd)을 남긴다. 이걸 뽑아 위험패턴(scan_danger 데이터) + escape 패턴으로
대조한다. 로그는 codex 자신의 명령만 담기므로 다른 프로세스 활동과 안 섞인다(스냅샷 diff 오탐 해결).

사용:
  audit_codex_log.py --session-after <epoch> [--workdir <wd>] [--patterns <file>]
  audit_codex_log.py --rollout <path>            # 특정 로그 직접 지정
반환: 위험/escape 히트 있으면 stderr 리포트 + exit 2. 없으면 exit 0.
"""
import json, glob, os, re, sys, argparse, time

CODEX_HOME = os.environ.get("CODEX_HOME", "")

def load_patterns(path):
    pats = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            tag, _, rx = line.partition(" ")
            if rx:
                pats.append((tag, re.compile(rx)))
    return pats

def extract_commands(rollout_path):
    """rollout jsonl에서 codex의 행위 추출.
    반환: [(kind, text)] — kind='exec'(셸 명령) | 'patch_path'(apply_patch 대상 경로).
    codex는 파일을 두 경로로 쓴다: (1) exec_command 셸 리다이렉트, (2) apply_patch custom_tool.
    둘 다 봐야 escape를 놓치지 않는다(실측: apply_patch가 절대경로 Add File 가능)."""
    acts = []
    for line in open(rollout_path, encoding="utf-8"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") != "response_item":
            continue
        p = o.get("payload", {})
        pt = p.get("type")
        if pt == "function_call" and p.get("name") == "exec_command":
            try:
                args = json.loads(p.get("arguments", "{}"))
            except Exception:
                continue
            cmd = args.get("cmd") or args.get("command")
            if cmd:
                acts.append(("exec", cmd if isinstance(cmd, str) else " ".join(cmd)))
        elif pt == "custom_tool_call" and p.get("name") == "apply_patch":
            body = p.get("input", "") or ""
            # apply_patch 대상 경로: '*** Add/Update/Delete File: <path>'
            for m in re.finditer(r'\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(\S+)', body):
                acts.append(("patch_path", m.group(1)))
            # 패치 본문 자체도 위험패턴 대조 대상(코드 내용)
            acts.append(("exec", body))
    return acts

def _session_cwd(fp):
    """rollout의 session_meta.cwd 반환(없으면 None)."""
    try:
        for line in open(fp, encoding="utf-8"):
            o = json.loads(line)
            if o.get("type") == "session_meta":
                return o.get("payload", {}).get("cwd")
    except Exception:
        pass
    return None

def _norm(p):
    """심링크·슬래시 흡수 정규화(FN5-D #3). 실패 시 abspath."""
    if not p:
        return None
    try:
        return os.path.realpath(p)
    except Exception:
        return os.path.abspath(p)

def find_rollouts(after_epoch, cwd_filter=None):
    """after_epoch 이후 로그를 (matched, unmatched)로 분류(스킵하지 않음 — FN5-D fail-open 방지).
    matched  = session_meta.cwd가 이 run workdir와 일치 → 이 run 확정.
    unmatched= cwd 불일치/특정불가 → 이 run인지 불확실 → 위험 발견 시 opaque(리뷰 플래그)로 표면화.
    '스킵'이 미탐(fail-open)을 만들었으므로, 애매하면 버리지 말고 사람에게 표면화한다."""
    matched, unmatched = [], []
    ncwd = _norm(cwd_filter) if cwd_filter else None
    for fp in glob.glob(os.path.join(CODEX_HOME, "sessions", "**", "rollout-*.jsonl"), recursive=True):
        if os.path.getmtime(fp) < after_epoch:
            continue
        if ncwd is None:
            matched.append(fp)  # 필터 없으면 전부 감사
            continue
        log_cwd = _norm(_session_cwd(fp))
        if log_cwd == ncwd:
            matched.append(fp)
        else:
            unmatched.append(fp)
    return matched, unmatched

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-after", type=float, help="이 epoch 이후 수정된 rollout만 감사")
    ap.add_argument("--rollout", help="특정 로그 직접 지정")
    ap.add_argument("--workdir", help="정상 workdir(이 밖 절대경로 쓰기 = escape 의심). 로그 특정에도 사용.")
    ap.add_argument("--delegated", action="store_true",
                    help="이번에 실제 위임함을 명시. 이 경우 로그 0건이면 이상신호(opaque)로 처리(FN5-D #2).")
    default_pat = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "lib", "danger_patterns.txt")
    ap.add_argument("--patterns", default=default_pat)
    args = ap.parse_args()

    pats = load_patterns(args.patterns)
    wd = os.path.abspath(args.workdir) if args.workdir else None
    if args.rollout:
        matched, unmatched = [args.rollout], []
    else:
        matched, unmatched = find_rollouts(args.session_after or 0, cwd_filter=wd)
    if not matched and not unmatched:
        # 위임했는데 로그 0건 = 정상 아님, 이상신호(FN5-D #2). 그 외엔 통과.
        if args.delegated:
            print("=== ⚠ OPAQUE: 위임했으나 감사할 rollout 로그 0건 → 이상신호(P1 검토) ===", file=sys.stderr)
            sys.exit(3)
        print("audit: 감사할 rollout 로그 없음(정상일 수 있음)", file=sys.stderr)
        sys.exit(0)


    def is_escape_path(raw, base):
        """raw 경로가 workdir 밖을 가리키면 True. 상대경로는 base(workdir) 기준 정규화(FN2).
        화이트리스트 = workdir 하위 + /dev/null 만(FN1: /tmp 무조건 제외 폐지)."""
        if not base:
            return False
        raw = raw.strip().strip('"').strip("'")
        if raw in ("/dev/null",):
            return False
        # 상대경로는 workdir 기준으로 해석(codex cwd=workdir)
        ap = raw if os.path.isabs(raw) else os.path.join(base, raw)
        ap = os.path.abspath(ap)
        return not (ap == base or ap.startswith(base + os.sep))

    # 유출/쓰기 명령에서 경로 인자를 뽑는 패턴(FN3: 리다이렉트 외 cp/mv/tee/dd/curl -o 등)
    # 리다이렉트 대상
    redir = re.compile(r'>>?\s*("?[^\s;|&"]+"?)')
    # 명령별 경로 인자(마지막/특정 인자)
    write_cmds = [
        re.compile(r'\b(?:cp|mv|install|ln)\b\s+.+?\s+("?[^\s;|&"]+"?)\s*$'),  # 목적지=마지막
        re.compile(r'\btee\b\s+(?:-a\s+)?("?[^\s;|&"]+"?)'),
        re.compile(r'\bdd\b[^\n]*\bof=("?[^\s;|&"]+"?)'),
        re.compile(r'\b(?:curl|wget)\b[^\n]*\s-[oO]\s*("?[^\s;|&"]+"?)'),
        re.compile(r'\brsync\b\s+.+?\s+("?[^\s;|&"]+"?)\s*$'),
    ]

    def scan_escape_targets(text):
        """text(셸 명령)에서 workdir 밖을 가리키는 쓰기 대상 경로들을 수집."""
        found = []
        for rx in [redir] + write_cmds:
            for m in rx.finditer(text):
                tgt = m.group(1)
                if is_escape_path(tgt, wd):
                    found.append(tgt)
        return found

    # OPAQUE 실행 표면화(브라이언 FN4/소견): 명령 텍스트만으로 행위를 알 수 없는 실행.
    # 완벽 탐지 목표 아님 — "감사 사각지대"를 표면화해 자동 GREEN 과신을 막는 fail-closed 메타규칙.
    # 차단(exit 2)이 아니라 리뷰 플래그(exit 3). 개별 유출 정규식(두더지잡기)과 다른 층위.
    IO_HINT = re.compile(r'\b(open|write|read|socket|urllib|requests|subprocess|shutil|'
                         r'os\.(system|remove|popen|exec)|Path|base64|pickle|marshal)\b')
    def is_opaque(text):
        # 인터프리터 -c/-e 코드 문자열 실행 + 그 안에 I/O 신호가 있으면 사각지대
        if re.search(r'\b(python[0-9.]*|perl|ruby|node|php|lua)\b[^\n]*\s-(c|e)\b', text) \
           and IO_HINT.search(text):
            return True
        # base64/xxd 디코드를 인터프리터로 파이프 = 난독 실행
        if re.search(r'\b(base64|xxd)\b[^\n]*(-d|--decode)[^\n]*\|\s*(sh|bash|python|perl|ruby|node)\b', text):
            return True
        return False

    def audit_one(rp):
        """로그 하나에서 (hits, opaque_items) 반환. hits=escape/위험, opaque=사각지대."""
        h, op = [], []
        for kind, text in extract_commands(rp):
            if kind == "patch_path":
                if is_escape_path(text, wd):
                    h.append((os.path.basename(rp), "escape_patch", text[:120]))
                continue
            for tag, rx in pats:
                if rx.search(text):
                    h.append((os.path.basename(rp), tag, text[:120]))
            for tgt in scan_escape_targets(text):
                h.append((os.path.basename(rp), "escape_write", text[:120]))
            if is_opaque(text):
                op.append((os.path.basename(rp), text[:120]))
        return h, op

    # matched(이 run 확정): 위험 발견 시 하드차단(exit 2).
    hits, opaque = [], []
    for rp in matched:
        h, op = audit_one(rp)
        hits += h
        opaque += op
    # unmatched(cwd 불일치/특정불가): 이 run인지 불확실 → 위험이든 뭐든 opaque로 표면화(스킵 금지, FN5-D).
    #   fail-open 방지: '버리지 않고' 사람에게 올린다. 단 하드차단(2)은 아니고 리뷰 플래그(3).
    unmatched_flag = []
    for rp in unmatched:
        h, op = audit_one(rp)
        if h or op:
            unmatched_flag.append((os.path.basename(rp), len(h), len(op)))

    if hits:
        print("=== 🔴 rollout 로그 감사: 위험/escape 행위 탐지(이 run 확정) ===", file=sys.stderr)
        for rp, tag, cmd in hits:
            print(f"  [{tag}] {rp}: {cmd}", file=sys.stderr)
        print(f"  총 {len(hits)}건 → apply 금지, 사람 검토(P1).", file=sys.stderr)
        sys.exit(2)
    if opaque or unmatched_flag:
        print("=== ⚠ OPAQUE: 로그만으로 안전 확정 불가(감사 사각지대) ===", file=sys.stderr)
        for rp, cmd in opaque:
            print(f"  [opaque] {rp}: {cmd}", file=sys.stderr)
        for rp, nh, nop in unmatched_flag:
            print(f"  [unmatched-cwd] {rp}: 위험{nh}·opaque{nop}건 (이 run 로그인지 불확실→표면화, FN5-D)", file=sys.stderr)
        print("  → 로그 감사 '통과'가 안전 보장 아님. P1 diff/로그 사람 검토 필수. 근본은 컨테이너 격리.", file=sys.stderr)
        sys.exit(3)
    print("audit: 실행 중 위험 행위 없음(로그 기준). 단 로그 감사는 탐지 보조지 완전 차단막 아님.", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()
