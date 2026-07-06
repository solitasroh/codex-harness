# DevLead 산출 — adr-check 골든셋 회귀 하네스 (브라이언 L3 권고 구현)

작성: 백팀장(DevLead) | 2026-07-05 | 대상: 브라이언 QA §L3 "골든셋 회귀 고정" 권고

## 왜 만들었나
브라이언 지적: **스킬은 프롬프트(확률적)라 "1회 통과=항상 통과"가 아니다. 프롬프트를
고치면 게이트가 조용히 무너질 수 있으니 골든셋을 고정해 스킬 수정 시마다 재실행하라.**
→ 맞는 지적. adr-check는 내 소관 스킬이므로 회귀 하네스로 못 박았다.

## 구현물
- `plugin/tests/golden/adr_golden.json` — 브라이언 QA 기준 §L2 **ADR-1~4 골든셋을 fixture로 고정**.
  각 케이스 = 기존 ADR 본문 + CONTEXT.md + 신규 결정 + expect(CONFLICT|OK) + kind(core/noncore).
- `plugin/tests/golden/golden_adr.py` — fixture 읽어 케이스마다 임시 workdir에 ADR/CONTEXT 기록 →
  `HOME=/opt/data claude --plugin-dir <plugin> --permission-mode bypassPermissions`로 adr-check 스킬
  라이브 태움 → 응답의 `VERDICT: CONFLICT|OK` 파싱 → expect 대조. **core 케이스 미탐 = 치명 표시.**

## 실측 결과 (claude 라이브 4케이스)
```
PASS ADR-1 (expect=CONFLICT got=CONFLICT)   # Rust 재작성 vs "stdlib only" → 충돌 감지
PASS ADR-2 (expect=CONFLICT got=CONFLICT)   # 무조건 차단 vs "strict opt-in" → 충돌 감지
PASS ADR-3 (expect=OK got=OK)               # Conventional Commits(무관) → 오탐 없음
PASS ADR-4 (expect=OK got=OK)               # 기존 방침 유지(멱등) → 오탐 없음
결과: 4/4 통과, 치명 미탐 0건, exit 0
```
- 브라이언 우선순위(**미탐 > 오탐**) 관점: core 충돌 2건 전부 감지(미탐 0), 무관/멱등 2건 정확 통과(오탐 0).

## 운영 메모 (하네스 실행 조건 — 코드 주석에도 명시)
- `HOME=/opt/data` 필수(claude credentials 위치). 없으면 인증 실패.
- `--permission-mode bypassPermissions` 필수(파일 접근). 없으면 승인 대기로 exit 124 타임아웃.
- 환경변수 오버라이드: `CLAUDE_HOME_OVERRIDE`, `GOLDEN_TIMEOUT`.

## 한계 (브라이언 L3 정신 계승 — 숨기지 않음)
- 이것도 **표본**이지 증명이 아니다. 4/4 통과는 "이 대표 케이스에선 게이트 작동"을 보이는 것.
- 가치는 **회귀 탐지**: 앞으로 adr-check SKILL.md를 고쳤을 때 이 하네스를 돌려 게이트가
  무너졌는지(예: 충돌을 놓치기 시작) 즉시 잡는다. 코드 회귀 스위트와 동일 정신.
- pytest 스위트(18/18 코드 회귀)와 분리 운용: 코드=결정적 회귀, 골든셋=확률적 스킬 회귀.
