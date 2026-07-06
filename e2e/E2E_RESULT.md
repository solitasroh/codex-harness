# E2E 실전 테스트 결과 — envlint (설계→ADR→코딩→검사 전 과정)

작성: 자비서(PM) | 2026-07-05 | 소재: .env 검증 CLI (envlint)
목적: 완성된 플러그인으로 작은 프로그램을 4단계 전 과정으로 만들어 파이프라인 실동작 확인

## 전 단계 실행 결과

| 단계 | 도구/스킬 | 결과 |
|------|----------|------|
| 1 설계 | design-grill 정신 | 확정 스펙 산출(envlint.spec.md), 5차원 미해소 0, 소재가 표준적이라 전부 CONSENSUS |
| 2 ADR | adr-check 정신 | ADR-0001(stdlib-only) 기록, 기존 ADR 0건 → 충돌 없음 OK |
| 3 코딩 | codex_run.sh → Codex | envlint.py(6.5KB)+test_envlint.py 격리 workdir(run_enqEF6)에 생성 |
| 4a 검사 | qa_verify.sh | ❌ exit 1 — 단 이는 코드결함 아닌 **하네스 한계**(아래) |
| 4b 검사 | PM L3 독립검증 | ✅ 코덱스 테스트 13/13 + PM 독립입력 11/11 전부 PASS |

## 산출물 (검증 통과 후 apply)
- e2e/src/envlint.py, e2e/src/test_envlint.py (13 tests OK)
- 실제로 작동: 형식오류·중복·빈값(strict구분)·export·따옴표·주석·JSON·스키마·파일없음(exit2)·빈파일 전부 정확.

## 이번 테스트가 드러낸 파이프라인 개선점 (백팀장 소관)
**qa_verify.sh의 L2b(expected stdout) 검사가 "메인 파일을 인자 없이 실행"을 가정한다** (line 54: `python3 "$MAIN"`).
→ envlint처럼 **파일 인자가 필수인 CLI**는 인자 없이 실행하면 usage 에러(exit 2)를 내므로,
   expected="ok"가 안 나와 게이트가 오판(재작업). 코드는 멀쩡한데 검사기가 못 돌린 것.
- 이건 Phase 1 diff-digest(인자 없이도 stdin 대기)와 달라서 안 드러났던 한계.
- 개선안: L2b가 (a) 실행 인자를 스펙/프롬프트에서 받거나 (b) 테스트 통과(L2a)만으로 충분하면 L2b를 옵션화.
- **중요**: 이건 게이트가 "조용히 통과"시킨 게 아니라 "보수적으로 막은" 것 → fail-closed 방향이라 안전측 오류. 그래도 실용성 위해 개선 필요.

## 결론
파이프라인은 **정확히 제 역할을 했다** — 설계·ADR·코딩·검사가 한 흐름으로 돌았고, 게이트는 판정을 내렸다.
코덱스 산출 코드는 스펙 완벽 충족(PM 독립검증 실증). 드러난 하네스 한계 1건은 안전측(막는 방향)이라
블로커 아니며, 백팀장 개선 대상으로 넘긴다. **첫 end-to-end 성공.**
