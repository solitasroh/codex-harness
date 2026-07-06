# 호스트 커널 설정 — codex 내장 샌드박스 활성화 (수장 2번 선택)

작성: 자비서(PM) | 2026-07-05 | 대상: 호스트 root 관리자(수장님)
목적: codex 내장 sandbox(workspace-write 등)를 살려서, codex가 격리 workdir 밖을 물리적으로 못 나가게.

## 진단 (PM 실측 확정)
codex 내장 샌드박스가 "No permissions to create namespace"로 실패하던 진짜 원인:
- `kernel.unprivileged_userns_clone = 1`  ← 이미 켜짐(문제 아님)
- `user.max_user_namespaces = 31610`      ← 이미 허용(문제 아님)
- **`kernel.apparmor_restrict_unprivileged_userns = 1`  ← ★진범** (Debian 13/Ubuntu 24.04 신규 보안 기본값)

이 AppArmor 제한이 non-root(uid 10000) 프로세스의 user namespace 생성을 막아 bwrap/codex sandbox가 전부 실패.
커널 sysctl은 호스트 전역 → 호스트에서 바꾸면 우리 컨테이너(자비서·codex)에도 즉시 반영.

## 수장님이 호스트에서 실행할 명령 (root)

### 즉시 적용 (재부팅 전까지)
```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
```

### 영구 적용 (재부팅 후에도 유지)
```bash
echo 'kernel.apparmor_restrict_unprivileged_userns=0' | sudo tee /etc/sysctl.d/99-codex-userns.conf
sudo sysctl --system
```

### 확인
```bash
cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns   # 0 이어야 함
```

## 보안 트레이드오프 (수장 판단 근거)
- 이 설정은 "비권한 사용자의 user namespace 생성"을 허용 → bwrap/podman/codex sandbox 등이 작동.
- Debian/Ubuntu가 기본 차단한 이유: userns를 악용한 로컬 권한상승(LPE) 공격 표면이 열림.
- **우리 맥락에서의 판단**: 이 호스트는 우리 통제하의 개발 서버이고, userns를 여는 대가로 codex를 진짜 격리(workdir 밖 물리 차단)할 수 있게 됨. 격리 이득 > LPE 위험(신뢰된 로컬 유저 모델). 단 다중 사용자 프로덕션이면 재고.
- 대안(더 보수적): 이 값을 건드리지 않고 "별도 격리 컨테이너를 --network none으로 띄우기"(1번)로 가도 됨. 2번은 편의성, 1번은 격리 순수성.

## 적용 후 (PM이 검증)
호스트에서 위 명령 실행 → PM이 `e2e/pm_verify_sandbox.sh` 재실행:
- workspace-write: workdir 안 쓰기 OK / 밖(/tmp) 쓰기 **차단** 확인
- read-only: 쓰기 전면 차단 확인
→ 통과하면 codex_run.sh의 `--dangerously-bypass-approvals-and-sandbox`를 `-s workspace-write`로 교체 가능.
  그러면 로그 감사(사후)에 의존하던 방어가 "실행 전 물리 격리"로 승격됨.

## ★ 적용 결과 (2026-07-05, PM 실측) — 1차 성공 + 2차 벽 발견
호스트에서 `apparmor_restrict_unprivileged_userns=0` 적용 확인됨(값 0 반영). 그러나 codex 샌드박스(userns) **여전히 불가**. 재진단:
| 계층 | 상태 |
|------|------|
| 호스트 sysctl apparmor 제한 | ✅ 0 (풀림 — 수장 조치 반영) |
| 호스트 unprivileged_userns_clone | ✅ 1 |
| user.max_user_namespaces | ✅ 31610 |
| **컨테이너 AppArmor 프로파일** | ❌ **docker-default (enforce)** |
| **컨테이너 seccomp** | ❌ **필터 활성(Seccomp:2)** |
| 컨테이너 capability | CapEff=0 (권한 전무) |
- **결론: 2차 벽 = 이 컨테이너를 띄운 docker run 옵션(seccomp+apparmor 프로파일)**. 커널 sysctl로 못 풂. 컨테이너 **재실행 설정** 문제.
- codex가 도는 이 컨테이너를 `--security-opt seccomp=unconfined --security-opt apparmor=unconfined`(또는 userns 허용 커스텀 프로파일)로 **재기동**해야 codex 내장 샌드박스가 살아남.

### ★ 재판단 — 여기서 방향 선택 (중요)
2차 벽을 뚫으려면 **이 컨테이너의 보안을 스스로 약화**(seccomp/apparmor unconfined)해야 함. 이건 역설적:
codex 내부 샌드박스를 켜려고 바깥 컨테이너 방어를 낮추는 꼴. **더 나은 대안**:
- **대안 A(권장)**: 이 컨테이너를 손대지 말고, 호스트에서 **codex 전용 별도 컨테이너**를 `--network none` + 읽기전용 마운트 + workdir만 rw로 띄워 거기에 코딩 위임. 격리를 "안에서 뚫기"가 아니라 "밖에서 새로 만들기". 순수·안전.
- **대안 B**: 이 컨테이너를 seccomp/apparmor unconfined로 재기동 → codex 내장 샌드박스 사용. 편하지만 컨테이너 자체 방어 약화.
- **현 상태 유지도 유효**: 이 컨테이너는 이미 CapEff=0 + seccomp + apparmor로 **강하게 격리**돼 있음. codex의 위험은 P1 사람검토 + 3겹 방어(33/33)로 잡는 중. 완전 자동화만 아니면 지금도 안전.
