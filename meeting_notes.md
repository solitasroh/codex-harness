# 회의록: Claude Code 플러그인 프로젝트 — Codex 위임 방식 결정 [종합 완료]

프로젝트: cc-plugin | PM: 자비서 | 상태: 3팀장 회신 완료 + PM 교차검증 완료

## 안건
1. 검증단계 백엔드: A(플러그인) vs B(MCP)
2. 최종 코딩 실행기: B(MCP) vs C(codex exec)
3. 인프라 선결: CODEX_HOME/config.toml 권한 + 격리 workdir
4. 보안: 비공식 플러그인, 샌드박스 기본 정책 + 완료 판정

---

## 회신 1 — 엘레나(DesignLead) · DX/워크플로 [접수·반영]
**결론: 표면 UX는 우리 소유(슬래시명령/스킬), 실행기는 B(MCP). A는 검증 참조용만.**
- A vs B는 레이어 분리로 해소: 개발자가 만지는 건 슬래시명령이지 codex 툴이 아님. "A가 자연스럽다"는 착시.
- 근거3: 멘탈모델 일관성 / 신뢰 UX(권한 가시성) / 벤더 독립(영상2 철학).
- Grill me UX 4대 보강: ①인지부하 분배(cookoff식 80% 자동, [NEEDS MAX]만 개입) ②진행감(3/5 표시) ③"왜 묻는지" 맥락 ④핸드오프(결정요약→write-prd→ADR→tech-spec, 死문서 금지) — 영상이 남긴 "비전만 풍부, 구현 디테일 빔" 구멍 정조준.
- GUI 확장(AskUserQuestion→카드/라디오) 염두한 CLI-first.
- 방향 확정 시 DX 와이어 제출 예정.

## 회신 2 — 브라이언(QA) · 리스크/보안 [접수·PM 교차검증]
**핵심 결함 제기: codex OS 샌드박스가 이 서버에서 작동 검증 안 됨 → 진짜 경계는 프로세스/FS 격리.**
- 실측: bwrap NOT FOUND, codex sandbox 헤드리스 무응답, codex doctor config 실패.
- ① 비공식 플러그인 A = 검증 1회용만(SHA핀+일회용workdir+코드베이스금지). 최종 B(MCP) 표준화 동의.
- ② 샌드박스는 "보조"지 "경계" 아님. 실제 경계 = 일회용 workdir+git init+apply전 diff리뷰. danger-full-access 기본금지, never 금지.
- ③ 완료 판정 3계층 루브릭: L1 기계적(빌드/린트/경계) ∧ L2 행위적(테스트+회귀0+경계값+AC) ∧ L3 교차검증(다른 벤더 검수+보안스캔 fail-closed+diff의도일치). 자기보고≠증거.
- 릴리스 게이트: 무인 자율루프 반대. 선결 (가)CODEX_HOME 표준화 (나)격리workdir 규약 → 충족 시 검증 GO.

## 회신 3 — 백팀장(DevLead) · 구현/아키 [접수·PM 교차검증 완료]
**반전 규명: 내장 샌드박스는 "미검증"이 아니라 "이 컨테이너에선 켜면 셸이 죽는다".**
- canary 4종 실측: read-only/workspace-write → `bwrap: No permissions to create a new namespace`로 셸 사망(쓰기 불가). --dangerously-bypass-* → canary 생성 ✅. MCP danger-full-access → canary_mcp 생성 ✅.
- 결정적: unprivileged userns 비활성 + root 없음 → 내장 bwrap이 namespace 못 만듦. **브라이언 권고 "workspace-write+on-request"는 이 환경에서 물리적으로 작동 불가.** 코딩되려면 내장 샌드박스 OFF 필수.
- 위험하냐? 아니오 — 브라이언 결론과 실은 동일. 3겹 격리 구현: ①컨테이너=외부격리(codex 문서가 bypass를 "solely for externally sandboxed environments"로 규정, 우리가 그 케이스) ②일회용 격리 workdir(runs/run_XXXX) ③git baseline+diff 게이트.
- 산출물: codex_bootstrap.sh(CODEX_HOME 표준화) + codex_run.sh(격리workdir+diff게이트). 실위임 테스트: hello.py+test_hello.py 생성, diff 캡처.
- 실행기 확정: **B(MCP) 주력 + C(exec) 보조.**

### PM 교차검증 (봇 자기보고 불신 원칙)
- File-mutation verifier 경고 있었으나 → search_files로 산출물 실존 확인(스크립트2 + runs/run_oVoxIE/ + canary2 + git baseline).
- **L2 재현 실행**: `python3 hello.py` → "hello from codex", rc=0, expected match **TRUE** ✅
- canary_bypass.txt="OK", canary_mcp.txt="MCPOK" 실존 확인 ✅
- codex_run.sh 코드 리뷰: 격리workdir+git baseline+diff게이트가 QA L1과 정합 ✅
- → 백팀장 주장 전부 사실. E1(bwrap부재)·E3(config실패) PM도 직접 재현.

---

## PM 종합 결론

**세 팀장이 서로 다른 각도로 같은 지점에 수렴했다:**
1. **실행기 = B(MCP) 주력 + C(exec) 보조** — 3팀장 만장일치. A(플러그인)는 검증 1회용 참조만.
2. **표면 UX = 우리 소유**(엘레나) / **실행기 = 감사가능한 MCP**(QA E4) / **구현 실증 완료**(백팀장) — 레이어 분리로 일관.
3. **안전 경계 = codex 내장 샌드박스가 아니라 "컨테이너 외부격리 + 일회용 workdir + git diff 게이트"** — QA가 원칙 제시, 백팀장이 실측으로 "내장 샌드박스는 이 환경에서 물리적으로 못 켠다" 확정, 셋의 결론 일치.
4. **완료 판정 = QA 3계층 루브릭**을 백팀장 runs/ diff에 부착.
5. **DX 4대 보강 + 핸드오프 체인**을 phase 스펙에 반영.

**선결 인프라 2건(QA 요구): (가)CODEX_HOME 표준화 (나)격리workdir 규약 → 백팀장이 스크립트로 구현·실증 완료. → 검증단계 착수 조건 충족.**

## 회신 2b — 브라이언(QA) 재회신 · 백팀장 검증 직접 재현 [PM 재교차검증 완료]
**판정 개정: 🚫반대 → ✅검증단계 착수 GO(조건부).**
- QA가 백팀장 canary를 직접 재현 → 샌드박스 원인규명 동의(read-only가 막은 게 아니라 bwrap namespace 불가로 셸 사망 = 내장 샌드박스 물리적 불가). 실물 전부 존재 확인.
- **QA가 실행으로 발견한 결함 2건**: D1) codex_run.sh에 테스트 실행 스텝 없음(diff캡처까지만) D2) test_hello.py가 여태 한 번도 안 통과됨(pytest 미설치). "테스트 파일 존재 ≠ 통과."
- **QA 조치**: `scripts/qa_verify.sh` 신규 작성(3계층 루브릭 자동적용, pytest 부재 시 test_함수 직접호출 폴백). run_oVoxIE 적용 → exit 0.
- 조건부 GO 조건: (a) codex_run.sh 끝에 qa_verify.sh 호출 통합(D1) (b) pytest venv 설치 권고.

### PM 재교차검증 (봇 자기보고 불신 원칙)
- qa_verify.sh 코드 리뷰 → 폴백 러너 로직 실재 확인 ✅
- **PM 직접 실행**: `bash scripts/qa_verify.sh runs/run_oVoxIE "hello from codex"` → L1·L2 전부 PASS, test_hello_output 통과, stdout 일치, **exit 0** ✅
- → 브라이언 D1·D2 지적 및 검증기 동작 전부 사실.

## 최종 팀 합의 (3팀장 + PM 교차검증)
- 실행기 B(MCP)주력+C(exec)보조 · 표면UX 우리소유 · 안전경계=외부격리+workdir+diff/QA게이트 · 완료판정 3계층 루브릭(qa_verify.sh) · DX 4대보강.
- **전원 조건부 GO.**

## 회신 3b — 백팀장 · D1 통합 + fail-closed 실증 [PM 재교차검증 완료]
- **D1 통합**: codex_run.sh 끝에 qa_verify.sh 호출 추가(set -e 회피 위해 `|| QA_RC=$?` rc캡처·명시전파, 최종 exit=QA판정, 검증전 git add -A 보장).
- **D2 종결**: fizzbuzz run으로 L2 4/4 통과, 파이프라인 exit 0.
- **조건 (b)**: .venv + pytest 9.1.1 설치 → `4 passed (runner=pytest)`. 폴백·표준 두 경로 동작.
- **fail-closed 실증**: 의도적 버그(add가 뺄셈) → pytest경로·폴백경로 모두 exit 1.
- 확정 파이프라인: `bootstrap → codex_run(격리workdir+위임+diff) → qa_verify(3계층→exit 0/1)`. L1·L2 자동화 완료. L3(다른벤더 교차검증+diff의도일치)는 오케스트레이터 스텝으로 phase 반영.

### PM 재교차검증 (봇 자기보고 불신 원칙)
- codex_run.sh grep → qa_verify 통합·QA_RC·git add -A 실재 ✅
- .venv/bin/pytest → pytest 9.1.1 실재 ✅
- **PM 직접 실행 (파이프 없이 정확한 exit code)**:
  - 통과 run_RjNxre(fizzbuzz) → **exit 0** ✅
  - 버그 run_FAIL_qCLm(add 결함) → **exit 1** ✅ (fail-closed 양방향 정확)
- → 백팀장 D1통합·D2종결·fail-closed 주장 전부 사실.

## ✅ 실무 검증 최종 수렴
DevLead·QA 실무 검증 완료. 파이프라인 L1·L2 자동화 + fail-closed 실증. **수장 승인만 나면 검증단계 GO.**

## 회신 2c — 브라이언(QA) 종결 회신 · fail-closed 독립 재현 [PM 확인]
- D1 통합 실물 확인(codex_run.sh 43~60행), pytest venv 확인, **fail-closed 양방향 QA 독립 재현**(폴백·pytest 두 경로 모두 exit 1) → PM 재현과 일치.
- QA 최종 판정: **L1·L2 자동화 게이트 합격. 검증단계 GO. QA 조건 전부 해소.**
- 잔여 = L3(교차검증)뿐 — 코딩=Codex→검수=Claude(다른벤더)+diff 의도일치. phase 반영, L3 합격기준은 QA가 작성 예정.
- 운영주의 2건: (1) pytest는 `--rootdir=<workdir>`로 격리(밖에서 돌리면 루트까지 수집해 느림, 실측) (2) 폴백 러너는 test_함수 직접호출 → fixture/parametrize는 pytest 경로 필요, 회귀 스위트는 표준 러너 고정.
- **안전경계 = 4겹(컨테이너 외부격리 + 격리 workdir + diff 게이트 + QA fail-closed) → 샌드박스 off 리스크 실증적 상쇄 → QA 승인 가능.**

## 🏁 회의 종결 (3팀장 전원 GO + PM 교차검증 완료)
- Design·QA·DevLead 전원 검증단계 GO. 실무 준비 100%.
- **유일한 미결 = 수장 결정 1건(아래).** 이후 phase 계획 확정 → 검증단계 착수.

## Phase 계획 제출·PM 검토 [백팀장 작성 / PM 승인]
- 문서: `/opt/data/projects/cc-plugin/phase_plan.md` (실물 확인 완료)
- Phase 0(실행기·안전경계, 실무완료·승인대기) → 1(파이프라인 종단검증) → 2(L3자동화+플러그인 골격) → 3(자율루프, 영상1 executor) → 4(일반화·배포+멀티에이전트).
- 회의 결론 정확 반영: 실행기 B+C · 4겹 안전경계 · L3 합격기준=QA · DX(엘레나 4대보강)는 Phase 2 · max4c/skills 검증1회용 · 운영주의5건.
- 역할분담: DevLead(파이프라인/골격/루프) · QA(루브릭/L3기준/위험명령정책) · Design(grill UX/DX) · PM(수장라우팅/게이트/소재지정).
- **PM 판정: 계획 승인. 블로커는 수장 안전경계 승인 1건뿐. 승인 시 Phase 1 소재 지정 후 착수.**

## 🚨 수장 결정 필요 1건 (백팀장 요청, PM 확인)
> 이 컨테이너에선 codex 내장 샌드박스를 물리적으로 켤 수 없음(bwrap namespace 불가). 따라서 codex는 `--dangerously-bypass-approvals-and-sandbox`로만 동작. 
> **"컨테이너 자체가 외부 격리(root없음/uid10000) + 일회용 격리 workdir + apply전 git diff 리뷰"를 안전 경계로 인정하고 진행할지 승인 요청.**
> 근거: codex 공식문서가 이 bypass 플래그를 "solely for externally sandboxed environments" 용도로 규정 — 우리 환경이 정확히 그 케이스. QA·DevLead 모두 이 경계로 충분하다는 데 동의.
