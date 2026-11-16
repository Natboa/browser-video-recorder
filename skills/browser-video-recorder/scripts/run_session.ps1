# Unattended run: test clip -> checks -> record every video -> check each file.
#   run_session.ps1 -Config <work>\videos.json                  # all videos not yet saved
#   run_session.ps1 -Config <work>\videos.json -Only "03 - X"   # just these
#   run_session.ps1 -Config <work>\videos.json -TestSeconds 180 # override test length
#   run_session.ps1 -Config <work>\videos.json -TestOnly        # just the test clip + checks (new site/machine)
#   run_session.ps1 -Config <work>\videos.json -TestStartSeconds 600 # choose a known talking section
# Launch detached so it survives the chat:
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File "<this>" -Config "<cfg>"'
# Progress: <work>\runner.log (test passed / TEST FAILED / check results / runner: done)
param([Parameter(Mandatory)][string]$Config, [string[]]$Only = @(), [int]$TestSeconds = 0, [switch]$TestOnly,
      [ValidateRange(-1, [double]::MaxValue)][double]$TestStartSeconds = -1)

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

function CaptureTest([double]$StartSeconds, [string]$Attempt) {
    Say "runner: test recording ($Attempt; start $(if ($StartSeconds -lt 0) { 'automatic' } else { $StartSeconds }) s)"
    $recLogPath = Join-Path $work "recorder.log"
    $logStart = if (Test-Path $recLogPath) { @(Get-Content $recLogPath).Count } else { 0 }
    $testArgs = @('--config', $Config, '--test', "$TestSeconds")
    if ($StartSeconds -ge 0) { $testArgs += @('--test-start', "$StartSeconds") }
    & $py -I "$scripts\record_videos.py" @testArgs *> $null
    $captureCode = $LASTEXITCODE
    $clip = Get-Item -LiteralPath (Join-Path $out "$testName.mp4") -ErrorAction SilentlyContinue
    $recLog = @(Get-Content $recLogPath -ErrorAction SilentlyContinue | Select-Object -Skip $logStart)
    $stalls = $recLog -match "NOT RECORDABLE|stalled|failed|Traceback|reset itself|could not resume|never showed up"
    if ($captureCode -ne 0 -or -not $clip -or $stalls) {
        Say "  capture failed or no completed test clip; recorder exit $captureCode"
        $stalls | ForEach-Object { Say "  recorder.log: $_" }
        return [pscustomobject]@{ Code = 1; Clip = $clip }
    }
    $expected = $TestSeconds * 0.97
    $rec = Recorded | Where-Object { $_.name -eq $testName } | Select-Object -Last 1
    if ($rec -and $rec.expected) { $expected = [double]$rec.expected }
    $sheet = Join-Path $work "sheets\$testName.png"
    $check = & $py -I "$scripts\check_recording.py" $clip.FullName --expected $expected --test --sheet $sheet 2>&1
    $checkCode = $LASTEXITCODE
    $check | ForEach-Object { Say "  $_" }
    return [pscustomobject]@{ Code = $checkCode; Clip = $clip }
}

$test = CaptureTest $TestStartSeconds 'initial'
if ($test.Code -eq 2) {
    # Preserve the inconclusive clip; source breaks and capture dropouts look alike.
    $savedTest = Join-Path $out "$testName - inconclusive-$([guid]::NewGuid().ToString('N').Substring(0,8)).mp4"
    Move-Item -LiteralPath $test.Clip.FullName -Destination $savedTest
    Say "runner: mixed sound/silence; kept $savedTest; retrying once elsewhere with all checks enabled"
    $retryStart = if ($TestStartSeconds -eq 60) { 600 } else { 60 }
    $test = CaptureTest $retryStart 'silence retry'
}
if ($test.Code -ne 0) {
    Say "runner: TEST FAILED - not recording (see references/troubleshooting.md)"; Say "runner: done (failed)"; exit 1
}
$clip = $test.Clip
if ($TestOnly) { Say "runner: test passed (test only; clip kept: $($clip.Name))"; Say "runner: done"; return }
Say "runner: test passed; deleting test clip"
Remove-Item $clip.FullName

$before = @(Recorded).Count
# Match the recorder's prefix filter without depending on recorded.json having new entries.
$wanted = @($cfg.videos | Where-Object {
    $name = $_.name
    -not $Only -or @($Only | Where-Object { $name.StartsWith($_) }).Count -gt 0
})
Say "runner: recording"
if ($Only) { & $py -I "$scripts\record_videos.py" --config $Config --only @Only *> $null }
else { & $py -I "$scripts\record_videos.py" --config $Config *> $null }
$recordFailed = $LASTEXITCODE -ne 0

$recorded = @(Recorded)
foreach ($video in $wanted) {
    $name = $video.name
    if (-not @($exts | Where-Object { Test-Path -LiteralPath (Join-Path $out "$name$_") }).Count) {
        Say "  missing recording: $name"
        $recordFailed = $true
    }
}
foreach ($r in ($recorded | Select-Object -Skip $before)) {
    if ($r.name -like "TEST - *") { continue }
    $res = & $py -I "$scripts\check_recording.py" $r.file --expected $r.expected 2>&1
    if ($LASTEXITCODE -ne 0) { $recordFailed = $true }
    Say "  check $($r.name): $(($res | Select-String 'RESULT') -replace '.*RESULT: ', '')"
    $res | Where-Object { $_ -match "PROBLEM" } | ForEach-Object { Say "    $_" }
}
Say "runner: done"
if ($recordFailed) { exit 1 }
