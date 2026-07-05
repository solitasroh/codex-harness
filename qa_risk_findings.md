# QA 소견: Codex 코딩 위임 — 리스크·보안·완료판정

작성: 브라이언(QA) | 근거: 이 서버 실측(2026-07-05) + PM 브리프 교차확인
안건: ① 비공식 플러그인(A) 보안 리스크 ② 샌드박스 기본 정책 ③ "코딩 완료" 판정 루브릭

---

## 핵심 결론 (먼저)

> **이 서버에서 codex의 OS 샌드박스는 "작동한다"고 검증되지 않는다.**
> 따라서 `--sandbox read-only/workspace-write`를 우리의 *진짜* 안전 경계로 믿으면 안 된다.
> 실제 경계는 **프로세스/파일시스템 격리(일회용 workdir + git 체크포인트 + apply 전 diff 리뷰)**로 세워야 한다.
> "테스트 안 한 것은 동작하지 않는 것이다" — 샌드박스도 예외 없음.

---

## 실측 증거

### E1. bubblewrap 부재
- `which bwrap` → **NOT FOUND**. codex의 Linux 샌드박스 백엔드가 의존하는 bwrap이 없음.
- uid=10000(hermes), **sudo/root 없음** → 우리가 bwrap을 설치하거나 권한을 조정할 수도 없음.

### E2. codex sandbox 헤드리스 무응답 (재현됨, 빈도 1/1)
- 조건: 게이트웨이 headless 셸(stdin/stdout not a terminal).
- 행동: `codex sandbox --config sandbox_mode=read-only -- bash -c '...'`
- 결과: **90초 내 반환 없음(무응답/행)**. read-only가 쓰기를 막는지 확인조차 불가.
- 심각도: **Major** — 안전장치의 동작을 검증할 수 없다는 것 자체가 리스크.
- → research_pipeline.md §4 caveat("게이트웨이에서 bubblewrap 샌드박스 깨질 수 있음")을 구체적으로 재현·확정함.

### E3. config 로드 실패
- `codex doctor` → `✗ config: config could not be loaded`. 실 config.toml 깨짐/미접근.
- 우회: PM이 만든 `CODEX_HOME=/tmp/codex_probe`(auth.json+최소 config, hermes 읽기가능) 존재·유효.

### E4. MCP(B)는 정책 인자를 명시적으로 노출
- `codex` 툴 인자에 `approval-policy`(untrusted/on-failure/on-request/never) + `sandbox`(read-only/workspace-write/danger-full-access).
- 즉 정책 결정지점이 **호출 인자로 감사 가능**. A(플러그인 node 래퍼)는 이 지점이 블랙박스.

---

## ① 비공식 플러그인(A) 검증단계 사용 — 보안 리스크

| 리스크 | 내용 | QA 판정 |
|--------|------|---------|
| 공급망 | Anthropic 공식 저장소에 없음(서드파티). node 래퍼가 임의 코드 실행 | 검증단계 한정 허용 가능, 단 **핀 고정** |
| 블랙박스 | 내부 동작·전달 인자 불투명(E4). 우리가 샌드박스/승인정책을 통제하는지 확인 불가 | **중대 감점** |
| 경로 변동 | 버전 디렉토리 동적 resolve → 재현성 취약 | 회귀테스트 방해 |

**권고**: A는 "cookoff 파이프라인을 눈으로 한 번 본다"는 **검증 1회용**으로만. 조건 3개 필수 —
(a) 커밋 SHA/버전 **핀 고정** 후 diff 감사, (b) **일회용 workdir + git clean**에서만 실행, (c) 프로덕션/우리 코드베이스 경로 절대 금지. 검증 후 최종 백엔드는 **B(MCP)로 표준화**(E4의 감사가능성 때문). → PM 하이브리드 판단에 QA 동의.

---

## ② 샌드박스 기본 정책 권고

**전제: E1~E2 때문에 codex 자체 샌드박스는 "보조"이지 "경계"가 아니다.**

| 단계 | codex 인자 기본값 | 실제 안전 경계(필수) |
|------|------------------|---------------------|
| 설계/그릴링(read/analyze) | `--sandbox read-only` | 애초에 쓰기 프롬프트 금지 |
| 코딩 위임 | `--sandbox workspace-write` + `--approval-policy on-request` | **일회용 workdir + git init + apply 전 `git diff` 리뷰** |
| danger-full-access | **금지(기본)**. 불가피 시 수장 승인 + 격리 컨테이너 한정 | — |

- 기본 승인정책은 `never` 금지 → **on-request** 권장(무인 자율루프라도 위험명령은 게이트).
- `--dangerously-bypass-*` 플래그는 **정책상 차단 대상**. 훅(PreToolUse exit 2)으로 명령 차단 검토.
- 네트워크: 코딩단계 기본 차단, 필요 시 명시 허용(화이트리스트).

---

## ③ "코딩 완료" 판정 루브릭 (verify-before-done 이식 + QA 강화)

Codex 자기보고("완료했습니다")는 **증거 아님**. 3계층 게이트 통과해야 done:

**L1 Mechanical (기계적, 자동)**
- [ ] 빌드/컴파일 성공 (실제 명령 출력 첨부)
- [ ] 린트/타입체크 신규 에러 0 (baseline 대비)
- [ ] 변경 파일이 workdir 경계 안(밖 수정 = 즉시 실패)

**L2 Behavioral (행위적, 자동+탐색)**
- [ ] 테스트 통과 & **회귀 0**(변경 전 baseline_failures 대비 신규 실패 없음)
- [ ] happy path뿐 아니라 **경계값/예외/빈입력** 최소 1케이스씩 확인
- [ ] 요구된 acceptance criteria 항목별 ✅ (없으면 착수 전 PM에 요구)

**L3 Consensus (교차검증)**
- [ ] 코딩=Codex면 **검수는 다른 벤더(Claude)** — 자기검수 금지(영상2 크리틱 원칙)
- [ ] 독립 리뷰어가 보안(시크릿/injection/eval/path traversal) + 로직오류 스캔 → **fail-closed**(하나라도 걸리면 done 아님)
- [ ] diff가 프롬프트 의도와 일치(범위 초과 변경 = 반려)

**판정**: L1∧L2∧L3 전부 통과만 "done". 하나라도 미통과 = **재작업**. 증거(명령 출력/diff/리뷰 JSON) 없으면 자동 "미완료".
심각도 분류: Critical(빌드깨짐/보안) → 즉시 반려, Major(회귀/acceptance 미충족) → 반려, Minor(스타일) → non-blocking 기록.

---

## 릴리스 게이트 관점 요약
- **지금 이대로 무인 자율루프 = 반대.** 이유: 샌드박스 미검증(E1~E2) + config 불안정(E3).
- **선결 인프라 2건**: (가) CODEX_HOME 표준화(E3 우회를 정식화) (나) 격리 workdir 규약 확정.
- 이 2건 + 위 루브릭이 서면화되면 검증단계 착수 GO.

---

## [갱신 2026-07-05] 백팀장 canary 검증에 대한 QA 재현·판정

백팀장이 말 대신 실행으로 규명 → QA가 자기보고 불신 원칙으로 **직접 재현**함.

### 확정(QA 재현 PASS)
- **E1~E2 원인 규명 동의**: read-only/workspace-write가 canary를 막은 게 아니라 `bwrap: No permissions to create a new namespace`로 셸 자체 사망. 즉 "안전하게 막힌" 게 아니라 "샌드박스 켜면 코딩 자체 불가". → 내 초기 우려("경계로 믿지 마라")보다 강한 결론: 이 환경에선 **내장 샌드박스를 켜는 것 자체가 물리적으로 불가능**. QA 동의.
- **실물 존재 확인**: `scripts/codex_bootstrap.sh`, `scripts/codex_run.sh`, `runs/run_oVoxIE/{hello.py,test_hello.py}` + git baseline 커밋 실재. (verifier가 경고한 bootstrap 미수정은 최종본이 디스크에 존재하므로 무해)
- **격리 3겹**(컨테이너 외부격리 + 일회용 workdir + git diff 게이트) 설계 타당. codex_run.sh가 diff --cached로 리뷰 게이트 실제 구현.

### QA가 실행으로 발견한 결함 (Major, 빈도 1/1)
- **D1. L2 게이트에 테스트 실행 스텝이 없음.** `codex_run.sh`는 diff 캡처까지만 하고 테스트를 **안 돌린다**(grep 확인). 백팀장의 "L2 PASS"는 `python3 hello.py` 수동 1회일 뿐.
- **D2. `test_hello.py`는 한 번도 통과된 적 없음.** 이 환경에 pytest 미설치(`No module named pytest`). 테스트 파일 존재 ≠ 테스트 통과. codex가 "pytest not found"를 정직 보고한 건 좋으나, **그 테스트가 유효한지 아무도 확인 안 함**.
  - QA 조치: 러너 없이 `test_hello_output()` 직접 호출 → **PASS 확정**. 테스트 로직 자체는 유효.

### QA 조치 결과물 (실증 완료)
- **`scripts/qa_verify.sh` 신규 작성** — 3계층 루브릭 자동 적용기. 핵심: **pytest 부재 시 test_ 함수 직접호출 폴백**으로 "러너 없어도 실제로 돌린다".
- **백팀장 run_oVoxIE에 실제 적용 → exit 0**:
  - L1: 변경파일 workdir 경계 내 ✅, py 문법 ✅
  - L2: test_hello_output ✅(direct runner), stdout "hello from codex" 일치 ✅
  - 판정: L1·L2 PASS → L3(다른벤더 교차검증+diff리뷰) 후 done 가능

### 개정된 릴리스 게이트 판정
- **검증단계 착수 GO** (조건부). 근거: 격리 경계 실물 확인 + QA 검증기 동작 실증.
- **선결 D1 반영 필수**: `codex_run.sh` 파이프라인 끝에 `qa_verify.sh <workdir>` 호출을 넣어 diff 캡처 직후 자동 검증. (백팀장께 통합 요청)
- **환경 보강 권고**: pytest를 venv에 설치(없으면 폴백으로 돌지만, 표준 러너 있는 게 회귀 스위트에 유리).
- **수장 결정 대기**: 내장 샌드박스 off(danger-full-access)를 "컨테이너 외부격리 + 격리 workdir + diff/QA 게이트"로 상쇄하는 안전 경계 인정 여부.

---

## [갱신2 2026-07-05] D1 통합 + fail-closed — QA 독립 재현·최종 확정

백팀장이 D1 통합·fail-closed 실증 → QA가 자기보고 불신 원칙으로 **직접 재현**함. **실무 검증 수렴.**

### QA 재현 결과 (전부 PASS)
- **D1 통합 실물 확인**: `codex_run.sh` 43~60행에 `qa_verify.sh` 호출 실재. 구현 디테일 옳음 — `set -e` 회피(`|| QA_RC=$?`), rc 명시 전파(`exit $QA_RC`), 검증 전 `git add -A` 재보장. 파이프라인 최종 exit=QA 판정.
- **pytest venv 확인**: `.venv/bin/pytest` 9.1.1 실재.
- **fail-closed 양방향 QA 직접 재현** (백팀장의 `run_FAIL_qCLm`, `add`가 뺄셈 버그 — `add(2,3)` 기대 5 vs 실제 -1):
  - 폴백 경로(시스템 python3): `qa_verify.sh` → `❌ test_add` AssertionError → 판정 재작업 → **exit 1** ✅
  - pytest 경로(.venv): `FAILED test_mathx.py::test_add - assert -1 == 5` → **exit 1** ✅
  - → 게이트가 통과=통과, 실패=실패로 **양방향 정확**. fail-closed 성립 확정.

### QA 최종 판정
- **L1·L2 자동화 게이트: 합격.** 통과·실패 양방향 실증됨. 증거 없는 self-report는 이제 파이프라인이 물리적으로 차단.
- **잔여 = L3(교차검증)뿐.** 코딩=Codex → 검수=Claude(다른 벤더) + diff 의도일치. phase 계획에 오케스트레이터 스텝으로 반영 예정(백팀장 안 동의).
- **릴리스 게이트: 검증단계 GO (QA측 조건 전부 해소).** 유일 잔여 = 수장 결정(샌드박스 off 안전경계 인정).

### 운영 주의(QA 기록)
- /tmp 등 프로젝트 밖에서 pytest 돌리면 루트까지 수집해 느려짐(타임아웃 관측). 검증은 항상 `--rootdir=<workdir>` 격리 or workdir 내 실행.
- qa_verify 폴백 러너는 unittest 스타일 없이 `test_` 함수 직접호출 → fixture/parametrize 쓰는 테스트는 pytest 경로 필요. 회귀 스위트는 표준 러너 고정 권고.
