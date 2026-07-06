# DevLead — FN5 수정: 층 계약 일치 + 발견된 FN5-C(이웃 run 오탐) 해결

작성: 백팀장(DevLead) | 2026-07-06 | 대상: 브라이언 QA FN5(codex_run이 opaque·escape를 !=0으로 뭉갬)

## FN5 = 내 정합성 실수 (수용)
audit_codex_log.py는 exit 2(escape·위험)와 3(opaque)을 의도적으로 구분하는데, codex_run.sh가
`ESCAPE_RC -ne 0` 하나로 뭉개 **opaque도 하드차단(exit 4)**했다. 두 층이 서로 다른 말을 함.
- 결과: workdir 내 정상 `python3 -c "open('x.py').read()"` 쓴 run이 통째로 죽음(fail-safe이나 사용성 악화).

## 수정 — exit code 계약 일치
codex_run.sh가 audit exit를 구분 처리:
- **2 (escape·위험)** → 하드차단 exit 4 (QA 무관, 사후검사 구멍 방어)
- **3 (opaque)** → 진행하되 `REVIEW_FLAG` 표시(자동 apply 금지·P1 사람검토). run은 안 죽임.
- **기타 non-zero** → 안전측 차단.
- dead code 정리: 이전 편집 잔재(orphan `ESCAPE_RC`/`OPAQUE_FLAG` 블록, exit 뒤 unreachable) 제거.

## 실측 중 발견 — FN5-C (이웃 run 오탐, 더 중요)
FN5 수정 후 테스트하다 **정상 프롬프트가 exit 4 차단**되는 오탐 발견. 원인 규명:
- codex_run은 `--session-after DELEGATE_START`로 로그를 감사하는데, 그 시간창에 **직전 run의
  escape 로그가 아직 걸려** 이번 run과 함께 감사됨. 측정기가 "이 run"이 아니라 "이 시각 이후 모든
  run"을 봄 → 이웃 run의 escape를 이번 run 탓으로 오판.
- **브라이언 교훈 재현**: 측정기가 대상(이 run)만 겨냥해야 하는데 이웃까지 봤다.
- **수정**: audit에 cwd 필터 추가. 각 run은 고유 workdir(mktemp)를 쓰므로, rollout의
  `session_meta.cwd == 이 run의 workdir`인 로그만 감사. 이웃 run과 물리적으로 분리.

## 실측 (전부 재현)
| 케이스 | 기대 | 결과 |
|--------|------|------|
| escape(apply_patch 절대경로 밖) | exit 4 차단 | ✅ exit 4 |
| opaque(python -c I/O, workdir 내) | 진행+리뷰플래그 | ✅ exit 0 + ⚠OPAQUE |
| 완전 정상(인터프리터 I/O 없음) | exit 0 무플래그 | ✅ exit 0 (FN5-C 해결) |
| 코드 회귀 스위트 | 33/33 | ✅ |
| bash 문법 | OK | ✅ |

## 교훈 (브라이언 소견 계승)
- "각 층(감사기 15/15)은 맞아도 층 사이 계약(exit code 의미)이 어긋나면 전체가 어긋난다" — 정확.
  단위 통과 ≠ 통합 정합성. exit code를 두 층이 같은 의미로 읽도록 계약을 명문화(주석+구분처리).
- 시간창 기반 로그 특정은 이웃 run 오염 위험 → cwd(workdir) 기반 특정이 정확. 측정 대상을
  "이 run"으로 못박음.
- 근본 결론 불변: 로그 감사=탐지 보조, 진짜 경계=P1 사람검토 + 컨테이너 격리(수장 최우선 결정).
