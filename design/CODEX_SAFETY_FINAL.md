# codex 실행 안전 — 최종 종합 (수장 질문 완결)

작성: 자비서(PM) | 2026-07-05 | PM이 팀 회신을 전부 독립 재현·검증

## 여정 요약
수장 질문 "claude hook/skill이 codex로 이전될 때?" → 파고든 결과 **4겹 방어 + 1개 근본 결론**.

## 실측으로 확정된 사실 (PM 직접 재현)
1. **claude 안전장치(hook·skill)는 codex에 자동 적용 안 됨** — 별도 프로세스. codex 자체 정책도 OFF.
2. **codex는 workdir 밖을 실제로 건드릴 수 있음** — `-C $WD`는 경계 아님. `/tmp` 쓰기 로그로 실증.
3. **codex 네이티브 가드 존재(수장 아이디어 정답)** — execpolicy `.rules`로 `rm -rf /`·`mkfs`·`curl` 실행 전 forbidden/prompt. PM 실증. 단 `bash -lc` 래퍼 분해는 execpolicy check CLI에선 안 됨(런타임 경로 확정은 Phase 2).
4. **rollout 로그 감사로 실행 중 행위 포착 가능** — 백팀장 구현. PM 독립 재현: FN1~FN3(cp/tmp유출·상대탈출·printf) 4/4 잡힘.
5. **★ 근본 상한(FN4) — PM 재현 확정**: `python3 -c 'open(...).write(...)'` 인터프리터 내부 I/O는 셸에 경로가 안 드러나 정규식 감사가 **못 잡음**(exit 0). cp 등 셸 동사는 잡힘(exit 2). → 정규식 완벽 탐지는 **불가능**.

## 최종 방어 아키텍처 (다층, 어느 하나도 단독 완결 아님)
| 겹 | 방어 | 위상 | 검증 |
|----|------|------|------|
| 1 사전-네이티브 | execpolicy .rules (실행 전 forbidden) | 직접 명령 강력 | PM ✅ (래퍼분해 Phase2) |
| 2 사전-프롬프트 | 위임 프롬프트 scan_danger | 보조 | 백팀장 ✅ |
| 3 실행 중 | rollout 로그 감사 | **탐지 보조**(완전 차단 아님) | PM 4/4 ✅, FN4 상한 확인 |
| 4 사후 | git diff + qa_verify + 사람 승인 P1 | 결과물 게이트 | 기존 ✅ |
| **★ 근본** | **컨테이너 네트워크/FS 격리** | **유일한 물리적 완전 차단** | **수장 결정 대기** |

## 핵심 결론 (브라이언 규명 + PM 재현)
- 로그 감사·정규식은 훌륭한 **탐지 보조**지만 **완전한 차단막이 아니다**(FN4 실증). "감사 통과=안전"은 과신.
- 변형은 무한(perl -e, ruby, base64…) → 규칙 추가는 두더지잡기. **완벽 탐지를 목표로 삼지 않는다.**
- **진짜 안전 경계 = 사람 검토(P1) + 컨테이너 격리.** 격리가 있으면 감사 미탐과 무관하게 유출이 물리 차단됨.
- 이 프로젝트 관통 원칙(브라이언): **"측정기가 대상을 온전히 측정하는가"가 통과 여부보다 먼저.** gap_probe→골든셋→로그감사 전부 같은 계열.

## 회귀 자산 (전부 PM 실행 확인)
- scan_danger 10 + guard_hook 8 + audit_escape 11 = **29/29**
- execpolicy .rules + PM 검증 스크립트(pm_verify_execpolicy/compound/audit/fn4)

## 수장 결정 필요 (QA가 최우선으로 밀어올림)
**네트워크/FS 컨테이너 격리를 인프라로 도입할지.** 이 서버는 userns 비활성이라 codex 내장 샌드박스 불가 →
별도 격리 컨테이너(네트워크 차단 + FS 마운트 제한)에서 codex를 돌리는 방식. 이게 마지막 근본 경계.

### ★ 격리 실현 가능성 실측 (PM 직접, 2026-07-05)
이 컨테이너 **내부**에서 추가 격리는 **전부 불가** — 5가지 수단 실측:
| 수단 | 결과 |
|------|------|
| docker (중첩) | 불가 (소켓 없음) |
| bubblewrap | 미설치 |
| `unshare -n` (네트워크 ns) | Operation not permitted (uid 10000 비권한) |
| **codex 내장 sandbox** (read-only/workspace-write) | **bwrap 의존 → "No permissions to create namespace" 전부 실패** |
| iptables | 미설치 |
- 근본 원인: 커널 `unprivileged_userns_clone` 비활성 + non-root(uid 10000). 컨테이너 안에서 namespace 생성 권한 없음.
- **결론: 격리는 이 컨테이너 안이 아니라 "이 컨테이너를 띄운 호스트 레벨"에서만 가능.** 백팀장 진단 정확, PM 5수단 실측 확인.

### 호스트 레벨 격리 선택지 (수장 인프라 결정)
1. **별도 격리 컨테이너**: 호스트에서 codex 전용 컨테이너를 `--network none` + 읽기전용 마운트 + workdir만 rw로 띄우고, 우리 파이프라인이 거기에 코딩 위임. 가장 근본적.
2. **호스트 커널 설정**: `sysctl kernel.unprivileged_userns_clone=1` 활성화 → 현 컨테이너 안에서 bwrap/codex sandbox 작동 가능해짐. 가장 가벼우나 호스트 보안 정책 변경.
3. **네트워크만 차단**: codex 실행을 `--network none` 컨테이너 또는 방화벽 규칙으로 외부 접속만 막기(FS는 사후 감사+P1로). 절충안.
- 세 방식 다 **호스트 root 권한 필요** → 수장님(또는 호스트 관리자) 조치 사항. 현재 세션(컨테이너 내 uid 10000)에서는 실행 불가.

## Phase 2 등록
- execpolicy 플러그인 정식 편입 + 실제 codex exec에서 bash 래퍼 분해 확정
- FN4: 인터프리터 one-liner 플래그(완화), 근본은 격리
- rollout 감사 음성 골든 + execpolicy 골든
