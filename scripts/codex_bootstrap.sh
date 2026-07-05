#!/usr/bin/env bash
# Codex 코딩 위임 부트스트랩 — 이 컨테이너 전용
# 배경(실측 2026-07-05, baek):
#  - /opt/data/.codex/config.toml 이 root:600 → hermes가 못 읽어 codex 기동 실패.
#    컨테이너에 root/sudo 없음 → 권한조정 불가 → CODEX_HOME 우회가 유일 경로.
#  - codex 내장 샌드박스(bwrap)는 unprivileged userns 비활성 + root부재로 작동 불가.
#    read-only/workspace-write 로 켜면 모든 셸 exec가 "No permissions to create a new namespace"로 죽음.
#    → 코딩이 되려면 --dangerously-bypass-approvals-and-sandbox 로 내장 샌드박스를 꺼야 함.
#  - 이게 위험하지 않은 이유: 컨테이너 자체가 externally-sandboxed 환경(uid 10000, root 없음).
#    Codex 문서도 이 플래그를 "solely for externally sandboxed environments"로 규정.
#  - 실제 안전 경계는 우리가 세운다: 일회용 격리 workdir + git baseline + apply 전 git diff 리뷰.
#  - 모델: gpt-5-codex 는 ChatGPT 계정에서 400 미지원 → model 미지정(계정 기본 gpt-5.5).
set -euo pipefail

PROJECT_ROOT="${1:-/opt/data/projects/cc-plugin}"
export CODEX_HOME="$PROJECT_ROOT/.codex_home"
AUTH_SRC="/opt/data/.codex/auth.json"

# 1) CODEX_HOME 표준화
mkdir -p "$CODEX_HOME"
if [[ ! -r "$AUTH_SRC" ]]; then
  echo "FATAL: auth.json 읽기 불가: $AUTH_SRC" >&2; exit 1
fi
cp -f "$AUTH_SRC" "$CODEX_HOME/auth.json"
chmod 600 "$CODEX_HOME/auth.json"
cat > "$CODEX_HOME/config.toml" <<'EOF'
# model 미지정: 계정 기본(gpt-5.5) 사용. gpt-5-codex 명시 금지(ChatGPT계정 400).
approval_policy = "never"
sandbox_mode = "danger-full-access"   # 컨테이너가 외부격리이므로 내장 bwrap 비활성
skip_git_repo_check = true
EOF
echo "[ok] CODEX_HOME=$CODEX_HOME"
codex login status
echo "[ok] bootstrap 완료. 다음: codex_run.sh 로 격리 실행."
