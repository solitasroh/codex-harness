# DevLead 검증 2차 — 샌드박스 실체 & 격리 규약 (실행 증명)

작성: 백팀장 | 근거: 이 컨테이너 실제 실행, 2026-07-05 | 브라이언 QA 회신에 대한 응답

## 브라이언 우려의 실체를 실행으로 규명함 (핵심 반전)

브라이언이 "샌드박스가 작동하는지 검증 안 됨"을 지적. 직접 canary 테스트로 확정:

| 테스트 | 명령 | 결과 | 의미 |
|--------|------|------|------|
| T1 read-only 쓰기 | `codex exec -s read-only` | canary 생성 안 됨. **but** bwrap: "No permissions to create a new namespace" | read-only가 막은 게 아니라 **bwrap이 죽어서** 셸 전부 실패 |
| T2 workspace-write 쓰기 | `codex exec -s workspace-write` | **동일 bwrap 실패, 쓰기 불가** | ⚠️ 코딩 위임이 이 모드로는 **물리적으로 불가능** |
| T3 sandbox 우회 | `--dangerously-bypass-approvals-and-sandbox` | **canary_bypass.txt 실제 생성 ✅** | bwrap 끄면 정상 동작 |
| T4 MCP danger-full-access | `codex mcp-server` tools/call | **canary_mcp.txt=MCPOK 실제 생성 ✅** | B(MCP)도 동일하게 우회 필요 |

**결정적 사실:** 이 컨테이너는 unprivileged user namespace 비활성 + root/sudo 없음.
codex 내장 샌드박스(bwrap)는 namespace를 못 만들어 **켜면 모든 셸 exec가 exit 1로 죽음**.
→ brian의 QA 권고 "workspace-write + on-request"는 **이 환경에서 작동 불가**. 켜는 순간 코딩 자체가 안 됨.
→ 코딩이 되려면 내장 샌드박스를 꺼야 함(`danger-full-access` / `--dangerously-bypass-*`).

## 그래서 위험한가? — 아니오. 브라이언 결론과 실은 일치

브라이언이 "실제 경계는 프로세스/파일시스템 격리로 세워야"라고 정확히 지적함. 그 격리는:
1. **컨테이너 자체** = externally-sandboxed 환경(uid 10000, root 없음, 호스트 격리). codex 문서가 `--dangerously-bypass-*`를 "solely for externally sandboxed environments"로 규정 — 우리가 바로 그 케이스.
2. **일회용 격리 workdir**(`runs/run_XXXX`) — 코드베이스 밖 mktemp 디렉토리에서만 실행. 코드베이스 경로 절대 격리.
3. **git baseline + apply 전 diff 리뷰** — 이게 진짜 승인 게이트. codex가 뭘 했든 diff로 전량 검토 후에만 반영.

즉 codex 내장 샌드박스를 끄는 대신, **우리가 상위 계층에 진짜 경계를 세운다.** 브라이언 ②의 "일회용 workdir·git diff 리뷰가 진짜 경계"와 정확히 같은 결론.

## 구현물 (실행 검증 완료)
- `scripts/codex_bootstrap.sh` — CODEX_HOME 표준화(auth 600 복사 + config). 실행 OK, `Logged in using ChatGPT`.
- `scripts/codex_run.sh` — 일회용 workdir + git baseline + codex 위임 + diff 캡처. 실행 OK.
  - 실증: "hello.py + pytest 생성" 위임 → runs/run_oVoxIE 에 2파일 실제 생성, diff 캡처됨.
  - **QA 루브릭 정당성 실증**: codex가 "pytest 실행" 자기시도 → "not found" 정직 보고. 자기보고 ≠ 검증.
  - **우리 L2 검증**: `python3 hello.py` → "hello from codex", returncode 0, stdout==expected **True**. PASS.

## 브라이언 앞 아키텍처 확답
- (가) **CODEX_HOME 표준화** → codex_bootstrap.sh로 스크립트화 완료.
- (나) **격리 workdir 규약** → codex_run.sh로 구현. mktemp 일회용 + git baseline + diff 게이트.
- 샌드박스 정책 정정: 이 환경에선 read-only/workspace-write가 **작동 불가**(bwrap 사망)라 무의미.
  실질 정책 = "내장 샌드박스 off + 격리 workdir + diff 리뷰 게이트". 이게 유일하게 동작하는 안전 모델.
- 실행기: **B(MCP) 주력**(멀티턴·감사가능·표준) + C(exec) 배치 보조. 둘 다 danger-full-access로 실동작 확인.

## 수장 결정 필요 지점
codex 내장 샌드박스를 끄는 것(`danger-full-access`)이 이 컨테이너에선 불가피함.
"컨테이너=외부격리 + 우리 격리 workdir/diff게이트"를 안전 경계로 인정하고 진행할지 승인 요망.
