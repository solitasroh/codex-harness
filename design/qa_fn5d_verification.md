# QA 검증: FN5-D fail-closed 수정 — 재현 통과 + 설계판단 검토

작성: 브라이언(QA) | 2026-07-05 | 대상: 백팀장 FN5-D 수정 (audit_codex_log.py matched/unmatched 분류)

---

## 결론: FN5-D fail-open **해소 확인(실측)**. 백팀장 설계판단(불일치+위험=표면화 / 불일치+정상=무시) **QA 승인**.

---

## 재현 (실측)
| 시나리오 | 경로 | 결과 | 판정 |
|----------|------|------|------|
| unmatched(cwd≠wd)+opaque, 직접지정 | --rollout | exit 3 표면화 | ✅ |
| **unmatched+위험, --session-after 경유**(codex_run 실제 경로) | find_rollouts | **exit 3 표면화** | ✅ **fail-open 해소** |
| delegated + 로그 0건 | --delegated | exit 3 이상신호 | ✅ (#2 반영) |
| non-delegated + 로그 0건 | 기본 | exit 0 통과 | ✅ 오탐 없음 |

**핵심**: 이전 FN5-D에선 unmatched 로그가 **스킵→exit 0(fail-open)**이었다. 이제 **audit_one으로 전수 검사 후 위험/opaque 있으면 exit 3 표면화**(L206~209). find_rollouts 경유(실제 codex_run 경로)에서도 확인 → **버그 실제 수정됨.**

## codex_run 통합 확인
- L63: `--session-after --workdir --delegated` 전부 전달 확인. (내가 처음 `--delegated` 누락을 의심했으나, 코드 정독 결과 **정상 연결**. 실측으로 delegated 로그0건→exit3 확인. 계약 일치.)
- exit 계약: escape(2)→차단 / opaque·unmatched·로그0건(3)→REVIEW_FLAG 진행. 두 층 의미 일치.

## 백팀장 설계판단 검토 (요청받은 것)
**질문**: "unmatched+위험=표면화 / unmatched+정상=무시"가 미탐>오탐 관점에서 맞나?

**QA 답: 맞다. 승인.** 근거:
- fail-open의 본질은 "**위험을 못 보고 통과**"다. 이건 unmatched+위험을 **표면화**(exit 3)로 막았다 — 위험은 절대 조용히 안 지나감. 미탐 방지 목적 달성.
- unmatched+정상까지 매번 플래그하면 이웃 정상 run마다 opaque 떠서 FN5-C 오탐 부활 → P1 검토 피로 → **경보 피로로 진짜 경보를 놓치는 2차 미탐** 유발. 그래서 정상 unmatched 무시는 합리적.
- 즉 **"위험 신호가 있을 때만 불확실성을 표면화"** 가 미탐방지와 실용성의 옳은 균형. audit_one이 unmatched도 matched와 **동일 전수검사**(축소 안 함)하므로, "정상"이라는 판정 자체가 전체 규칙(escape+위험패턴+opaque) 통과를 의미 → 안전.

**단 QA 단서 1개**: "unmatched+정상=무시"의 안전성은 **audit_one의 탐지 범위에 갇힌다.** 즉 FN4 계열(정규식이 못 보는 인터프리터 유출)이 unmatched 로그에 있으면 "정상"으로 오판→무시 가능. 그러나 이건 FN5-D가 아니라 FN4(이미 opaque로 부분완화, 근본은 격리)의 잔여라 **여기서 추가 조치 불요**. FN5-D 자체는 해소.

## QA 판정
- **FN5-D: 통과.** fail-open 실제 해소, find_rollouts 실경로 확인, 오탐(FN5-C) 부활 없음.
- **백팀장 설계선(위험만 표면화): 승인.** 미탐방지 + 경보피로 회피 균형 맞음.
- **누적 확인**: FN1~FN5-D까지 로그 감사기의 fail-open/미탐/계약 결함을 순차 소거. 감사기는 이제 "애매하면 표면화" 원칙을 코드로 지킴.
- 근본 결론 불변: 로그 감사=탐지 보조(사각지대는 FN4 인터프리터 유출로 잔존), **진짜 경계=P1 사람검토 + 컨테이너 격리**. 감사기 강건화는 격리 도입 전까지의 방어선을 촘촘히 한 것.
