#!/usr/bin/env python3
"""위험 코드 스캐너 — 생성 코드/디프의 추가(+) 라인을 패턴으로 검사.

QA 설계 §2 반영:
- 패턴은 데이터 파일(lib/danger_patterns.txt)에서 로드 (운영규칙 #3).
- 기본은 정보성(리포트, exit 0). --strict 히트 시 차단(exit 2) (운영규칙 #4: 차단은 opt-in).
- --diff: unified diff에서 추가(+) 라인만 검사(삭제는 위험 유입 아님).

사용:
  scan_danger.py [--diff] [--strict] [--patterns FILE] [FILE ...]
  cat code.py | scan_danger.py --strict
반환: 히트 있으면 stderr에 리포트. exit: 0(리포트/무히트) / 2(--strict & 히트).
"""
import sys, re, os, argparse

def load_patterns(path, layers=None):
    """단일 원본(danger_patterns.txt)에서 패턴 로드. 형식: 'layer:tag regex'.
    layers: 로드할 계층 집합(예: {"code"}). None이면 전부. (자비서 구멍 ① 단일원본화)
    접두어 없는 구형 라인은 layer='code'로 간주(하위호환)."""
    pats = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            tok, _, rx = line.partition(" ")
            if not rx:
                continue
            layer, sep, tag = tok.partition(":")
            if not sep:            # 구형 'tag regex' → 기본 code 계층
                layer, tag = "code", tok
            if layers is not None and layer not in layers:
                continue
            pats.append((tag, re.compile(rx)))
    return pats

def iter_lines(text, diff_mode):
    for i, line in enumerate(text.splitlines(), 1):
        if diff_mode:
            # unified diff: 추가 라인만(+로 시작, +++ 헤더 제외)
            if line.startswith("+") and not line.startswith("+++"):
                yield i, line[1:]
        else:
            yield i, line

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--diff", action="store_true", help="unified diff의 추가 라인만 검사")
    ap.add_argument("--strict", action="store_true", help="히트 시 exit 2로 차단")
    default_pat = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "lib", "danger_patterns.txt")
    ap.add_argument("--patterns", default=default_pat)
    args = ap.parse_args()

    # 스캐너는 '생성 코드 diff' 계층을 본다: code(코드 전용) + both(코드·셸 공용). 셸 전용(shell)은 제외.
    pats = load_patterns(args.patterns, layers={"code", "both"})
    texts = []
    if args.files:
        for fp in args.files:
            with open(fp, encoding="utf-8") as f:
                texts.append((fp, f.read()))
    else:
        texts.append(("<stdin>", sys.stdin.read()))

    hits = []
    for name, text in texts:
        for lineno, content in iter_lines(text, args.diff):
            for tag, rx in pats:
                if rx.search(content):
                    hits.append((name, lineno, tag, content.strip()[:80]))

    if hits:
        print("=== 위험 패턴 히트 ===", file=sys.stderr)
        for name, lineno, tag, snippet in hits:
            print(f"  [{tag}] {name}:{lineno}: {snippet}", file=sys.stderr)
        if args.strict:
            print(f"차단(--strict): {len(hits)}건", file=sys.stderr)
            sys.exit(2)
        print(f"(정보성 리포트: {len(hits)}건 — 차단하려면 --strict)", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()
