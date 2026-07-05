# DevLead(백팀장) 검토 — Codex 코딩 위임 실행기

작성: 백팀장 | 근거: 이 서버(baek 프로필) 실물 실행 검증, 2026-07-05
검증 방식: 말이 아니라 실제 실행. codex exec 1회 + MCP JSON-RPC initialize/tools/list/tools/call 전부 돌림.

## 실측 로그 (재현 가능)
- CODEX_HOME=/opt/data/projects/cc-plugin/.codex_home (auth.json 600 복사 + 자체 config.toml)
- C(exec): `codex exec --skip-git-repo-check --sandbox read-only "...PONG..."` → **PONG, EXIT=0**, model=gpt-5.5
- B(MCP): `codex mcp-server` stdio → initialize OK, tools/list=[codex, codex-reply], tools/call(codex) → **RESULT "PONG" + structuredContent{threadId,...}, EXIT=0**

## ① 최종 실행기: B(MCP) 주력 + C(exec) 보조
- **둘 다 실동작 확인.** 대립이 아니라 역할 분담.
- **B(MCP)를 주 백엔드로 권고.** 근거:
  - threadId 멀티턴이 네이티브 → 우리가 resume 세션관리를 안 짜도 됨(structuredContent.threadId 실측)
  - sandbox/approval-policy를 **호출 인자**로 턴마다 정밀 제어(read-only→workspace-write 단계적 상향 가능)
  - MCP 표준 → Claude가 표준 툴로 인식, `claude mcp add`로 바로 물림. 투명.
  - 우리 아키텍처가 "Claude 오케스트레이터가 Codex를 부린다"이므로 대화형 인터페이스가 맞음.
- **C(exec)는 헤드리스 자율 배치(fire-and-forget)에만 보조 사용.** 훅으로 TDD가드 붙일 때 유리. 상시 인터페이스로는 접착 스크립트 부담.
- A(비공식 플러그인)는 실행기로 채택 안 함. 결국 CLI 래퍼이고 블랙박스·유지보수 통제 불가.

## ② config.toml root:600 → CODEX_HOME이 유일한 답 (논쟁 종결)
- 실측: 실제 codex 홈은 `/opt/data/.codex`, config.toml이 **root:root 600** → hermes가 못 읽어 `codex login status`조차 permission denied.
- 컨테이너에 **root/sudo 없음(uid 10000 hermes)** → 권한조정은 물리적으로 불가.
- ∴ "CODEX_HOME vs 권한조정" 선택지 자체가 현실에서 소거됨. **CODEX_HOME 지정이 유일 경로.**
- 권고 표준: 프로젝트별 전용 CODEX_HOME(`.codex_home`)에 auth.json(600) 복사 + 우리 소유 config.toml. 오염된 전역 config를 안 건드려 더 깨끗함.

## ⚠ 추가로 발견한 함정 (반드시 반영)
- **`gpt-5-codex` 모델은 ChatGPT 계정에서 400 미지원.** config에 model 고정하면 codex가 조용히 실패.
  → **model 미지정**(계정 기본 gpt-5.5로 자동) 또는 지원 모델만 명시.
- git 저장소 밖 실행 시 `--skip-git-repo-check`(exec) / config `skip_git_repo_check=true`(MCP) 필요.
- bubblewrap이 PATH에 없어 번들 bwrap 사용(경고 뜨나 동작엔 지장 없음).

## ③ Claude→Codex 오케스트레이터 최소 골격
1. Claude Code = 오케스트레이터. grill-me로 설계 → ADR/용어집 대조 → 스펙 확정.
2. 등록: `CODEX_HOME=<proj>/.codex_home claude mcp add codex -- codex mcp-server` (env로 CODEX_HOME 주입).
3. 코딩 위임: Claude가 `codex` 툴 호출(prompt=확정스펙, sandbox=workspace-write, approval-policy=never) → threadId 수신.
4. 반복/수정: `codex-reply`에 threadId+후속 프롬프트로 멀티턴.
5. verify-before-done 게이트: 빌드/테스트 증거 없으면 "완료" 불가(QA 루브릭과 연동).

## 인프라 선결과제 (내가 처리 가능)
- [x] CODEX_HOME 우회 실증 완료 (경로 위 참조)
- [ ] 프로젝트 표준 부트스트랩 스크립트화(.codex_home 세팅 + claude mcp add) — 착수 대기
