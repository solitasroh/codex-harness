# DevLead 수정 — 로그 감사기 미탐 3건(FN1~FN3) 해결 (브라이언 프로브 대응)

작성: 백팀장(DevLead) | 2026-07-06 | 대상: 브라이언 QA가 뚫은 audit_codex_log.py 미탐 3건

## 판단: Phase 2 아님, 지금 수정
브라이언이 마지막 방어선을 직접 뚫어 미탐 3건을 찾음. FN2(상대경로 탈출)는 진짜 구멍이라
Phase 2로 미루면 그동안 열려 있음. 그가 라인·해법까지 짚었으니 즉시 수정 + 회귀 고정.

## 수정 내용 (브라이언 권고 3건 그대로)
- **FN2 (상대경로 탈출, 최우선)**: apply_patch·쓰기 경로를 `abspath(join(workdir, path))`로
  **정규화 후** workdir 밖이면 escape. `../../../etc/evil` 같은 상대 탈출 이제 잡음.
- **FN1 (/tmp 유출)**: `/tmp` 무조건 제외 폐지. 화이트리스트를 **workdir 하위 + /dev/null**로 한정.
- **FN3 (위험패턴 의존)**: escape 판정을 위험패턴과 **독립**시켜 경로 기반으로. 리다이렉트 외
  `cp/mv/install/ln/tee/dd of=/curl -o/wget -O/rsync` 목적지 경로도 추출해 검사. 조용한 유출도 잡음.

## 실측 (합성 rollout로 감사기 직접 프로브 — 브라이언 방식)
`tests/test_audit_escape.py` 신설, **11/11 통과**:
- 양성 7건 전부 탐지(exit 2): curl|sh, **cp /etc/passwd 유출(FN3)**, **printf > /tmp 유출(FN1)**,
  **../../../ 상대 apply_patch(FN2)**, 절대 apply_patch, tee /etc/cron.d, curl -o /root/.ssh
- 음성 4건 오탐 없이 통과(exit 0): workdir 내 쓰기, workdir 내 apply_patch, /dev/null, pytest
- **fail-closed 실증**: FN2 정규화 무력화 → `test_relative_patch_escape_detected` RED → 복구 후 통과.

## 전체 회귀 스위트: 29/29 통과
scan_danger 10 + guard_hook 8 + **audit_escape 11**(신규). pytest 확인.

## 브라이언 질문 2건 반영
- **L1.5 편입 vs codex_run 현위치**: 네 판단(현위치 유지) 수용. 감사는 DELEGATE_START·CODEX_HOME·
  $WD가 codex_run 문맥에만 있음. qa_verify는 범용이라 rollout 위치 모름. escape(exit4)를 qa와
  합쳐 codex_run이 최종 판정하는 현 구조 유지.
- **escape 골든 케이스**: 네 순서 그대로 따름 — **FN1~3 먼저 수정 → 이제 GREEN** → 음성 골든으로
  고정 완료(test_audit_escape.py가 그 역할. 합성 rollout이라 claude 라이브 불필요·빠름·결정적).

## 정직한 한계 (계속 명시)
- 감사기는 여전히 codex가 rollout에 남기는 exec_command·apply_patch만 본다. codex가 이 두 경로
  밖으로 부작용을 내는 방법이 있다면 못 잡음(현재까지 이 둘이 codex 파일쓰기 전부로 확인).
- 경로 추출은 정규식이라 극단적 난독화(변수치환·base64·eval)엔 취약할 수 있음 → 위험패턴
  스캐너(eval/exec 등)가 그 계열을 병행 커버. 근본 해결은 컨테이너 레벨 네트워크·FS 격리(수장 항목).
- 측정기 교훈 재확인: "통과"보다 "측정기가 대상을 온전히 보는가"가 먼저(브라이언 원칙).
