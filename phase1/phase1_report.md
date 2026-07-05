# Phase 1 완료 보고서 — 파이프라인 종단 검증 성공

작성: 자비서(PM) | 2026-07-05 | 소재: diff-digest CLI | 판정: ✅ 전 과정 검증 통과

## 목표
작은 실제 아이디어 하나로 [설계 → ADR → 스펙 → Codex 코딩 → QA검증 → L3 교차검증]을
한 바퀴 돌려 우리 파이프라인이 실제로 작동하는지 눈으로 확인.

## 실행 결과 (전 단계 실측)

| 단계 | 내용 | 결과 |
|------|------|------|
| 1-1 설계 | grill-me 하이브리드 5차원 결정트리 | 전부 CONSENSUS 기본값 확정, 수장 개입 0 |
| 1-2 스펙 | 함수 시그니처 + AC1~AC5 | design_spec.md |
| 1-3 ADR | ADR-001~003 기록 | design_spec.md |
| 1-4 위임 | codex_run.sh → Codex 격리 workdir 코딩 | run_Oz3JuL/ 생성, 2파일 산출 |
| 1-5a QA(L1·L2) | qa_verify.sh 자동 | **5/5 PASS, exit 0** |
| 1-5b L3 | **PM 독립입력 교차검증** | **전항 PASS** |

## L3 교차검증 상세 (PM이 Codex 산출 테스트가 아닌 독립 입력으로 실동작 확인)
근거 스크립트: phase1/l3_verify.py | 입력: phase1/l3_test.diff (PM 작성)
- ✅ 파일별 통계 정확 (safe.py +2/-1, danger.py +3/-1)
- ✅ **추가된 eval 잡음 / 삭제된(-) eval 안 잡음** (스펙 핵심 로직 실증)
- ✅ os.system·rm -rf·SECRET 위험패턴 탐지
- ✅ --strict → exit 2 / --json 유효(json.loads 성공, files·risks 키)

## 핵심 성과
1. **"플러그인 vs MCP" 질문에 실전 답 완성**: 이번엔 C(codex exec) 경로로 위임 성공.
   B(MCP)는 Phase 2에서 오케스트레이터 붙일 때 주력으로.
2. **파이프라인 실동작 실증**: bootstrap→codex_run→qa_verify(fail-closed)→L3가 한 흐름으로 동작.
3. **봇 자기보고 불신 원칙 준수**: Codex "완료" + QA "5/5"를 그대로 안 믿고, PM이 독립 입력으로 재검증.
4. **첫 dogfooding 산출물**: diff-digest 자체가 우리 L3 diff리뷰를 보조하는 도구 → Phase 2 편입 후보.

## 관측된 실무 이슈 (다음 phase 반영)
- 인라인 `python -c`가 매 실행 승인 게이트에 걸림 → **검증 로직은 스크립트 파일로**(메모리 기록과 동일 패턴). l3_verify.py로 처리.
- heredoc에 diff 원문 넣으면 깨짐 → write_file로 입력 준비.
- `/tmp`에 시크릿 패턴(API_KEY=) 포함 파일 쓰기 차단됨 → 프로젝트 내부 경로 + 플레이스홀더 사용.

## 다음 단계 제안 (Phase 2)
- L3 교차검증을 **오케스트레이터 자동 스텝**으로 (지금은 PM 수동). 합격기준=브라이언(QA).
- diff-digest를 플러그인 bin/에 편입 + `.claude-plugin` 골격 시작.
- 실행기를 B(MCP)로 전환해 Claude 오케스트레이터가 codex 툴을 직접 호출.
