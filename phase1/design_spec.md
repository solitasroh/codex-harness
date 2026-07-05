# Phase 1 설계·스펙 — diff-digest CLI

작성: 자비서(PM, grill-me 하이브리드 수행) | Phase 1-1~1-3 산출물
방식: cookoff 하이브리드 — 자명한 결정은 [CONSENSUS] 기본값 자동 확정, 판단 필요분만 [NEEDS 수장]

---

## 1. grill-me 결정 트리 (5차원 — 하이브리드 해소)

### Goals (목표)
- [CONSENSUS] git diff를 입력받아 **리뷰어가 빠르게 훑도록 요약**하는 CLI.
- [CONSENSUS] 우리 파이프라인의 "apply 전 diff 리뷰" 게이트 보조가 1차 용도(dogfooding).

### Acceptance (수용 기준 = 이게 곧 QA L2 테스트가 됨)
- [CONSENSUS] 입력: unified diff 텍스트를 **stdin** 또는 **파일 인자**로 받음.
- [CONSENSUS] 출력(기본): 사람이 읽는 텍스트 요약 —
  - 파일별 변경 통계(+추가/-삭제 라인 수), 총계
  - 위험 패턴 히트 목록(패턴명 + 파일:라인 + 매칭 라인 발췌)
- [CONSENSUS] `--json` 플래그: 같은 정보를 JSON으로(기계 소비용).
- [CONSENSUS] 빈 입력 → "no changes" 안내, exit 0.

### Boundaries (경계·정책)
- [CONSENSUS] 위험 패턴 기본 목록(정규식): `eval(`, `exec(`, `os.system`, `subprocess`, `rm -rf`, `--dangerously`, `--yolo`, 시크릿류(`API_KEY|SECRET|PASSWORD|TOKEN\s*=`), `curl .. | sh`.
- [CONSENSUS] 위험 패턴은 **추가된(+) 라인만** 검사(삭제는 위험 유입 아님).
- [CONSENSUS] 종료코드 기본: 위험 패턴 있어도 **exit 0(리포트만)**. `--strict` 지정 시 위험 히트 있으면 **exit 2**(파이프라인 게이트로 활용 가능).

### Alternatives (대안·기술선택)
- [CONSENSUS] 언어: **Python3**(우리 환경 표준). 의존성: **stdlib만**(자기완결, 설치 불필요).
- [CONSENSUS] 단일 파일 `diff_digest.py` + 테스트 `test_diff_digest.py`(pytest & 폴백러너 양립: 순수 `test_` 함수, fixture 미사용).

### Assumptions (가정)
- [CONSENSUS] 입력은 표준 unified diff(`diff --git`, `+++/---`, `@@` 헤더). git diff 산출물 가정.
- [CONSENSUS] 바이너리 diff는 통계에서 제외(파일명만 "binary" 표기).

**[NEEDS 수장] 없음** — 전부 합리적 기본값으로 확정 가능한 소형 유틸. (판단 갈리는 지점 미발생 → 사용자 개입 0. 엘레나 DX 원칙 정확 적용.)

---

## 2. tech-spec (구현 명세 — Codex 위임용)

### 파일
- `diff_digest.py` — CLI 본체
- `test_diff_digest.py` — pytest/폴백 양립 테스트

### 인터페이스
```
python3 diff_digest.py [DIFF_FILE] [--json] [--strict]
# DIFF_FILE 생략 시 stdin에서 읽음
```

### 함수 시그니처 (테스트 대상 = AC)
- `parse_diff(text: str) -> list[dict]` — 파일별 `{path, added, removed, binary}` 리스트 반환.
- `scan_risks(text: str) -> list[dict]` — 추가라인의 위험패턴 히트 `{pattern, path, line_no, snippet}` 리스트.
- `format_text(files: list, risks: list) -> str` — 사람용 요약 문자열.
- `format_json(files: list, risks: list) -> str` — JSON 문자열.
- `main(argv) -> int` — 종료코드 반환(0 정상, 2 = --strict + 위험히트).

### Acceptance Criteria (QA L2가 검증할 항목)
- AC1: 2파일 diff(+3/-1, +0/-5) → parse_diff가 파일별 통계 정확.
- AC2: 추가라인에 `eval(` 있으면 scan_risks가 1건 이상 잡음. 삭제라인의 `eval(`은 안 잡음.
- AC3: 빈 입력 → format_text "no changes", main exit 0.
- AC4: `--strict` + 위험히트 → main returns 2. 위험 없으면 0.
- AC5: `--json` → 유효한 JSON(json.loads 성공), files·risks 키 존재.

---

## 3. ADR (Phase 1-3 — 이번 결정 기록)

- **ADR-001 언어=Python stdlib only**: 우리 환경 표준 + 자기완결(설치 불필요) + 폴백러너 호환. 대안(rust/go 바이너리)은 배포 복잡 → 기각.
- **ADR-002 위험 히트 기본 non-blocking(exit 0), --strict로만 exit 2**: 리뷰 보조가 1차 목적이라 정보성이 기본. 게이트 사용 시 명시적 opt-in. 오탐이 파이프라인을 막지 않도록.
- **ADR-003 테스트는 fixture 미사용 순수 test_ 함수**: qa_verify 폴백러너(pytest 부재 환경) 호환 유지. 회귀 스위트는 표준 pytest(.venv) 사용.

---

## 4. Codex 위임 프롬프트 (Phase 1-4 입력)

> Python3 stdlib만으로 `diff_digest.py` CLI와 `test_diff_digest.py`를 작성하라.
> 위 함수 시그니처와 AC1~AC5를 정확히 충족. 테스트는 pytest 없이도 돌도록 fixture/parametrize 없이 순수 `test_` 함수로. 위험패턴 목록은 스펙의 기본 목록 사용. 외부 의존성 금지.
