# Codex 코딩 위임 부트스트랩 — Windows 판 (codex_bootstrap.sh 의 윈도우 등가물)
#
# 목적: 사용자가 이미 `codex login` 으로 로그인해 둔 기존 인증(auth.json)을
#       플러그인 로컬 CODEX_HOME 으로 복사해, 설치 직후 harness-run 선행체크가
#       위임을 차단하지 않게 한다("기존 codex 로그인 재사용" 방침, 수장 확정 2026-07-07).
#
# 배경/판단 근거 (baek, 2026-07-07):
#  - .mcp.json 은 `CODEX_HOME=${CLAUDE_PLUGIN_ROOT}\.codex_home` 을 읽는다. 개발(리눅스)
#    박스에선 plugin\.codex_home 이 repo 루트로 가는 심볼릭 링크라 우연히 동작하지만,
#    윈도우는 심링크가 기본 비활성 → 반드시 .mcp.json 이 읽는 실경로에 직접 심어야 한다.
#  - 샌드박스: 리눅스판은 sandbox_mode="danger-full-access" + approval_policy="never".
#    그 정당화 근거는 "컨테이너가 외부격리(uid≠0·root 없음)". 윈도우는 사용자 실기기라
#    그 근거가 사라지고, 리눅스의 실제 안전벽(일회용 workdir·diff·rollout 감사)은 전부
#    bash(codex_run.sh)에만 있어 윈도우 MCP 경로엔 격리층이 없다. 따라서 리눅스 config 를
#    그대로 복제하면 실기기에서 무승인·무샌드박스 자율실행이 된다 → 금지.
#    윈도우는 안전측: approval_policy="on-request" + sandbox_mode="workspace-write".
#    (사용자가 대화형으로 앞에 있으니 실행 전 승인 게이트가 자연스럽다.)
#  - 모델 미지정: 계정 기본(gpt-5.5) 사용. gpt-5-codex 명시 금지(ChatGPT계정 400).
#  - ⚠ 윈도우 실측 불가: 이 스크립트는 pwsh 없는 리눅스 컨테이너에서 작성됐다.
#    %USERPROFILE%\.codex 가 codex 기본 홈이라는 것은 codex 관례상 그렇다는 "추정"이며,
#    구문/경로/ACL 은 정적 리뷰만 거쳤다. 실제 윈도우에서 1회 검증 필요.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- 1) 플러그인 루트 확정 (심링크 의존 제거) ---
# .mcp.json 이 읽는 목적지는 항상 <플러그인 루트>\.codex_home.
# CLAUDE_PLUGIN_ROOT 가 주입돼 있으면 우선, 없으면 이 스크립트(bin\)의 상위로 역산.
if ($env:CLAUDE_PLUGIN_ROOT -and $env:CLAUDE_PLUGIN_ROOT.Trim()) {
    $PluginRoot = $env:CLAUDE_PLUGIN_ROOT
} else {
    # $PSScriptRoot = <PluginRoot>\bin  →  상위가 플러그인 루트
    $PluginRoot = Split-Path -Parent $PSScriptRoot
}
$DstHome = Join-Path $PluginRoot '.codex_home'
$DstAuth = Join-Path $DstHome 'auth.json'

# --- 2) 소스(기존 로그인) codex 홈 탐지: %CODEX_HOME% 우선 → 없으면 %USERPROFILE%\.codex ---
if ($env:CODEX_HOME -and $env:CODEX_HOME.Trim()) {
    $SrcHome = $env:CODEX_HOME
} else {
    $SrcHome = Join-Path $env:USERPROFILE '.codex'   # 추정: codex 기본 홈(실기기 미검증)
}
$SrcAuth = Join-Path $SrcHome 'auth.json'

Write-Host "[info] 플러그인 CODEX_HOME(목적지): $DstHome"
Write-Host "[info] 기존 로그인 소스: $SrcAuth"

# 소스==목적지 자기복사 방지 (사용자가 CODEX_HOME 을 플러그인 로컬로 export 해둔 경우)
if ([IO.Path]::GetFullPath($SrcAuth) -eq [IO.Path]::GetFullPath($DstAuth)) {
    Write-Warning "소스와 목적지가 동일합니다. 별도의 사용자 홈에서 'codex login' 후 재실행하세요."
}

# --- 3) 소스 auth 존재 확인 (fail-loud) ---
if (-not (Test-Path -LiteralPath $SrcAuth -PathType Leaf)) {
    Write-Error "FATAL: 기존 codex 로그인을 못 찾음: $SrcAuth`n먼저 'codex login' 으로 로그인한 뒤 다시 실행하세요."
    exit 1
}

# --- 4) 목적지 CODEX_HOME 준비 + auth 복사 ---
if (-not (Test-Path -LiteralPath $DstHome)) {
    New-Item -ItemType Directory -Path $DstHome -Force | Out-Null
}
Copy-Item -LiteralPath $SrcAuth -Destination $DstAuth -Force

# --- 5) 권한 축소 (chmod 600 등가) — best-effort ---
# 상속 제거 후 현재 사용자에게만 읽기 부여. 도메인 계정/특수 환경에서 icacls 가 실패할 수
# 있어 치명적으로 다루지 않는다(파일 복사는 이미 성공). 실패 시 수동 축소를 안내.
try {
    & icacls "$DstAuth" /inheritance:r /grant:r "${env:USERNAME}:R" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls exit $LASTEXITCODE" }
    Write-Host "[ok] auth.json 권한을 현재 사용자 전용(R)으로 축소"
} catch {
    Write-Warning "auth.json 권한 축소 실패($_). 토큰 보호를 위해 수동으로 접근 권한을 제한하세요."
}

# --- 6) config.toml 작성 (윈도우 안전측 정책) ---
# BOM 함정 방지: PS 5.1 의 -Encoding utf8 은 BOM 을 붙여 TOML 파서를 깨뜨릴 수 있으므로
# [IO.File]::WriteAllText + UTF8(BOM 없음)로 명시적으로 쓴다.
$ConfigToml = @"
# model 미지정: 계정 기본(gpt-5.5) 사용. gpt-5-codex 명시 금지(ChatGPT계정 400).
# 윈도우는 사용자 실기기 → 무승인·무샌드박스 자율실행 금지. 안전측 정책 사용.
approval_policy = "on-request"
sandbox_mode = "workspace-write"
skip_git_repo_check = true
"@
$ConfigPath = Join-Path $DstHome 'config.toml'
[IO.File]::WriteAllText($ConfigPath, $ConfigToml, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "[ok] CODEX_HOME=$DstHome"

# --- 7) 로그인 상태 확인 (best-effort — codex 가 PATH 에 없어도 복사 자체는 성공) ---
try {
    $env:CODEX_HOME = $DstHome
    & codex login status
} catch {
    Write-Warning "codex login status 확인 실패($_). codex 가 PATH 에 있는지 확인하세요."
}

Write-Host "[ok] bootstrap 완료. 이제 harness-run 선행체크가 통과합니다."
