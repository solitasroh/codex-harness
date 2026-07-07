#!/usr/bin/env bash
# QA 검증기 — 하위호환 shim. 실제 로직은 크로스플랫폼 qa_verify.py 로 이관됨(백팀장, 2026-07-07 스코프 C).
# 배경: 원안(.sh)은 find/grep/pytest·py_compile 을 bash 로 호출해 윈도우(.NET/xUnit)에서 무용이었다.
#   하네스 대상이 윈도우 주력이므로 검증 로직을 python3 단일 구현(qa_verify.py)으로 재작성하고,
#   이 .sh 는 기존 리눅스 호출자(codex_run.sh 등)를 안 깨뜨리기 위한 얇은 래퍼로만 남긴다.
# 계약(불변): exit 0=done / exit 1=재작업 / exit 2=사용법·환경 오류. 인자도 동일: <workdir> [expected].
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/qa_verify.py" "$@"
