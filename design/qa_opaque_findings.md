# QA 검증: FN4 opaque 표면화 — 감사기 정확, 단 codex_run 통합 결함

작성: 브라이언(QA) | 2026-07-05 | 대상: 백팀장 opaque 표면화 (audit_codex_log.py + codex_run.sh)

---

## 결론: 감사기 exit 2/3 구분은 정확(재현). 단 **codex_run.sh가 그 구분을 뭉갬 — 통합 결함(FN5).** 방향은 fail-safe라 위험 아님, 그러나 설계 취지 훼손 + 정상 run 과잉 실패.

---

## 재현 1 — 감사기 단독 (exit code 구분, 백팀장 설계대로 작동)
| 케이스 | 결과 | 기대 |
|--------|------|------|
| opaque(`python3 -c` + open/write) | exit 3 (리뷰 플래그) ✅ | 3 |
| escape(`cp /etc/passwd /tmp`) | exit 2 (차단) ✅ | 2 |
| clean(`python3 -c 'print(2+2)'` I/O 없음) | exit 0 (오탐 방지) ✅ | 0 |

→ 감사기는 백팀장 설계대로 정확. opaque=exit3="차단 아닌 리뷰 플래그", escape=exit2="차단"을 **의도적으로 구분**함.

## 재현 2 — codex_run.sh 통합 (FN5 결함)
`codex_run.sh` L59~81 로직: `ESCAPE_RC=<감사기 exit>; if [[ $ESCAPE_RC -ne 0 ]]; then exit 4`
| 감사기 exit | codex_run 처리 |
|:-----------:|---------------|
| 0 | QA 단계 진행 ✅ |
| 2 (escape 차단) | exit 4 차단 ✅ |
| **3 (opaque 리뷰 플래그)** | **exit 4 차단** ❌ ← escape와 동일 취급 |

→ **감사기가 애써 나눈 "차단(2) vs 리뷰 플래그(3)"가 상위에서 `!= 0` 하나로 뭉개짐.** 백팀장이 opaque를 "차단 아님"으로 설계한 취지가 codex_run에서 사라짐.

## 왜 문제인가 (그러나 뉘앙스)
- opaque는 **의도적으로 보수적** — workdir 내 정상 `python3 -c "open('x.py').read()"`도 exit 3로 표면화(백팀장 명시 트레이드오프). 이건 "리뷰 필요"지 "차단"이 아니어야 함.
- 그런데 codex_run이 exit 4 하드 차단으로 처리 → **정상적인 인터프리터 I/O를 쓴 코딩 run마다 통째로 실패.** 백팀장이 우려한 "P1 검토 자주 뜸"이 "run 자체가 죽음"으로 악화.
- **단, 위험 방향은 아님(fail-safe)**: 과잉 차단이라 유출이 새는 게 아니라 정상이 막히는 쪽. 보안 사고 리스크 X, 사용성/설계정합성 문제. 심각도 **Minor~Major(사용성)**.

## QA 권고 (수정안)
codex_run.sh가 감사기 exit code를 **구분 처리**:
```bash
# escape(2) = 하드 차단(exit 4). opaque(3) = 리뷰 플래그(진행하되 P1 필수 표시).
if [[ $ESCAPE_RC -eq 2 ]]; then echo "[차단] ESCAPE"; exit 4
elif [[ $ESCAPE_RC -eq 3 ]]; then echo "[리뷰필요] OPAQUE 실행 — P1 사람검토 후 apply"; NEEDS_REVIEW=1
fi
```
- opaque는 "자동 GREEN 금지"가 목적이지 "run 실패"가 목적이 아님. 진행시키되 최종 상태를 "P1 검토 대기"로 표시(exit code나 마커로).
- 또는 명시적으로 "opaque=차단"이 팀 정책이면 그렇게 **문서화**하고 감사기 주석의 "차단 아님"을 고칠 것. 지금은 **코드 두 곳이 서로 다른 말을 함**(감사기="리뷰 플래그", codex_run="차단").

## QA 판정
- **감사기 자체: 통과.** exit 2/3/0 구분 정확, 오탐 방지 확인.
- **codex_run 통합: FN5 결함.** opaque(3)를 escape(2)와 동일 차단 처리 → 설계 취지 훼손 + 정상 run 과잉 실패. **fail-safe 방향이라 비긴급이나, 코드 정합성 위해 수정 권고.**
- 이번에도 교훈 일관: **각 층은 맞아도 층 사이 계약(exit code 의미)이 어긋나면 전체가 어긋난다.** 단위(감사기)는 15/15여도 통합(codex_run) 경계를 봐야 함.
- 근본 결론 불변: 로그 감사는 탐지 보조, **진짜 경계 = P1 사람검토 + 컨테이너 격리(수장 결정)**.
