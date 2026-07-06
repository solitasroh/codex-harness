# DevLead 조사 — 훅/스캐너 이중관리 & 훅 회귀 강화 (브라이언 관찰 대응)

작성: 백팀장(DevLead) | 2026-07-05 | 대상: 브라이언 QA 관찰(훅 차단목록 vs 스캐너 패턴 이중관리)

## 조사 결론
브라이언 지적대로 두 목록은 **별도 소스**다. 실측으로 용도·겹침·동작을 확인함.

### 두 목록의 실체 (실측)
| | hooks/guard_dangerous.sh | bin/scan_danger.py (lib/danger_patterns.txt) |
|---|---|---|
| 대상 | **런타임 셸 명령**(Claude가 실행하려는 Bash) | **생성된 코드/diff**(Codex 산출물) |
| 시점 | PreToolUse(실행 직전) | 코딩 위임 후 검사 |
| 엔진 | bash grep -E (ERE) | Python re |
| 패턴 위치 | 스크립트에 하드코딩 | lib/ 데이터 파일(분리됨) |
| 고유 패턴 | fork bomb, mkfs, dd of=/dev/, chmod -R 777 / | eval/exec, os.system, subprocess 호출, secret 리터럴 |
| 겹치는 개념 | rm -rf, curl/wget\|sh | 동일 2개 |

→ **분리가 지금은 타당**(대상·시점·엔진이 다름). 다만 겹치는 2개념은 이중관리 위험 실재.
   브라이언 권고대로 Phase 2에서 단일 소스 수렴 검토(예: 공통 patterns 파일 + 엔진별 어댑터).

## 이번에 강화한 것 (fail-closed를 훅에도 확장)
브라이언이 스캐너에 적용한 fail-closed 검증 원칙을 **훅에도** 적용:
- `tests/test_guard_hook.py` 신규 — 위험5건 차단(exit2) + 정상3건 통과(exit0). **8/8 통과**(pytest+폴백).
- fail-closed 실증: 훅에서 rm_rf 패턴 임시 제거 → `test_block_rm_rf_root` **RED** → 복구 후 통과.
- 이제 훅 패턴을 건드려도 회귀가 잡는다(스캐너와 동급 방어).

## ⚠ 측정 도구 교훈 (중요 — QA와 공유)
이중관리 갭을 재보려고 만든 `tests/gap_probe.sh`가 **훅을 전부 "pass"로 오측정**했다.
- 원인: probe가 `printf '...' | bash hooks/...`로 훅을 조립 실행 → **외부 환경 보안 가드**가
  `파이프 to interpreter`/`파괴명령`을 감지해 개입, 훅 프로세스의 exit code를 오염(2가 아닌 값).
  probe는 `[ h -eq 2 ]`만 BLOCK으로 봐서 오염값을 전부 pass로 표기.
- 개별 재현(fixture 파일 stdin)으로는 훅이 **정상 차단(exit 2)** 확인. 스캐너도 정상.
- **결론: 훅/스캐너 둘 다 정상. gap_probe.sh는 신뢰 불가 측정기**였다.
- **교훈**: 위험명령을 셸에서 조립하면 환경 가드가 결과를 왜곡한다. 훅 테스트는 반드시
  **JSON fixture를 stdin 파일로 고정 입력**하고 exit code만 읽어야 재현 가능(test_guard_hook.py 방식).

## 검증 상태 갱신
| 항목 | 상태 |
|------|------|
| 위험패턴 스캐너 회귀(D-Q1/D-Q2) | ✅ 10/10 (기확인) |
| **훅 회귀(신규)** | ✅ 8/8 + fail-closed 실증 |
| 훅·스캐너 실동작 | ✅ 개별 fixture로 차단/통과 확인 |
| gap_probe.sh | ⚠ 오측정기로 판명 — 교훈 주석 처리, 회귀에서 제외 |

## 엘레나 HTML 반영 요청(브라이언 제안 수용)
두 목록의 **용도 차이 각주**: "훅=런타임 셸 명령 차단 / 스캐너=생성 코드 검사. 겹치는 개념(rm-rf,
curl|sh) 있으나 대상·시점이 달라 현재 분리 운용. Phase 2 단일소스 수렴 예정."
