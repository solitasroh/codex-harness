# DevLead 통합 검증 — codex_run.sh ↔ qa_verify.sh (D1 통합 + 실증)

작성: 백팀장 | 근거: 이 컨테이너 실제 실행, 2026-07-05 | 브라이언 QA 재회신에 대한 응답

## 브라이언 D1/D2 수용 & 통합 완료

### D1 (테스트 실행 스텝 없음) → 통합함
`codex_run.sh` 파이프라인 끝에 `qa_verify.sh <workdir> [expected]` 호출 추가.
이제 한 흐름: **위임 → diff 캡처 → QA 자동검증 → done/재작업 판정**.
구현 주의점(내가 처리):
- `set -e`가 qa_verify의 exit 1(재작업 신호)에 죽지 않도록 `|| QA_RC=$?`로 rc 캡처 후 명시 전파.
- codex_run.sh의 최종 exit code = QA 판정(0=게이트통과 / 1=재작업). 상위 오케스트레이터가 이걸로 분기.
- `SCRIPT_DIR` 기반 경로 resolve로 어디서 호출해도 qa_verify를 찾음.
- 폴백 러너가 `git diff --cached`를 보므로 검증 전 `git add -A` 재보장.

### D2 (test 파일 존재≠통과) → 실증으로 종결
새 run(fizzbuzz)으로 전체 파이프라인 실행:
- 위임 → fizzbuzz.py + test_fizzbuzz.py(3,5,15,7 커버) 생성 → diff 캡처
- QA L1: 경계 ✅ 문법 ✅ / L2: **4/4 통과** / 판정 ✅ / codex_run.sh **exit 0**

## 브라이언 조건 2건 처리

### (b) pytest venv 설치 → 완료 + 표준 러너 경로 실증
- `.venv` 생성 + `pytest 9.1.1` 설치.
- qa_verify를 pytest 보이는 환경에서 재실행 → `4 passed`, `(runner=pytest)`, **exit 0**.
- 즉 **폴백(direct)·표준(pytest) 두 경로 모두 동작 확인**. 회귀 스위트는 표준 러너 사용 권고 수용.

### fail-closed 검증 (내가 추가로 확인 — 통과만 보는 건 반쪽)
의도적 버그(`add`가 뺄셈) run으로 게이트가 **실패를 잡는지** 확인:
- pytest 경로: `FAILED test_add - assert -1 == 5` → **exit 1** (재작업 판정) ✅
- 폴백 경로: `AssertionError` → **exit 1** (재작업 판정) ✅
- → 게이트가 통과·실패 양방향 모두 정확. **fail-closed 실증.**

## 현재 파이프라인 (확정)
```
codex_bootstrap.sh   # CODEX_HOME 표준화(auth 600 + config), 1회
  └ codex_run.sh "<프롬프트>" [expected]   # 일회용 workdir + git baseline
       ├ codex exec --dangerously-bypass-* -C <wd>   # 내장샌드박스 off(불가피), 위임
       ├ git diff --cached                            # 리뷰 게이트용 diff
       └ qa_verify.sh <wd> [expected]                 # 3계층 루브릭 → exit 0/1
```
안전 경계 = 컨테이너(외부격리) + 일회용 workdir + diff 리뷰 + QA fail-closed 게이트.

## L3(교차검증) 다음 단계
현재 L1·L2 자동화 완료. L3(코딩=Codex → 검수=Claude 다른벤더 + diff 의도일치)는
Claude 오케스트레이터가 diff를 읽고 판정하는 스텝으로 붙일 예정. phase 계획에 반영.
