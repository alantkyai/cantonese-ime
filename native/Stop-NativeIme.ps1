$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$readyPath = Join-Path $projectRoot '.local/native/backend-ready.json'
if (-not (Test-Path -LiteralPath $readyPath)) { Write-Output 'No broker ready file.'; return }
$ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
$brokerId = [int]$ready.pid
if ($brokerId -le 0) { throw 'Invalid broker identity.' }
$broker = Get-CimInstance Win32_Process -Filter "ProcessId=$brokerId"
if ($broker) {
    $serverPath = Join-Path $PSScriptRoot 'backend/server.py'
    if (-not $broker.CommandLine -or -not $broker.CommandLine.Contains($serverPath)) {
        throw 'Ready file identifies another process; refusing to terminate it.'
    }
    $stopped = Invoke-CimMethod -InputObject $broker -MethodName Terminate
    if ($stopped.ReturnValue -ne 0) { throw "Broker termination failed: $($stopped.ReturnValue)" }
    Write-Output "Stopped project broker PID $brokerId"
}
# Remove only this ready record, after confirming it still refers to that PID.
if (Test-Path -LiteralPath $readyPath) {
    $current = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
    if ([int]$current.pid -eq $brokerId) { Remove-Item -LiteralPath $readyPath }
}
