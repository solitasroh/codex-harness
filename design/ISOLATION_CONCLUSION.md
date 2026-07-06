# 회의 결론 — claude 안전장치 vs codex 코딩 (수장 질문 답)

작성: 자비서(PM) | 2026-07-05 | 근거: PM·백팀장·브라이언 실측 종합 (봇 보고를 PM이 재검증)

## 수장 질문
"claude 내 hook과 skill 또는 스크립트들이 codex 코딩으로 이전될 때 어떻게 동작할까?"

## 답 (실측 확정)

### 1. claude 안전장치는 codex에 자동 적용 안 됨
- 훅(PreToolUse Bash): claude 툴에만 발동 → codex는 claude 툴 아님 → **안 걸림**
- 스킬(SKILL.md): claude가 읽는 지침 → codex는 안 읽음 → **적용 안 됨**
- codex 자체 정책: `approval=never` + `sandbox=danger-full-access` → **codex 내부 안전장치도 OFF**
- 즉 claude/codex는 별도 프로세스, 안전벨트가 이전되지 않는다.

### 2. 통제는 "사전 차단"이 아니라 "격리 + 사후 검사"
격리 workdir → codex 자유 실행 → git diff 캡처 → qa_verify 게이트 → 사람 승인(P1) apply

### 3. ★ 이 모델의 근본 구멍 (수장이 정확히 짚은 지점) — 실증됨
- qa_verify·codex_run 둘 다 `git diff` 기반 → **측정 대상 = "diff에 남은 파일 변경"뿐**.
- 브라이언 실증: 임시파일 생성후삭제 / workdir 밖 읽기 / 외부 네트워크 → **3종 다 diff에 흔적 0**.
- PM 실증: e2e 로그에 codex가 실제로 `printf ... > /tmp/codex_escape_mcp_*.txt`로 **workdir 밖(/tmp)에 쓴 기록** 발견. → codex는 `-C $WD` cwd 고정에도 **절대경로로 workdir 밖 쓰기 가능**. diff엔 안 남음.
- 결론: 현 게이트는 "결과물 오염"은 잡지만 "실행 중 행위(파괴·유출·외부접속)"엔 **사각지대**.

### 4. ★ 구멍 메울 근거 — 이미 존재 (PM 실측 확인)
- codex는 실행마다 `.codex_home/sessions/**/rollout-*.jsonl`에 **`exec_command`로 모든 셸 명령 기록**.
- PM 검증(pm_verify_rollout.py): 로그 15개에서 실제 실행 명령 추출 성공 —
  `printf > /tmp/...`(워크스페이스 이탈), `pytest`, `python - <<PY` 등 전부 포착.
- **diff는 "무엇이 남았나", 로그는 "무엇을 했나". 로그 스캔이 실행 중 행위 사각지대를 메운다.**

## 확정 방어 설계 (3겹, Phase 2 필수)
- (a) **사전**: 위임 프롬프트를 codex 실행 전 스캔 — 위험 지시 거부.
- (b) **실행 중 감사 ★핵심**: qa_verify에 L1.5 추가 — 해당 run의 rollout 로그에서 exec_command 뽑아
      위험패턴(rm 밖경로/curl|sh/외부호스트) 대조. 이미 있는 데이터라 구현 비용 낮음.
- (c) **격리 강화**: 가능하면 네트워크 차단 실행. workdir 밖 절대경로 쓰기는 cwd 고정으로 못 막으니(실증) (b)가 유일한 사후 포착.

## 미결/등록
- 골든셋 하네스 케이스 강화(브라이언 메타검증): adr-check 스킬 자체는 PASS, 하네스는 "스킬 없이도 통과하는 명백 케이스" → Phase 2 케이스 강화.
- (b) rollout 로그 스캔을 qa_verify에 편입 = Phase 2 최우선.
- HTML 설계서 §5: 엘레나가 대비 2패널 + 격리흐름도 + 근본구멍 경고 반영. 방어책 (a)(b)(c) 결론을 자리표시에 채우면 완성.
