# DevLead 실측 — codex 실행 경계 + 다층 방어 구현 (수장 질문 답)

작성: 백팀장(DevLead) | 2026-07-06 | 수장 질문: "codex 코딩 시 claude 안전장치는 어떻게 되나"

## PM 배분 3문항 — 전부 실측(추측 아님)

### ① codex가 `-C $WD`로 cwd 고정돼도 workdir 밖을 쓰나 → 🔴 쓸 수 있다
- exec 경로: 절대경로 `/tmp/codex_escape_*.txt` **실제 생성 성공**.
- **`-C $WD`는 파일시스템 경계가 아니다.** diff 캡처 범위일 뿐, 프로세스 권한은 hermes 유저 전체.
- 이유: 이 컨테이너는 내장 bwrap 샌드박스를 못 켜므로(userns 비활성) danger-full-access로 도는데,
  그 순간 codex 프로세스는 hermes가 접근 가능한 모든 경로에 쓸 수 있다.

### ③ MCP 경로 vs exec 경로 안전 경계 같은가 → 동일
- MCP 경로도 `danger-full-access`로 `/tmp/codex_escape_mcp_*.txt` **실제 생성**. 둘 다 경계 없음.

### ② guard 훅을 codex에 거는 법 → 훅은 구조적으로 불가, 다층 방어로 대체
- PreToolUse 훅은 **claude Bash 툴에만** 발동. codex(exec/MCP)는 claude 툴이 아니라 안 걸림.
- 대신 3겹 방어를 codex_run.sh에 구현(브라이언 (a)(b)(c) + 내 ①③ 실측 결합):

## 구현한 다층 방어 (codex_run.sh, 전부 실측 통과)

**(a) 사전 차단** — 위임 프롬프트를 `scan_danger.py --strict`로 스캔, 위험 지시면 **exit 3 거부**.
  - 실측: "eval + subprocess.run(rm -rf)" 프롬프트 → 위임 전 차단 ✅

**(b) 실행 중 행위 감사 ★핵심** — `audit_codex_log.py` 신설. 브라이언 발견(rollout 로그) 구현.
  - codex는 `.codex_home/sessions/**/rollout-*.jsonl`에 실제 실행 행위를 남긴다:
    - `function_call` name=exec_command → 셸 명령(arguments.cmd)
    - `custom_tool_call` name=apply_patch → 파일 쓰기(`*** Add File: <path>`)
  - **둘 다 감사.** diff는 "무엇이 남았나", 로그는 "무엇을 했나".
  - escape 탐지: apply_patch/셸 리다이렉트 대상이 workdir 밖 절대경로면 차단(/tmp,/dev 제외).
  - 실측: codex가 apply_patch로 `design/INJECTED.txt`(workdir 밖) 쓰기 → **escape_patch 탐지, exit 4 차단** ✅
    (diff·QA는 통과했으나 로그 감사가 잡음 — 사후검사 구멍 메움 실증)

**(c) 격리 강화** — workdir 밖 쓰기는 -C로 못 막으니(①실측) (b)가 유일 사후 포착 수단.
  - 네트워크 차단은 컨테이너 레벨 조치 필요(수장 결정 항목).

## 중요: 측정기 정확성 교훈 (브라이언 계열)
처음엔 escape 탐지를 **파일시스템 스냅샷 diff**로 구현했다가 **오탐 발견**:
- 다른 봇(브라이언)이 동시에 `design/*.md`를 쓰면 그것까지 "codex escape"로 오판.
- 스냅샷은 "그 시간의 모든 변경"을 보지 "codex가 한 일"을 못 본다.
- → **rollout 로그 방식으로 교체.** 로그는 codex 자신의 행위만 담아 다른 프로세스와 안 섞임.
- 또 apply_patch 경로를 처음에 놓쳐 미탐 → 실측으로 잡아 커버 추가.
- 교훈: "측정기가 대상을, 대상만 측정하는가"를 실측으로 확인해야 한다.

## 정직한 한계
- (b) 로그 감사는 codex가 rollout에 기록하는 행위만 본다. codex가 로그를 우회하는 방법이 있다면
  못 잡음(현재까지 exec_command·apply_patch 두 경로가 codex의 파일쓰기 전부로 확인됨).
- 근본 해결은 **네트워크·파일시스템 격리(컨테이너/네임스페이스)**. 이 서버는 userns 비활성이라
  codex 내장 샌드박스가 불가 → 컨테이너 레벨 격리가 정공법. (b)는 그 전까지의 실질 방어선.

## 검증 상태
| 방어 | 실측 |
|------|------|
| (a) 위험 프롬프트 사전 차단 | ✅ exit 3 |
| (b) apply_patch escape 로그 감사 | ✅ exit 4 (diff·QA 통과해도 차단) |
| 정상 프롬프트 오탐 없음 | ✅ exit 0 (audit: 위험 없음) |
| -C 경계 아님 실증 | 🔴 exec·MCP 둘 다 escape 성공 |
