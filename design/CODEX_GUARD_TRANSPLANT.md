# codex 가드 이식 — hook을 codex 네이티브로 (수장 아이디어 실현)

작성: 자비서(PM) | 2026-07-05 | 수장 지시: "hook이나 스킬을 codex에 이식하는 게 좋지 않아?"
결론: **실현·실측 완료.** claude 위험명령 가드를 codex PreToolUse 훅으로 이식 → codex가 실행 전 스스로 차단.

## 왜 이게 전환점인가
그동안 방어는 "codex가 한 뒤 로그로 잡기"(사후 감사) → FN1~FN5-D 끝없는 두더지잡기.
수장 아이디어로 방향 전환: **"codex가 하기 전에 막기"**(사전 차단). codex는 claude 훅 파일을
못 읽지만, codex에 **동등한 PreToolUse 훅** 기능이 있어 거기에 우리 가드를 심었다.
- 호스트 권한 불필요(격리 컨테이너와 달리 지금 바로 가능). 이미 적용·작동 확인.
- claude와 **같은 danger_patterns.txt 공유** → 한 곳 관리로 양쪽 적용.

## 산출물
- `plugin/.codex/hooks/pre_tool_use_guard.py` — stdin JSON(tool_input.command) 받아 위험패턴 대조,
  걸리면 `{"hookSpecificOutput":{"permissionDecision":"deny",...}}` 반환. fail-closed(파싱실패→deny).
  패턴 파일은 DANGER_PATTERNS 환경변수 또는 다중 후보로 로드(설치 위치 무관).
- `plugin/.codex/hooks.json` — PreToolUse matcher=Bash|apply_patch|Edit|Write
- `codex_run.sh` 편입: 매 실행마다 CODEX_HOME/hooks.json + 스크립트 동기화, codex exec에
  `--dangerously-bypass-hook-trust` 추가(자동 발동). 낡은 주석("훅은 codex에 못 검") 제거.
- `plugin/tests/test_codex_hook.py` — 회귀 10케이스(차단5+통과4+failclosed1)

## 실측 (PM 직접, 실제 codex 실행)
1. **훅 발동 확인**: codex에 무해작업 지시 → 출력에 `hook: PreToolUse` / `Completed`, hello.txt 정상 생성.
2. **★위험 차단 확인**: codex에 위험명령 유도 → `hook: PreToolUse Blocked`,
   codex_core 로그 `Command blocked by PreToolUse hook: 위험 패턴 'mkfs' 감지 → 실행 전 차단`.
   codex가 `command -v mkfs`로 우회 탐색해도 재차단. codex 자신도 "safety hook에 막혔다" 인정.
3. **정식 편입 통합**: 훅 제거 후 codex_run 실행 → 훅 자동 재설치 확인 + 위험 차단 + 정상 done.
4. **측정기 신뢰성(fail-closed 실효)**: 훅 deny 무력화 → 차단 테스트 5건 정확히 RED(4/10),
   복구 → 10/10. 빈 껍데기 아님 실증(브라이언 gap_probe 교훈 적용).

## 전체 회귀 48/48 (PM 실행 확인)
scan_danger 10 + guard_hook(claude) 8 + audit_escape 20 + **codex_hook 10(신규)**

## 방어 계층 재정리 (사전 차단이 1선으로 승격)
| 겹 | 방어 | 시점 | 상태 |
|----|------|------|------|
| **1 ★사전-훅** | **codex PreToolUse 가드(이식)** | **실행 직전 차단** | **PM 실측 ✅** |
| 2 사전-프롬프트 | scan_danger 위임 거부 | 위임 전 | ✅ |
| 3 실행 중 | rollout 로그 감사(FN1~5D 소거) | 실행 후 탐지·표면화 | ✅ 48/48 |
| 4 사후 | git diff + qa_verify + P1 사람승인 | 결과물 게이트 | ✅ |
| 근본 | 컨테이너 네트워크/FS 격리 | 물리 차단 | 수장 결정(호스트) |

## 한계 (정직)
- 문서 명시: PreToolUse는 "완전 강제경계"가 아닌 **가드레일** — 단순 셸만 가로챔, unified_exec/일부 경로 불완전.
- 즉 훅 이식은 사전 차단을 크게 강화하지만 **완벽 차단은 여전히 컨테이너 격리**뿐. 다층 방어의 강력한 1선이지 유일 방어가 아님.
- FN4(인터프리터 내부 유출)처럼 훅도 "명령 텍스트" 기반이라 못 보는 변형 존재 → 격리로 근본 해결.

## 남은 것
- (선택) codex Hooks 외 execpolicy .rules 병행(이미 실증) — 이중 사전 차단.
- (수장 결정) 컨테이너 격리 — 완전 자동화의 마지막 경계.
