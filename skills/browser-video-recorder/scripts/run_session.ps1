# Unattended run: test clip -> checks -> record every video -> check each file.
#   run_session.ps1 -Config <work>\videos.json                  # all videos not yet saved
#   run_session.ps1 -Config <work>\videos.json -Only "03 - X"   # just these
#   run_session.ps1 -Config <work>\videos.json -TestSeconds 180 # override test length
#   run_session.ps1 -Config <work>\videos.json -TestOnly        # just the test clip + checks (new site/machine)
# Launch detached so it survives the chat:
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File "<this>" -Config "<cfg>"'
# Progress: <work>\runner.log (test passed / TEST FAILED / check results / runner: done)
param([Parameter(Mandatory)][string]$Config, [string[]]$Only = @(), [int]$TestSeconds = 0, [switch]$TestOnly)

$ErrorActionPreference = "Continue"
$scripts = $PSScriptRoot
$work = Split-Path (Resolve-Path $Config) -Parent
$py = Join-Path $work ".venv\Scripts\python.exe"
$runLog = Join-Path $work "runner.log"
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$out = $cfg.output_dir
# recorded.json entries, one per item. (Windows PowerShell 5.1's ConvertFrom-Json returns a JSON array as ONE
# object, so @(... | ConvertFrom-Json) is always a 1-item list - which hid every saved file from the checks.)
function Recorded {
    $raw = Get-Content (Join-Path $work "recorded.json") -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return @() }
    return @($raw | ConvertFrom-Json | ForEach-Object { $_ })
}
function Say($m) {
    # retry: a monitor reading the log at the same moment can briefly lock it
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"
    for ($i = 0; $i -lt 50; $i++) {
        try { Add-Content $runLog $line -Encoding utf8 -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 200 }
    }
}

# test length: past the display-off timeout, so the test proves the screen stays on
if ($TestSeconds -le 0) {
    $idx = (powercfg /q SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Select-String "Current AC Power Setting Index") -replace '.*:\s*0x', ''
    $timeout = if ($idx) { [Convert]::ToInt32($idx, 16) } else { 0 }
    $TestSeconds = if ($timeout -gt 0) { [Math]::Min([Math]::Max($timeout + 120, 180), 1200) } else { 180 }
}

Set-Location $work
Say "runner: start (videos: $(if ($Only) { $Only -join ', ' } else { 'all remaining' }); test $TestSeconds s)"
# 1. download first: videos whose site offers the file (download_url, found by find_videos.py)
if (-not $TestOnly -and @($cfg.videos | Where-Object { $_.download_url }).Count) {
    Say "runner: downloading the videos their sites offer as files"
    & $py -I "$scripts\download_videos.py" --config $Config *> $null
    foreach ($r in @(Recorded | Where-Object { $_.downloaded })) {
        if ($cfg.videos.name -contains $r.name) { Say "  downloaded $($r.name)" }
    }
}
# 2. the rest is recorded: the test uses the first video not saved yet (any extension)
$exts = ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".mpg", ".mpeg", ".ogv"
$first = $cfg.videos | Where-Object { $v = $_; -not ($exts | Where-Object { Test-Path -LiteralPath (Join-Path $out "$($v.name)$_") }) } |
    Select-Object -First 1
if (-not $first -and $TestOnly) { $first = $cfg.videos[0] }  # a test of the site is always possible
if (-not $first) { Say "runner: every video is already saved (recorded or downloaded); nothing to record"; Say "runner: done"; return }
# remove only this video's old test clip (other clips may be kept on purpose, e.g. from -TestOnly runs)
$testName = "TEST - $($first.name)"
Remove-Item -LiteralPath (Join-Path $out "$testName.mp4"), (Join-Path $out "$testName.mkv") -ErrorAction SilentlyContinue

Say "runner: test recording"
$recLogPath = Join-Path $work "recorder.log"
$logStart = if (Test-Path $recLogPath) { (Get-Content $recLogPath).Count } else { 0 }
& $py -I "$scripts\record_videos.py" --config $Config --test $TestSeconds *> $null
$clip = Get-Item -LiteralPath (Join-Path $out "$testName.mp4") -ErrorAction SilentlyContinue
$recLog = @(Get-Content $recLogPath | Select-Object -Skip $logStart)  # only this test's lines
if ($recLog -match "NOT RECORDABLE") {
    Say "runner: TEST FAILED - $(($recLog -match 'NOT RECORDABLE')[-1])"; Say "runner: done"; return
}
if (-not $clip) { Say "runner: TEST FAILED - no test clip saved (see recorder.log)"; Say "runner: done"; return }
$sheet = Join-Path $work "sheets\$testName.png"
# expected length as the recorder logged it (a video shorter than the test is tested whole)
$expected = $TestSeconds * 0.97
$rec = Recorded | Where-Object { $_.name -eq $testName } | Select-Object -Last 1
if ($rec -and $rec.expected) { $expected = [double]$rec.expected }
$check = & $py -I "$scripts\check_recording.py" $clip.FullName --expected $expected --test --sheet $sheet 2>&1
$check | ForEach-Object { Say "  $_" }
# "never showed up": the page states another length than what played (an ad?) - a test must not pass on that
$stalls = $recLog -match "stalled|failed|Traceback|reset itself|could not resume|never showed up"
if ($LASTEXITCODE -ne 0 -or $stalls) {
    if ($stalls) { Say "  recorder.log: $($stalls -join ' | ')" }
    Say "runner: TEST FAILED - not recording (see references/troubleshooting.md)"; Say "runner: done"; return
}
if ($TestOnly) { Say "runner: test passed (test only; clip kept: $($clip.Name))"; Say "runner: done"; return }
Say "runner: test passed; deleting test clip"
Remove-Item $clip.FullName

$before = @(Recorded).Count
Say "runner: recording"
if ($Only) { & $py -I "$scripts\record_videos.py" --config $Config --only @Only *> $null }
else { & $py -I "$scripts\record_videos.py" --config $Config *> $null }

$recorded = @(Recorded)
foreach ($r in ($recorded | Select-Object -Skip $before)) {
    if ($r.name -like "TEST - *") { continue }
    $res = & $py -I "$scripts\check_recording.py" $r.file --expected $r.expected 2>&1
    Say "  check $($r.name): $(($res | Select-String 'RESULT') -replace '.*RESULT: ', '')"
    $res | Where-Object { $_ -match "PROBLEM" } | ForEach-Object { Say "    $_" }
}
Say "runner: done"
