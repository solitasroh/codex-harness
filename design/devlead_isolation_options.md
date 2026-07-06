# 수장 결정 근거 — 컨테이너 격리, 이 환경에서 무엇이 가능한가 (실측)

작성: 백팀장(DevLead) | 2026-07-06 | 목적: "격리하세요"가 아니라 "무엇이 되고 안 되는지"로 결정 근거 제공

## 왜 이 문서
QA·DevLead 릴레이의 최종 결론은 "컨테이너 격리가 근본 경계"로 수렴. 그런데 "격리 필요"만
반복하면 수장님이 결정을 못 함. **이 환경에서 실제로 가능한 격리가 무엇인지 실측**해 근거로 제공.

## 실측: 컨테이너 '내부'에서 가능한 격리 = 사실상 없음

| 방법 | 실측 결과 | 이유 |
|------|-----------|------|
| codex 내장 샌드박스(bwrap) | ❌ `No permissions to create a new namespace` | unprivileged userns 비활성 |
| codex `workspace-write`(네트워크 제한 포함) | ❌ 명령 자체 실패 | 위 bwrap에 의존 → all-or-nothing |
| `unshare -n`(네트워크 네임스페이스) | ❌ `Operation not permitted` | userns 비활성 + CAP 없음 |
| `setpriv --bounding-set`(권한 축소) | ❌ `Operation not permitted` | CAP_SETPCAP 없음 |
| `iptables`/`nft`(아웃바운드 차단) | ❌ 바이너리 없음 + CAP_NET_ADMIN 없음 | — |
| `sudo`/`firejail` | ❌ 없음 | root 권한 자체가 없음(uid 10000) |

- 현재 프로세스 capability: `CapEff=0`(유효 권한 전무). 격리를 걸 커널 권한이 아예 없음.
- **아웃바운드 네트워크는 OPEN**(8.8.8.8:53 연결 성공) → codex가 외부 유출 물리적으로 가능.

## 결론: 격리는 컨테이너 '바깥'에서만 가능

이 컨테이너 안에서는 코드/스크립트로 네트워크·FS 격리를 걸 방법이 **없다**(실측). codex를
`danger-full-access`로 돌릴 수밖에 없고(bwrap이 유일 대안인데 죽음), 3겹 방어(사전스캔+로그감사+
diff/QA)는 그 위에서의 **탐지·표면화**이지 **물리 차단**이 아니다.

## 수장님 결정 선택지 (호스트/오케스트레이터 레벨)

**A. 네트워크 차단 컨테이너에서 codex 실행 (권장)**
- codex 위임만 별도 컨테이너(`--network none` 또는 egress 화이트리스트)에서 실행.
- 효과: 감사기가 유출을 놓쳐도(FN4 잔여) 외부로 나갈 경로가 물리적으로 없음.
- 비용: codex 실행 경로를 별도 컨테이너로 분리하는 인프라 작업.

**B. 호스트에서 unprivileged userns 활성화**
- `sysctl kernel.unprivileged_userns_clone=1`(호스트 권한 필요).
- 효과: codex 내장 bwrap 샌드박스가 살아남 → codex 자체 read-only/workspace-write 격리 동작.
- 비용: 호스트 커널 설정 변경(보안 정책상 막아둔 것일 수 있음 — 확인 필요).

**C. 현행 유지 (3겹 탐지 + P1 사람검토)**
- 격리 없이 탐지·표면화 + apply 전 사람 검토로 운영.
- 리스크: FN4 계열(인터프리터 유출) 잔여 사각지대 존재. 무인 자율루프엔 부적합, 사람 개입 전제.

## 권고
- **무인 자율 실행을 목표로 한다면 A 필수.** 탐지는 사각지대가 남으므로(FN1~5 릴레이가 증명),
  물리 차단이 있어야 무인이 안전.
- **당분간 사람 검토(P1) 전제 반자동이면 C로 운영 가능**, 단 "로그 감사 통과=안전"으로 읽지 말 것.
- B는 호스트 정책 확인 후 가능하면 병행(codex 네이티브 격리 복원).

## 실측 재현 명령 (근거)
```
unshare -n echo x            # → Operation not permitted
grep CapEff /proc/self/status # → 0000000000000000
python3 -c "socket.create_connection(('8.8.8.8',53))"  # → 연결 성공(OPEN)
codex exec --sandbox workspace-write "..."  # → bwrap namespace 실패
```
