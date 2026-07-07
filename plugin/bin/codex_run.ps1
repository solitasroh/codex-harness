# 격리 실행 래퍼 (A안: 사본 기반 위임) — Windows 판. codex_run.sh 의 등가물.
#
# 대상 repo 의 일회용 사본에서 Codex 에 코딩 위임하고 diff 를 캡처한다. 원본은 P1 사람 승인 전까지 불가침.
#
# 사용:
#   codex_run.ps1 -Prompt "<코딩 프롬프트>" [-Expect <substr>] [-Target <repo_or_dir>]
#     -Target 지정: 그 repo/폴더의 사본(git이면 worktree, 비-git이면 복제)에서 위임 → 기존 파일 수정 지원.
#     -Target 생략: 빈 폴더 baseline(그린필드) — 신규 파일 생성 전용(하위호환).
#
# 흐름: 사본생성 → (사본 안에서만)bypass 위임 → git diff 캡처 → rollout audit(escape) → QA →
#       [P1] 사람 diff 승인 안내 → (사람이 승인해야)원본 apply. ★자동 apply 절대 금지.
# exit: 0=QA통과(P1 승인 후 apply 가능) / 1=재작업 / 3=프롬프트 거부 / 4=escape·audit 차단.
#
# ★ 윈도우 안전 주의(설계문서 §1): 윈도우는 사용자 실기라 컨테이너 외벽이 없다. bypass 로 사본에서
#   돌지만 사본 밖 절대경로 쓰기를 물리 차단하는 건 실기에서만 확인 가능(doctor+audit 가 사후 확인).
#   그래서 이 스크립트는 apply 를 절대 자동화하지 않고 P1(사람 diff 승인)을 강제한다.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Prompt,
    [string]$Expect = "",
    [string]$Target = ""
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail($msg, $code=1) { Write-Error $msg; exit $code }

# ── 경로 확정 (리눅스 하드코딩 없음 — $PSScriptRoot/env 기반) ──
$ScriptDir = $PSScriptRoot
if ($env:PROJECT_ROOT) { $ProjectRoot = $env:PROJECT_ROOT }
elseif ($env:CLAUDE_PLUGIN_ROOT) { $ProjectRoot = $env:CLAUDE_PLUGIN_ROOT }
else { $ProjectRoot = Split-Path -Parent $ScriptDir }   # bin\ 의 상위 = 플러그인 루트
if ($env:CODEX_HOME) { $CodexHome = $env:CODEX_HOME } else { $CodexHome = Join-Path $ProjectRoot '.codex_home' }
$env:CODEX_HOME = $CodexHome

$AuthPath = Join-Path $CodexHome 'auth.json'
if (-not (Test-Path -LiteralPath $AuthPath)) { Fail "FATAL: CODEX_HOME 미초기화($CodexHome). 먼저 codex_bootstrap.ps1 실행." 1 }

# python 탐색 (가드 훅/스캐너 실행용): py → python → python3
$PyBin = $null
foreach ($cand in @('py','python','python3')) {
    $c = Get-Command $cand -ErrorAction SilentlyContinue
    if ($c) { $PyBin = $c.Source; break }
}

# ── 1) 프롬프트 사전 스캔 (가드 1선) ──
$scanner = Join-Path $ScriptDir 'scan_danger.py'
if ($PyBin -and (Test-Path -LiteralPath $scanner)) {
    $Prompt | & $PyBin $scanner --strict *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "🔴 위임 거부: 프롬프트에 위험 지시 포함 (scan_danger --strict)" -ForegroundColor Red
        $Prompt | & $PyBin $scanner --strict 2>&1 | Write-Host
        exit 3
    }
}

# ── 1-b) codex PreToolUse 훅 설치 (P2: 위험패턴 실행 전 차단). bootstrap.ps1 과 동일 로직. ──
$HookSrc = Join-Path $ProjectRoot '.codex\hooks\pre_tool_use_guard.py'
$PatSrc  = Join-Path $ProjectRoot 'lib\danger_patterns.txt'
$HookDir = Join-Path $CodexHome 'hooks'
if ((Test-Path -LiteralPath $HookSrc) -and (Test-Path -LiteralPath $PatSrc)) {
    if (-not (Test-Path -LiteralPath $HookDir)) { New-Item -ItemType Directory -Path $HookDir -Force | Out-Null }
    Copy-Item -LiteralPath $HookSrc -Destination (Join-Path $HookDir 'pre_tool_use_guard.py') -Force
    Copy-Item -LiteralPath $PatSrc  -Destination (Join-Path $HookDir 'danger_patterns.txt') -Force
    $hookPy = (Join-Path $HookDir 'pre_tool_use_guard.py')
    $pb = if ($PyBin) { $PyBin } else { 'python' }
    $pbJson = $pb.Replace('\','\\'); $hpJson = $hookPy.Replace('\','\\')
    $hooksJson = @"
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|apply_patch|Edit|Write",
        "hooks": [
          { "type": "command",
            "command": "\"$pbJson\" \"$hpJson\"",
            "timeout": 20,
            "statusMessage": "위험 명령 검사(codex 이식 가드)" }
        ]
      }
    ]
  }
}
"@
    [IO.File]::WriteAllText((Join-Path $CodexHome 'hooks.json'), $hooksJson, (New-Object System.Text.UTF8Encoding($false)))
}

# ── 2) 일회용 사본 생성 ──
$runsDir = Join-Path $ProjectRoot 'runs'
if (-not (Test-Path -LiteralPath $runsDir)) { New-Item -ItemType Directory -Path $runsDir -Force | Out-Null }
$WD = Join-Path $runsDir ("run_" + [Guid]::NewGuid().ToString('N').Substring(0,8))
$CopyMode = ""; $WtOrigin = ""

function Invoke-Git { param([string[]]$GitArgs) & git @GitArgs 2>&1 }

if ($Target) {
    $Target = (Resolve-Path -LiteralPath $Target -ErrorAction SilentlyContinue).Path
    if (-not $Target -or -not (Test-Path -LiteralPath $Target -PathType Container)) { Fail "FATAL: -Target 경로 없음/디렉터리 아님" 1 }
    $isGit = $false
    try { & git -C $Target rev-parse --is-inside-work-tree *> $null; if ($LASTEXITCODE -eq 0) { $isGit = $true } } catch {}
    if ($isGit) {
        $WtOrigin = (& git -C $Target rev-parse --show-toplevel).Trim()
        & git -C $WtOrigin worktree add -q --detach $WD HEAD *> $null
        if ($LASTEXITCODE -eq 0) {
            $CopyMode = "worktree"; Write-Host "[copy] git worktree: $WtOrigin -> $WD (HEAD detached)"
        } else {
            # worktree 실패 → 복제 폴백
            New-Item -ItemType Directory -Path $WD -Force | Out-Null
            Copy-Item -Path (Join-Path $Target '*') -Destination $WD -Recurse -Force
            $dotgit = Join-Path $WD '.git'; if (Test-Path -LiteralPath $dotgit) { Remove-Item -LiteralPath $dotgit -Recurse -Force }
            & git -C $WD init -q; & git -C $WD -c user.email=codex@local -c user.name=codex add -A
            & git -C $WD -c user.email=codex@local -c user.name=codex commit -q -m baseline *> $null
            $CopyMode = "clone"; Write-Host "[copy] worktree 실패 -> 복제 폴백: $Target -> $WD"
        }
    } else {
        New-Item -ItemType Directory -Path $WD -Force | Out-Null
        Copy-Item -Path (Join-Path $Target '*') -Destination $WD -Recurse -Force -ErrorAction SilentlyContinue
        & git -C $WD init -q
        & git -C $WD -c user.email=codex@local -c user.name=codex add -A
        & git -C $WD -c user.email=codex@local -c user.name=codex commit -q -m baseline --allow-empty *> $null
        $CopyMode = "clone"; Write-Host "[copy] 비-git 복제: $Target -> $WD"
    }
} else {
    New-Item -ItemType Directory -Path $WD -Force | Out-Null
    & git -C $WD init -q
    & git -C $WD -c user.email=codex@local -c user.name=codex commit -q --allow-empty -m baseline *> $null
    $CopyMode = "greenfield"; Write-Host "[workdir] 그린필드: $WD"
}

# ── 3) Codex 위임 (사본 안에서만 bypass) ──
$DelegateStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
# codex exec: 프롬프트는 인자로 전달(파이프 stdin 중복 금지). 경고 라인은 필터(무해).
& codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust -C $WD $Prompt 2>&1 |
    Where-Object { $_ -notmatch '^warning:|bubblewrap' } | Write-Host

# ── 3) 변경 캡처 → 리뷰 diff ──
& git -C $WD add -A
Write-Host "===== REVIEW DIFF (P1: 사람 승인 전 반드시 검토) ====="
& git -C $WD --no-pager diff --cached --stat
Write-Host "-----"
& git -C $WD --no-pager diff --cached
Write-Host "===== END DIFF ====="

# ── 3-b) rollout audit (escape 탐지). --workdir=사본. ──
$AuditRc = 0
$auditor = Join-Path $ScriptDir 'audit_codex_log.py'
if ($PyBin -and (Test-Path -LiteralPath $auditor)) {
    $env:CODEX_HOME = $CodexHome
    & $PyBin $auditor --session-after $DelegateStart --workdir $WD --delegated 2>&1 | Write-Host
    $AuditRc = $LASTEXITCODE
}

# ── 4) QA 검증 ──
$QaRc = 0
$qaPy = Join-Path $ScriptDir 'qa_verify.py'
if ($PyBin -and (Test-Path -LiteralPath $qaPy)) {
    & git -C $WD add -A
    & $PyBin $qaPy $WD $Expect 2>&1 | Write-Host
    $QaRc = $LASTEXITCODE
} else {
    Write-Host "⚠ qa_verify.py 없음/실행불가 — QA 검증 스킵"
    $QaRc = 1
}

Write-Host "[work] 작업물(사본): $WD"
if ($CopyMode -eq "worktree") {
    Write-Host "[apply] 승인 후: 원본=$WtOrigin 에 diff 적용. 정리: git -C `"$WtOrigin`" worktree remove --force `"$WD`""
}

# ── audit exit code 구분 처리(FN5) ──
$ReviewFlag = ""
if ($AuditRc -eq 2) {
    Write-Host "[차단] ESCAPE/위험 행위 탐지 → apply 절대 금지(사람 검토, exit 4)" -ForegroundColor Red
    exit 4
} elseif ($AuditRc -eq 3) {
    $ReviewFlag = "⚠ OPAQUE: 로그로 행위판정 불가한 실행 있음 → apply 전 P1 사람검토 필수(자동 apply 금지)"
} elseif ($AuditRc -ne 0) {
    Write-Host "[차단] 로그 감사 비정상 종료(rc=$AuditRc) → 안전측 차단(exit 4)" -ForegroundColor Red
    exit 4
}

# ── ★ P1 사람 승인 게이트 (자동 apply 절대 금지) ──
Write-Host "===== [P1] 사람 승인 필요 ====="
if ($QaRc -eq 0) {
    Write-Host "[done] QA 게이트 통과. ★ 위 diff 를 사람이 검토·승인해야만 원본에 apply. 이 스크립트는 apply 하지 않음." -ForegroundColor Green
    if ($ReviewFlag) { Write-Host $ReviewFlag -ForegroundColor Yellow }
} else {
    Write-Host "[재작업] QA 게이트 미통과(rc=$QaRc) → 증거 없이 apply 금지" -ForegroundColor Yellow
    if ($ReviewFlag) { Write-Host $ReviewFlag -ForegroundColor Yellow }
}
exit $QaRc
