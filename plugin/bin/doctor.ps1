# codex-harness 자가진단 (doctor) — Windows 판
#
# 목적: 실사용자가 플러그인 설치 직후 이 스크립트 1회 실행 → 자기 윈도우 실기에서
#       핸드오프 체크리스트 6개가 실제로 통과하는지 자동 판정.
#
# 설계 원칙(팀 기준):
#  - 각 항목: PASS / FAIL / SKIP + 한 줄 근거. "존재 확인"이 아니라 "실제로 돌려서" 판정.
#    (3·4·5 는 반드시 실동작 — MCP tools/call 찔러보기 / xUnit self-test / 훅 fixture)
#  - SKIP(실기에만 있는 조건 불충족, 예: dotnet 미설치)은 FAIL 과 구분. 사용자가 헷갈리지 않게.
#  - fail-closed: 판정 불가는 안전측(FAIL 또는 명확한 SKIP). 마지막에 요약 한 줄 + 종료코드.
#  - ★ 3번 함정(스킬 명시): claude mcp list 의 "✔ Connected" 는 프로세스만 떴다는 뜻이고
#    auth 깨져도 초록으로 뜬다(phantom connection). 그래서 실제 tools/call(codex) 1건이
#    structuredContent.threadId 를 돌려주는지까지 찔러봐야 진짜 통과. Connected 만 보고 PASS 금지.
#
# 실증 상태(baek, 2026-07-07):
#  - 뼈대·판정 로직·JSON-RPC PONG probe(3)·xUnit self-test(4)·훅 fixture(5) 로직은
#    리눅스(pwsh 7.4.6 + dotnet SDK 로컬설치, ICU 없어 INVARIANT=1)에서 실제 실행해 검증.
#  - 3·6 의 "진짜 윈도우 동작"과 icacls·py런처 실기 케이스는 이 스크립트가 실사용자 PC에서
#    대신 확인하는 구조라 개발 박스에서 미리 못 봄 → "실사용자가 돌리면 검증됨"으로 설계.

Set-StrictMode -Version Latest
# 항목 하나가 죽어도 전체 진단은 끝까지 돌려야 하므로 Stop 대신 Continue.
$ErrorActionPreference = 'Continue'

# ── 결과 집계 ──
$script:Results = @()   # @{ n=번호; name=제목; status='PASS'|'FAIL'|'SKIP'; reason='근거' }

function Add-Result {
    param([int]$N, [string]$Name, [ValidateSet('PASS','FAIL','SKIP')][string]$Status, [string]$Reason)
    $script:Results += [pscustomobject]@{ N = $N; Name = $Name; Status = $Status; Reason = $Reason }
    $color = switch ($Status) { 'PASS' { 'Green' } 'FAIL' { 'Red' } 'SKIP' { 'Yellow' } }
    $tag = $Status.PadRight(4)
    Write-Host ("  [{0}] {1}. {2} — {3}" -f $tag, $N, $Name, $Reason) -ForegroundColor $color
}

function Test-CommandExists {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

# ── 플러그인 루트 확정 (bootstrap.ps1 과 동일 규칙: CLAUDE_PLUGIN_ROOT 우선, 없으면 bin\ 상위) ──
if ($env:CLAUDE_PLUGIN_ROOT -and $env:CLAUDE_PLUGIN_ROOT.Trim()) {
    $PluginRoot = $env:CLAUDE_PLUGIN_ROOT
} else {
    $PluginRoot = Split-Path -Parent $PSScriptRoot   # $PSScriptRoot=<root>\bin
}
$CodexHome = Join-Path $PluginRoot '.codex_home'
$AuthPath  = Join-Path $CodexHome 'auth.json'

Write-Host ""
Write-Host "===== codex-harness doctor (Windows) =====" -ForegroundColor Cyan
Write-Host ("플러그인 루트: {0}" -f $PluginRoot)
Write-Host ("CODEX_HOME   : {0}" -f $CodexHome)
Write-Host ""

# python 실행기 탐색 (여러 항목이 재사용): py → python → python3
$script:PyBin = $null
foreach ($cand in @('py','python','python3')) {
    $c = Get-Command $cand -ErrorAction SilentlyContinue
    if ($c) { $script:PyBin = $c.Source; break }
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. codex CLI 존재 + PATH
# ─────────────────────────────────────────────────────────────────────────────
if (Test-CommandExists 'codex') {
    $ver = (& codex --version 2>&1 | Select-Object -First 1)
    Add-Result 1 'codex CLI' 'PASS' ("PATH 에서 발견: {0}" -f $ver)
} else {
    Add-Result 1 'codex CLI' 'FAIL' "codex 가 PATH 에 없음 — Codex CLI 설치 후 PATH 등록 필요"
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. CODEX_HOME\auth.json 존재·읽기 가능 (harness-run 선행체크와 동일 기준)
# ─────────────────────────────────────────────────────────────────────────────
$authOk = $false
if (Test-Path -LiteralPath $AuthPath -PathType Leaf) {
    try {
        $null = [IO.File]::ReadAllText($AuthPath)   # 실제 읽기까지 확인(권한 문제 포착)
        $sz = (Get-Item -LiteralPath $AuthPath).Length
        if ($sz -gt 0) {
            $authOk = $true
            Add-Result 2 'auth.json' 'PASS' ("존재·읽기 가능 ({0} bytes): {1}" -f $sz, $AuthPath)
        } else {
            Add-Result 2 'auth.json' 'FAIL' ("파일은 있으나 비어 있음 → bin\codex_bootstrap.ps1 재실행 필요")
        }
    } catch {
        Add-Result 2 'auth.json' 'FAIL' ("존재하나 읽기 실패({0}) — 권한 확인" -f $_.Exception.Message)
    }
} else {
    Add-Result 2 'auth.json' 'FAIL' ("없음: {0} → 먼저 bin\codex_bootstrap.ps1 실행" -f $AuthPath)
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. MCP tools/call 실동작 (★ Connected 가짜통과 방지 — 실제 코딩 위임 1건 찔러보기)
#    initialize → notifications/initialized → tools/call(codex, prompt=PONG)
#    → structuredContent.threadId 가 나오면 진짜 통과. (스킬 references/mcp-server 검증본)
# ─────────────────────────────────────────────────────────────────────────────
if (-not (Test-CommandExists 'codex')) {
    Add-Result 3 'MCP tools/call' 'SKIP' "codex CLI 없어 probe 불가(1번 먼저 해결)"
} elseif (-not $authOk) {
    Add-Result 3 'MCP tools/call' 'SKIP' "auth.json 미비로 probe 불가(2번 먼저 해결)"
} else {
    try {
        # 격리 git workdir (codex 는 git repo 밖이면 abort — skip_git_repo_check 도 병행)
        $wd = Join-Path ([IO.Path]::GetTempPath()) ("doctor_mcp_" + [Guid]::NewGuid().ToString('N').Substring(0,8))
        New-Item -ItemType Directory -Path $wd -Force | Out-Null
        try { & git -C $wd init -q 2>&1 | Out-Null; & git -C $wd commit -q --allow-empty -m baseline 2>&1 | Out-Null } catch {}

        # cwd 를 JSON 에 안전히 넣기 위해 백슬래시 이스케이프
        $wdJson = $wd.Replace('\','\\')
        $req = @(
          '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"doctor","version":"1.0"}}}',
          '{"jsonrpc":"2.0","method":"notifications/initialized"}',
          ('{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"codex","arguments":{"prompt":"Reply with exactly the single word PONG and nothing else.","sandbox":"workspace-write","approval-policy":"never","cwd":"' + $wdJson + '","config":{"skip_git_repo_check":true}}}}')
        ) -join "`n"

        # codex mcp-server 를 stdin 으로 구동. CODEX_HOME 을 이 프로세스에 주입.
        $env:CODEX_HOME = $CodexHome
        # 타임아웃 가드: mcp-server 는 stdio 로 계속 떠 있으므로, 응답 받으면 stdin EOF 로 종료.
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = (Get-Command codex).Source
        $psi.Arguments = 'mcp-server'
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.EnvironmentVariables['CODEX_HOME'] = $CodexHome
        $proc = [System.Diagnostics.Process]::Start($psi)
        $proc.StandardInput.Write($req + "`n")
        $proc.StandardInput.Close()
        # 최대 180초 대기(첫 모델 호출은 느릴 수 있음)
        $done = $proc.WaitForExit(180000)
        if (-not $done) { try { $proc.Kill() } catch {}; }
        $out = $proc.StandardOutput.ReadToEnd()

        Remove-Item -LiteralPath $wd -Recurse -Force -ErrorAction SilentlyContinue

        # ★ 판정 강화(baek 실측 2026-07-07): threadId 존재만으론 부족 — 가짜/만료 auth 도
        #   tools/call 응답에 structuredContent.threadId 를 담아 보낸다(isError=True 인데도!).
        #   실측: 401 Unauthorized 인 경우 result.isError=True, content[0].text 에 "401 Unauthorized".
        #   그래서 id=2 응답을 JSON 파싱해 (a)isError!=true (b)content 에 401/Unauthorized 없음 까지 봐야
        #   진짜 통과. threadId 정규식만 보면 phantom connection 의 한 단계 깊은 함정에 걸린다.
        $id2 = $null
        foreach ($ln in ($out -split "`n")) {
            $t = $ln.Trim()
            if (-not $t.StartsWith('{')) { continue }
            try { $obj = $t | ConvertFrom-Json -ErrorAction Stop } catch { continue }
            if ($obj.PSObject.Properties.Name -contains 'id' -and $obj.id -eq 2) { $id2 = $obj; break }
        }

        $threadId = $null; $isError = $null; $contentText = ''
        if ($id2) {
            if ($id2.PSObject.Properties.Name -contains 'error') {
                # JSON-RPC 레벨 에러(프로토콜 실패)
                $isError = $true
                $contentText = ($id2.error | ConvertTo-Json -Compress -Depth 5)
            } elseif ($id2.result) {
                $r = $id2.result
                if ($r.PSObject.Properties.Name -contains 'isError') { $isError = [bool]$r.isError }
                if ($r.structuredContent -and $r.structuredContent.threadId) { $threadId = $r.structuredContent.threadId }
                if ($r.content) {
                    try { $contentText = (($r.content | ForEach-Object { $_.text }) -join ' ') } catch { $contentText = ($r.content | ConvertTo-Json -Compress -Depth 5) }
                }
            }
        }
        $authBroken = ($contentText -match '401|Unauthorized|Missing bearer|invalid_?api_?key|expired')

        if ($threadId -and ($isError -ne $true) -and (-not $authBroken)) {
            Add-Result 3 'MCP tools/call' 'PASS' ("실제 tools/call(codex) 성공 — threadId={0}, isError=false. 진짜 위임 성공(Connected 껍데기 아님)" -f $threadId)
        } elseif ($authBroken) {
            $snip = ($contentText -replace '\s+',' '); if ($snip.Length -gt 140) { $snip = $snip.Substring(0,140) }
            Add-Result 3 'MCP tools/call' 'FAIL' ("인증 실패 — tools/call 이 threadId 는 줬지만 isError=True/401(phantom). auth.json 만료·잘못됨 → codex login 후 bin\codex_bootstrap.ps1. 응답: {0}" -f $snip)
        } elseif ($id2 -and $isError -eq $true) {
            $snip = ($contentText -replace '\s+',' '); if ($snip.Length -gt 140) { $snip = $snip.Substring(0,140) }
            if ($contentText -match 'not supported when using Codex with a ChatGPT account') {
                Add-Result 3 'MCP tools/call' 'FAIL' "모델 미지원(gpt-5-codex ChatGPT계정 400) — config.toml 의 model 라인 제거"
            } else {
                Add-Result 3 'MCP tools/call' 'FAIL' ("tools/call isError=True — 위임 실패. 응답: {0}" -f $snip)
            }
        } elseif (-not $done) {
            Add-Result 3 'MCP tools/call' 'FAIL' "180초 내 응답 없음 — 네트워크/인증/모델 확인(phantom connection 의심)"
        } else {
            $snippet = ($out -replace '\s+',' '); if ($snippet.Length -gt 160) { $snippet = $snippet.Substring(0,160) }
            Add-Result 3 'MCP tools/call' 'FAIL' ("id=2 응답 파싱 실패/threadId 없음 — tools/call 실패. 응답: {0}" -f $snippet)
        }
    } catch {
        Add-Result 3 'MCP tools/call' 'FAIL' ("probe 예외: {0}" -f $_.Exception.Message)
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. dotnet 존재 + qa_verify.py 가 xUnit 실제로 돌리는지 (임시 xUnit self-test 1회)
# ─────────────────────────────────────────────────────────────────────────────
$qaPy = Join-Path $PluginRoot 'bin\qa_verify.py'
if (-not (Test-CommandExists 'dotnet')) {
    Add-Result 4 '.NET 게이트' 'SKIP' "dotnet 이 PATH 에 없음 — .NET 프로젝트를 쓸 계획이면 SDK 설치 필요(안 쓰면 무시 가능)"
} elseif (-not $script:PyBin) {
    Add-Result 4 '.NET 게이트' 'FAIL' "python 을 못 찾음(py/python/python3) — qa_verify.py 실행 불가"
} elseif (-not (Test-Path -LiteralPath $qaPy)) {
    Add-Result 4 '.NET 게이트' 'FAIL' ("qa_verify.py 없음: {0} — 플러그인 트리 무결성 확인" -f $qaPy)
} else {
    try {
        $verInfo = (& dotnet --version 2>&1 | Select-Object -First 1)
        # 임시 xUnit 프로젝트 scaffold → qa_verify.py 로 검사 → exit 0 이어야 PASS
        $tp = Join-Path ([IO.Path]::GetTempPath()) ("doctor_xunit_" + [Guid]::NewGuid().ToString('N').Substring(0,8))
        New-Item -ItemType Directory -Path $tp -Force | Out-Null
        Push-Location $tp
        try {
            & dotnet new xunit -n DoctorSelfTest 2>&1 | Out-Null
            $projDir = Join-Path $tp 'DoctorSelfTest'
            if (-not (Test-Path -LiteralPath $projDir)) {
                Add-Result 4 '.NET 게이트' 'FAIL' "dotnet new xunit 실패 — SDK 는 있으나 템플릿/복원 문제"
            } else {
                & $script:PyBin $qaPy $projDir 2>&1 | Out-Null
                $rc = $LASTEXITCODE
                if ($rc -eq 0) {
                    Add-Result 4 '.NET 게이트' 'PASS' ("dotnet {0} + qa_verify.py 가 임시 xUnit 을 실제로 빌드·테스트해 exit 0" -f $verInfo)
                } else {
                    Add-Result 4 '.NET 게이트' 'FAIL' ("qa_verify.py 가 정상 xUnit 에 exit {0} 반환 — 러너감지/dotnet test 경로 점검" -f $rc)
                }
            }
        } finally {
            Pop-Location
            Remove-Item -LiteralPath $tp -Recurse -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Add-Result 4 '.NET 게이트' 'FAIL' ("self-test 예외: {0}" -f $_.Exception.Message)
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. 가드훅 패턴 자가탐색 (윈도우에서 패턴0개로 안 떨어지고 위험명령 실제 차단)
#    fixture 2건: 안전명령 → allow(무출력), 위험명령(rm -rf /) → deny. env 제거로 자가탐색만 시험.
# ─────────────────────────────────────────────────────────────────────────────
$hookPath = Join-Path $CodexHome 'hooks\pre_tool_use_guard.py'
if (-not $script:PyBin) {
    Add-Result 5 '가드훅 자가탐색' 'FAIL' "python 을 못 찾음 — 훅 실행 불가"
} elseif (-not (Test-Path -LiteralPath $hookPath)) {
    Add-Result 5 '가드훅 자가탐색' 'FAIL' ("훅 미설치: {0} → bin\codex_bootstrap.ps1 재실행(훅+패턴 설치)" -f $hookPath)
} else {
    try {
        # env(DANGER_PATTERNS/CLAUDE_PLUGIN_ROOT) 제거 = 자가탐색만으로 도는지 시험
        $safeJson   = '{"tool_name":"Bash","tool_input":{"command":"echo hello safe"}}'
        $dangerJson = '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}'

        function Invoke-Hook {
            param([string]$Payload)
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $script:PyBin
            $psi.Arguments = ('"{0}"' -f $hookPath)
            $psi.RedirectStandardInput = $true
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError = $true
            $psi.UseShellExecute = $false
            # 자가탐색 시험: 이 두 env 를 자식에서 비운다
            $psi.EnvironmentVariables['DANGER_PATTERNS'] = ''
            $psi.EnvironmentVariables['CLAUDE_PLUGIN_ROOT'] = ''
            $p = [System.Diagnostics.Process]::Start($psi)
            $p.StandardInput.Write($Payload)
            $p.StandardInput.Close()
            $o = $p.StandardOutput.ReadToEnd()
            $p.WaitForExit(20000) | Out-Null
            return $o
        }

        $safeOut   = Invoke-Hook $safeJson
        $dangerOut = Invoke-Hook $dangerJson
        $safeAllow  = [string]::IsNullOrWhiteSpace($safeOut)              # 통과 = 무출력
        $dangerDeny = ($dangerOut -match '"permissionDecision"\s*:\s*"deny"')

        if ($safeAllow -and $dangerDeny) {
            Add-Result 5 '가드훅 자가탐색' 'PASS' "env 없이 안전명령 통과 / 위험명령(rm -rf /) 차단 — 패턴 자가탐색 정상"
        } elseif (-not $safeAllow -and $dangerDeny) {
            Add-Result 5 '가드훅 자가탐색' 'FAIL' "위험은 차단하나 안전명령까지 차단됨 — 패턴 자가탐색 실패(fail-closed 전면차단 지뢰). 패턴이 훅 옆에 복사됐는지 확인"
        } elseif ($safeAllow -and -not $dangerDeny) {
            Add-Result 5 '가드훅 자가탐색' 'FAIL' "위험명령이 차단 안 됨(fail-open) — 심각. 훅/패턴 무결성 확인"
        } else {
            Add-Result 5 '가드훅 자가탐색' 'FAIL' "안전 통과 실패 AND 위험 차단 실패 — 훅 동작 이상"
        }
    } catch {
        Add-Result 5 '가드훅 자가탐색' 'FAIL' ("훅 fixture 예외: {0}" -f $_.Exception.Message)
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. CODEX_HOME 갈림길 리포트 (스코프4 — 읽기 전용. 자동 변경 금지, 사람 판단용)
# ─────────────────────────────────────────────────────────────────────────────
try {
    $lines = @()
    # 기본 codex 홈(관례): %USERPROFILE%\.codex
    $userHome = if ($env:USERPROFILE) { Join-Path $env:USERPROFILE '.codex' } else { '(USERPROFILE 미설정)' }
    $userAuth = if ($env:USERPROFILE) { Join-Path $userHome 'auth.json' } else { $null }
    $userAuthExists = ($userAuth -and (Test-Path -LiteralPath $userAuth))
    $pluginAuthExists = (Test-Path -LiteralPath $AuthPath)

    $lines += ("기본 홈 %USERPROFILE%\.codex\auth.json: {0}" -f ($(if ($userAuthExists) {'있음'} else {'없음'})))
    $lines += ("플러그인 CODEX_HOME\auth.json: {0}" -f ($(if ($pluginAuthExists) {'있음(bootstrap 완료)'} else {'없음(bootstrap 필요)'})))

    # codex login status 는 CODEX_HOME 에 따라 결과가 갈리므로, 두 경우를 각각 읽어 리포트(변경 없음)
    if (Test-CommandExists 'codex') {
        # 플러그인 CODEX_HOME 기준
        $env:CODEX_HOME = $CodexHome
        $stPlugin = (& codex login status 2>&1 | Select-Object -First 1)
        $lines += ("codex login status (CODEX_HOME=플러그인): {0}" -f $stPlugin)
    } else {
        $lines += "codex CLI 없어 login status 확인 불가"
    }

    # 방향 안내(자동 변경 아님, 사람 판단):
    $advice =
        if ($pluginAuthExists) {
            "방향a(현행): CODEX_HOME 고정 + bootstrap 이 채움 — 플러그인 auth 존재하므로 그대로 사용 권장."
        } elseif ($userAuthExists) {
            "기존 로그인은 기본 홈에 있음. bin\codex_bootstrap.ps1 실행해 플러그인 CODEX_HOME 으로 복사 필요(방향a)."
        } else {
            "양쪽 다 auth 없음 → 먼저 'codex login' 후 bin\codex_bootstrap.ps1 실행."
        }
    $lines += $advice

    Add-Result 6 'CODEX_HOME 리포트' 'SKIP' "리포트 전용(사람 판단). 아래 상세 참조"
    foreach ($l in $lines) { Write-Host ("       · {0}" -f $l) -ForegroundColor DarkGray }
} catch {
    Add-Result 6 'CODEX_HOME 리포트' 'SKIP' ("리포트 수집 중 예외(무해): {0}" -f $_.Exception.Message)
}

# ─────────────────────────────────────────────────────────────────────────────
# 요약 + 종료코드
# ─────────────────────────────────────────────────────────────────────────────
$pass = @($script:Results | Where-Object { $_.Status -eq 'PASS' }).Count
$fail = @($script:Results | Where-Object { $_.Status -eq 'FAIL' }).Count
$skip = @($script:Results | Where-Object { $_.Status -eq 'SKIP' }).Count

Write-Host ""
Write-Host "===== 요약 =====" -ForegroundColor Cyan
$summary = ("PASS {0} / FAIL {1} / SKIP {2}  (총 {3}항목)" -f $pass, $fail, $skip, $script:Results.Count)
if ($fail -gt 0) {
    Write-Host $summary -ForegroundColor Red
    Write-Host "→ FAIL 항목을 근거대로 해결 후 재실행하세요. (SKIP 은 실기 조건 불충족 — FAIL 아님)" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host $summary -ForegroundColor Green
    if ($skip -gt 0) {
        Write-Host "→ FAIL 없음. SKIP 은 해당 기능을 안 쓰면 무시 가능(예: .NET 미사용 시 dotnet SKIP)." -ForegroundColor Yellow
    } else {
        Write-Host "→ 전 항목 통과. 하네스가 이 환경에서 실동작함이 확인됐습니다." -ForegroundColor Green
    }
    exit 0
}
