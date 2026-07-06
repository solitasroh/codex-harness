#!/usr/bin/env python3
"""QA 정적 검증 도구 — 스킬 SKILL.md가 '빈 껍데기'인지 결정적으로 측정.
기준: design/qa_skill_verification_criteria.md L1.
사용: qa_skill_static_check.py <SKILL.md> [<SKILL.md> ...]
원칙: 측정기 자신도 신뢰돼야 한다 → 판정 근거(매칭 위치)를 함께 출력.
반환: 모든 파일 L1 FAIL 0이면 exit 0, FAIL 있으면 exit 1."""
import sys, re, os

# 게이트 강제성 어휘 (정적 대리 지표)
STRONG = ["반드시", "까지", "금지", "않으면", "모든", "MUST", "절대", "must", "해소될 때까지", "없이"]
WEAK   = ["가능하면", "권장", "되도록", "보통", "선택적", "가급적", "웬만하면"]

def analyze(path):
    if not os.path.exists(path):
        return None, [f"파일 없음: {path} (산출물 대기 중)"]
    txt = open(path, encoding="utf-8").read()
    lines = txt.splitlines()
    fails, warns, notes = [], [], []

    # S1: frontmatter name + description
    fm = re.search(r"^---\s*\n(.*?)\n---", txt, re.S)
    fm_body = fm.group(1) if fm else ""
    has_name = bool(re.search(r"^name:\s*\S", fm_body, re.M))
    desc_m = re.search(r"^description:\s*(.+)$", fm_body, re.M)
    has_desc = bool(desc_m)
    if not (has_name and has_desc):
        fails.append(f"S1 frontmatter 미비(name={has_name}, description={has_desc})")

    # S2: 트리거 조건 (description에 '할 때/when/사용' 등)
    desc = desc_m.group(1) if desc_m else ""
    if not re.search(r"할 때|사용|when|트리거|라고", desc + txt[:400]):
        warns.append("S2 트리거 조건 불명확(언제 켜지는지)")

    # S3: 번호/단계 절차 수
    steps = len(re.findall(r"^#{2,3}\s|^\s*\d+[.)]\s|^\s*-\s", txt, re.M))
    numbered = len(re.findall(r"단계|step|Step|##\s*\d|^\s*\d+[.)]", txt, re.M))
    if numbered < 3:
        warns.append(f"S3 단계 구체화 부족(번호/단계 표지 {numbered}개)")

    # S4: 산출 포맷 정의
    if not re.search(r"포맷|산출|출력|결과물|format|스펙 산출|반환", txt):
        fails.append("S4 산출 포맷 정의 없음")

    # S5: 예시
    if not re.search(r"예시|예:|example|Example|```|예를 들", txt):
        warns.append("S5 예시 없음(프롬프트 실효성↓)")

    # G-static: 게이트 강제성
    strong_hits = [(w, i+1) for i, l in enumerate(lines) for w in STRONG if w in l]
    weak_hits   = [(w, i+1, lines[i].strip()[:50]) for i, l in enumerate(lines) for w in WEAK if w in l]
    if not strong_hits:
        fails.append("G-static 강제 표현 0 — 게이트가 없음(빈 껍데기 의심)")
    if weak_hits:
        warns.append(f"G-static 물렁 표현 {len(weak_hits)}건(게이트 무를 수 있음): " +
                     "; ".join(f"L{ln}:{w}" for w,ln,_ in weak_hits[:3]))
    notes.append(f"강제표현 {len(strong_hits)}건 / 물렁표현 {len(weak_hits)}건 / 절차표지 {steps}개")

    return {"fails": fails, "warns": warns, "notes": notes}, None

def main():
    if len(sys.argv) < 2:
        print("사용: qa_skill_static_check.py <SKILL.md> ..."); sys.exit(2)
    total_fail = 0
    for path in sys.argv[1:]:
        print("="*62); print(f"검사: {path}")
        res, err = analyze(path)
        if err:
            print("  ⏳", *err); continue
        for f in res["fails"]:
            print(f"  ❌ FAIL {f}"); total_fail += 1
        for w in res["warns"]:
            print(f"  ⚠  경고 {w}")
        for n in res["notes"]:
            print(f"  ℹ  {n}")
        if not res["fails"]:
            print("  ✅ L1 정적 FAIL 0" + (" (경고는 보강 권고)" if res["warns"] else " (클린)"))
    print("="*62)
    print(f"총 L1 FAIL: {total_fail}건" if total_fail else "총 L1 FAIL: 0 — 정적 검증 통과")
    sys.exit(1 if total_fail else 0)

if __name__ == "__main__":
    main()
